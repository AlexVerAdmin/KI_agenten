import sqlite3
import json
from datetime import datetime
from typing import Annotated, Literal, TypedDict, List, Union
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
import logging, os
from config import config
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# --- DB PERSISTENCE ---
DB_PATH = 'memory_v2.sqlite'

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
        cur.execute('SELECT role, content, agent_type FROM chat_history WHERE user_id = ? AND agent_type = ? ORDER BY timestamp ASC', (user_id, agent_type))
    else:
        cur.execute('SELECT role, content, agent_type FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{'role': r[0], 'content': r[1], 'agent': r[2]} for r in rows]

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
        if purpose == 'german': model_name = 'gemini-3.1-pro-preview'
        elif purpose == 'career': model_name = 'gemini-3.0-flash-preview'
        else: return ChatGroq(model_name='llama-3.3-70b-versatile', api_key=config.groq_api_key)

    if 'gemini' in model_name:
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=config.google_api_key)
    return ChatGroq(model_name='llama-3.3-70b-versatile', api_key=config.groq_api_key)

def node_handler(state: AgentState):
    agent_type = state.get('agent_type', 'general')
    model_override = state.get('model_override')
    llm = get_model(agent_type, model_override)
    
    system_prompts = {
        'german': 'Ты Herr Max Klein, профессиональный учитель немецкого. Отвечай на немецком, поясняй на русском. Используй вежливое Sie.',
        'career': 'Ты эксперт по карьере и HR. Помогай с резюме, поиском работы и стратегией роста. Твой тон профессиональный и глубокий.',
        'general': 'Ты универсальный ИИ-ассистент. Отвечай четко и по делу.'
    }
    
    messages = [SystemMessage(content=system_prompts.get(agent_type, system_prompts['general']))] + state['messages']
    response = llm.invoke(messages)
    return {'messages': [response]}

workflow = StateGraph(AgentState)
workflow.add_node('agent', node_handler)
workflow.set_entry_point('agent')
workflow.add_edge('agent', END)
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
def is_ollama_online(): return False
def is_copilot_configured(): return True
