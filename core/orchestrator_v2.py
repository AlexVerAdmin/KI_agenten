import sqlite3
import json
import logging, os
import requests
from datetime import datetime
from typing import Annotated, Literal, TypedDict, List, Union
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from config import config
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from core.utils_obsidian import obsidian
from langchain_core.utils.function_calling import convert_to_openai_tool

# --- DB PERSISTENCE ---
DB_PATH = config.sqlite_db_path
LOCAL_SERVER_URL = config.local_server_url

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT, agent_type TEXT, role TEXT, content TEXT, timestamp DATETIME)')
    conn.commit()
    conn.close()

def save_message(user_id, agent_type, role, content):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT INTO chat_history (user_id, agent_type, role, content, timestamp) VALUES (?, ?, ?, ?, ?)', 
                (user_id, agent_type, role, content, datetime.now()))
    conn.commit()
    conn.close()

def get_chat_history_db(user_id, agent_type=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if agent_type:
        cur.execute('SELECT role, content, agent_type, timestamp FROM chat_history WHERE user_id = ? AND agent_type = ? ORDER BY timestamp ASC', (user_id, agent_type))
    else:
        cur.execute('SELECT role, content, agent_type, timestamp FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{'role': r[0], 'content': r[1], 'agent': r[2], 'timestamp': r[3]} for r in rows]

def clear_chat_history(user_id, agent_type=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if agent_type:
        cur.execute('DELETE FROM chat_history WHERE user_id = ? AND agent_type = ?', (user_id, agent_type))
    else:
        cur.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True

init_db()

# --- TOOLS DEFINITION ---
def obsidian_capture_tool(content: str, title: str = None) -> str:
    """Быстрое сохранение заметки во входящие (Inbox) Obsidian. 
    Используй для сохранения планов обучения, заметок и идей."""
    return obsidian.capture_to_inbox(content, title)

def obsidian_read_note_tool(relative_path: str) -> str:
    """Чтение содержимого заметки из Obsidian по относительному пути (например, '_Inbox/Note.md')."""
    return obsidian.read_note(relative_path) or "Заметка не найдена"

def obsidian_log_thought_tool(content: str) -> str:
    """Запись мысли или события в ежедневный файл (Daily Note)."""
    return obsidian.log_thought(content)

OBSIDIAN_TOOLS = [obsidian_capture_tool, obsidian_read_note_tool, obsidian_log_thought_tool]

# --- AGENT CORE ---
AGENT_REGISTRY = {
    'general': {'name': 'Общий ассистент'},
    'german': {'name': 'Herr Max Klein (Учитель)'},
    'career': {'name': 'HR-Эксперт'}
}

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    agent_type: str
    model_override: str

def get_model(purpose='general', model_override=None):
    if not config.google_api_key or not config.groq_api_key:
        raise ValueError('Missing API keys in config.py')

    model_name = model_override
    if not model_name:
        if purpose == 'german': model_name = 'gemini-1.5-pro'
        elif purpose == 'career': model_name = 'gemini-1.5-flash'
        else: return ChatGroq(model_name='llama-3.3-70b-versatile', api_key=config.groq_api_key)

    if 'gemini' in model_name:
        return ChatGoogleGenerativeAI(
            model=model_name, 
            google_api_key=config.google_api_key,
            convert_system_message_to_human=True,
            version="v1"  # Явно заставляем использовать стабильную версию v1
        )
    return ChatGroq(model_name='llama-3.3-70b-versatile', api_key=config.groq_api_key)

def node_handler(state: AgentState):
    agent_type = state.get('agent_type', 'general')
    model_override = state.get('model_override')
    llm = get_model(agent_type, model_override)
    
    # Привязываем инструменты если агент Herr Max Klein
    if agent_type == 'german':
        llm_with_tools = llm.bind_tools(OBSIDIAN_TOOLS)
    else:
        llm_with_tools = llm
    
    system_prompts = {
        'german': 'Ты Herr Max Klein, профессиональный учитель немецкого. Ответы на немецком, пояснения на русском. Используй Sie. У тебя есть доступ к Obsidian (второму мозгу) через инструменты. Сохраняй там важные планы обучения и читай их при необходимости.',
        'career': 'Ты эксперт по карьере и HR. Помогай с резюме, поиском работы и стратегией роста. Твой тон профессиональный и глубокий.',
        'general': 'Ты универсальный ИИ-ассистент. Отвечай четко и по делу.'
    }
    
    messages = [SystemMessage(content=system_prompts.get(agent_type, system_prompts['general']))] + state['messages']
    response = llm_with_tools.invoke(messages)
    return {'messages': [response]}

# Реакция на инструменты (Tool Node)
def tool_node(state: AgentState):
    messages = state['messages']
    last_message = messages[-1]
    
    tool_results = []
    if last_message.tool_calls:
        for tool_call in last_message.tool_calls:
            tool_name = tool_call['name']
            args = tool_call['args']
            
            if tool_name == 'obsidian_capture_tool':
                result = obsidian_capture_tool(**args)
            elif tool_name == 'obsidian_read_note_tool':
                result = obsidian_read_note_tool(**args)
            elif tool_name == 'obsidian_log_thought_tool':
                result = obsidian_log_thought_tool(**args)
            else:
                result = "Unknown tool"
                
            tool_results.append(ToolMessage(
                tool_call_id=tool_call['id'],
                content=str(result)
            ))
    return {'messages': tool_results}

def should_continue(state: AgentState):
    last_message = state['messages'][-1]
    if last_message.tool_calls:
        return 'tools'
    return END

workflow = StateGraph(AgentState)
workflow.add_node('agent', node_handler)
workflow.add_node('tools', tool_node)
workflow.set_entry_point('agent')
workflow.add_conditional_edges('agent', should_continue)
workflow.add_edge('tools', 'agent')
app = workflow.compile()

def process_message(text, user_id, agent_type='general', model_override=None, **kwargs):
    save_message(user_id, agent_type, 'user', text)
    history_raw = get_chat_history_db(user_id, agent_type)
    msgs = []
    for m in history_raw[-10:]:
        if m['role'] == 'user': msgs.append(HumanMessage(content=m['content']))
        else: msgs.append(AIMessage(content=m['content']))
    inputs = {'messages': msgs, 'agent_type': agent_type, 'model_override': model_override}
    res = app.invoke(inputs)
    ai_text = res['messages'][-1].content
    save_message(user_id, agent_type, 'assistant', ai_text)
    return {'text': ai_text, 'active_node': agent_type}

def get_chat_history(uid): return get_chat_history_db(uid)

def is_ollama_online():
    """Проверка доступности локального Ollama сервера (GPU-нода)"""
    try:
        response = requests.get(f"{LOCAL_SERVER_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

def is_copilot_configured(): return True
