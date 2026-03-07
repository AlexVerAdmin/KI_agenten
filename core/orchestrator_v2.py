import os
import sqlite3
import json
from datetime import datetime
from typing import Annotated, TypedDict, List, Union, Optional
from typing_extensions import Required

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, END

from config import config

# ГЛОБАЛЬНЫЙ РЕЕСТР АГЕНТОВ (для UI)
AGENT_REGISTRY = {
    'general': {'name': '🤖 Помощник', 'desc': 'Общие вопросы и поиск в Obsidian'},
    'german': {'name': '🇩🇪 Herr Max Klein', 'desc': 'Учитель немецкого языка'},
    'career': {'name': '💼 HR-Эксперт', 'desc': 'Консультант по трудоустройству'},
    'finance': {'name': '💰 Финансы', 'desc': 'Управление личными финансами (Obsidian)'},
    'vds_admin': {'name': '🌐 VDS Admin', 'desc': 'Управление Docker и системный мониторинг'},
    'local_admin': {'name': '🏠 Local Admin', 'desc': 'Управление локальным сервером'}
}

# Настройка путей
DB_PATH = os.environ.get('SQLITE_DB_PATH', '/app/data/memory_v2.sqlite')

# Типизация состояния
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], "The messages in the conversation"]
    agent_type: str
    model_override: Optional[str]
    user_id: str

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_name TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS agent_settings (
            user_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT,
            PRIMARY KEY (user_id, agent_type, setting_key)
        )
    ''')
    cur.execute("PRAGMA table_info(chat_history)")
    columns = [column[1] for column in cur.fetchall()]
    if 'model_name' not in columns:
        try:
            cur.execute('ALTER TABLE chat_history ADD COLUMN model_name TEXT')
        except: pass
    conn.commit()
    conn.close()

init_db()

def save_message(user_id, agent_type, role, content, model_name=None):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    if not isinstance(role, str): role = str(role)

    if not isinstance(content, str):
        try:
            # Если это список сообщений от Google (как в жалобе), извлекаем текст
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        text_parts.append(item['text'])
                    else:
                        text_parts.append(str(item))
                content = "".join(text_parts)
            else:
                content = str(content)
        except:
            content = "[Unserializable Content]"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT INTO chat_history (user_id, agent_type, role, content, timestamp, model_name) VALUES (?, ?, ?, ?, ?, ?)', 
                (user_id, agent_type, role, content, datetime.now(), model_name))
    conn.commit()
    conn.close()

def get_agent_setting(user_id, agent_type, key, default=None):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT setting_value FROM agent_settings WHERE user_id = ? AND agent_type = ? AND setting_key = ?', 
                    (user_id, agent_type, key))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default
    except sqlite3.OperationalError:
        init_db()
        return default

def save_agent_setting(user_id, agent_type, key, value):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''INSERT OR REPLACE INTO agent_settings (user_id, agent_type, setting_key, setting_value) 
                     VALUES (?, ?, ?, ?)''', (user_id, agent_type, key, value))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DEBUG: Error saving setting: {e}")

def get_chat_history_db(user_id, agent_type=None):
    if not isinstance(user_id, str): user_id = str(user_id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if agent_type:
        if not isinstance(agent_type, str): agent_type = str(agent_type)
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

def get_model(model_name: str, temperature=0):
    if model_name.startswith('gemini'):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature, version="v1beta")
    elif model_name.startswith('llama') or model_name.startswith('mixtral'):
        from langchain_groq import ChatGroq
        return ChatGroq(model_name=model_name, temperature=temperature)
    elif model_name.startswith('ollama/'):
        from langchain_community.chat_models import ChatOllama
        actual_model = model_name.replace('ollama/', '')
        return ChatOllama(model=actual_model, base_url=config.local_server_url, temperature=temperature)
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_name, temperature=temperature)

def is_ollama_online():
    import requests
    try:
        url = config.local_server_url.rstrip('/') + '/api/tags'
        resp = requests.get(url, timeout=2)
        return resp.status_code == 200
    except:
        return False

SYSTEM_PROMPTS = {
    'general': 'Ты полезный ИИ-помощник.',
    'german': 'Ты Herr Max Klein, профессиональный учитель немецкого. Твой ученик — будущий аналитик данных. Твоя цель — снять языковой барьер. ПРАВИЛО: Все новые фразы и слова, которые мы обсуждаем, ты ДОЛЖЕН автоматически сохранять в Obsidian, используя инструмент obsidian_capture_tool. Не проси пользователя копировать текст вручную — делай это сам! Общайся на немецком, поясняй на русском. У тебя есть доступ к Obsidian через инструменты.',
    'career': 'Ты экспертный консультант по трудоустройству в Германии и IT-сфере. Помогаешь с резюме, поиском вакансий и подготовкой к интервью.',
    'vds_admin': 'Ты администратор VDS сервера. Используй инструменты для управления контейнерами и мониторинга.',
    'local_admin': 'Ты администратор локального сервера (EuroStick). Используй инструменты для проверки статуса железа и синхронизации.'
}

def get_tools_for_agent(agent_type):
    from core.admin_tools import admin_tools
    from core.utils_obsidian import obsidian_capture_tool
    if agent_type == 'german':
        return [obsidian_capture_tool]
    if agent_type in ['vds_admin', 'local_admin']:
        return [
            admin_tools.get_docker_status,
            admin_tools.check_connection,
            admin_tools.run_remote_command
        ]
    return []

def node_handler(state: AgentState):
    agent_type = state['agent_type']
    model_name = state.get('model_override') or 'gemini-1.5-flash'
    llm = get_model(model_name)
    tools = get_tools_for_agent(agent_type)
    if tools: llm = llm.bind_tools(tools)
    sys_msg = SystemMessage(content=SYSTEM_PROMPTS.get(agent_type, SYSTEM_PROMPTS['general']))
    messages = [sys_msg] + state['messages']
    response = llm.invoke(messages)
    return {'messages': [response]}

def tool_node(state: AgentState):
    from core.admin_tools import admin_tools
    last_message = state['messages'][-1]
    tool_results = []
    if hasattr(last_message, 'tool_calls'):
        for tool_call in last_message.tool_calls:
            tool_name = tool_call['name']
            args = tool_call['args']
            if tool_name == 'get_docker_status': result = admin_tools.get_docker_status(**args)
            elif tool_name == 'check_connection': result = admin_tools.check_connection(**args)
            elif tool_name == 'run_remote_command': result = admin_tools.run_remote_command(**args)
            else: result = f"Error: Tool {tool_name} not found."
            tool_results.append(ToolMessage(tool_call_id=tool_call['id'], content=str(result)))
    return {'messages': tool_results}

def should_continue(state: AgentState):
    last_message = state['messages'][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return 'tools'
    return END

workflow = StateGraph(AgentState)
workflow.add_node('agent', node_handler)
workflow.add_node('tools', tool_node)
workflow.set_entry_point('agent')
workflow.add_conditional_edges('agent', should_continue)
workflow.add_edge('tools', 'agent')
app = workflow.compile()

def get_user_agent(user_id):
    """Fallback for Telegram logic missing in V2"""
    return get_agent_setting(user_id, 'all', 'last_agent', 'general')

def set_user_agent(user_id, agent_type):
    """Fallback for Telegram logic missing in V2"""
    save_agent_setting(user_id, 'all', 'last_agent', agent_type)

def process_message(text, user_id, agent_type=None, thread_id=None, model_override=None, **kwargs):
    init_db()
    
    # --- МАППИНГ ТЕМ (Topics) В ТЕЛЕГРАМЕ ---
    topic_mapping = {
        2: "german",   # Учитель
        8: "career",   # Консультант/HR
        11: "finance"  # Финансы
    }
    
    if thread_id in topic_mapping:
        agent_type = topic_mapping[thread_id]
        set_user_agent(user_id, agent_type)
    
    if agent_type is None:
        agent_type = get_user_agent(user_id)

    # --- СТРОГИЙ ПРЕФИКСНЫЙ ПЕРЕКЛЮЧАТЕЛЬ ---
    lower_text = text.lower()
    clean_text = text
    
    if lower_text.startswith("передай учителю") or lower_text.startswith("передай максу") or lower_text.startswith("учитель,"):
        agent_type = "german"
        clean_text = text.replace("Передай учителю", "").replace("передай учителю", "").replace("Учитель,", "").replace("учитель,", "").strip()
        set_user_agent(user_id, agent_type) 
    elif lower_text.startswith("передай в финансы") or lower_text.startswith("запиши расход"):
        agent_type = "finance"
        clean_text = text.replace("Передай в финансы", "").replace("передай в финансы", "").strip()
        set_user_agent(user_id, agent_type)
    elif lower_text.startswith("передай hr") or lower_text.startswith("передай коучу"):
        agent_type = "career"
        clean_text = text.replace("Передай hr", "").replace("передай hr", "").strip()
        set_user_agent(user_id, agent_type)
    
    if not clean_text: clean_text = text

    if model_override: save_agent_setting(user_id, agent_type, 'selected_model', model_override)
    save_message(user_id, agent_type, 'user', clean_text, model_name=model_override)
    
    history_raw = get_chat_history_db(user_id, agent_type)
    msgs = []
    for m in history_raw[-15:]:
        if m['role'] == 'user': msgs.append(HumanMessage(content=m['content']))
        elif m['role'] == 'assistant': msgs.append(AIMessage(content=m['content']))
    
    inputs = {'messages': msgs, 'agent_type': agent_type, 'model_override': model_override, 'user_id': user_id}
    try:
        res = app.invoke(inputs, config={"recursion_limit": 50})
        ai_msg = res['messages'][-1]
        ai_text = ai_msg.content
        if isinstance(ai_text, list):
            text_parts = [part['text'] for part in ai_text if isinstance(part, dict) and 'text' in part]
            ai_text = "".join(text_parts)
        elif not isinstance(ai_text, str):
            ai_text = str(ai_text)
            
        save_message(user_id, agent_type, 'assistant', ai_text, model_name=model_override)
        return {'text': ai_text, 'active_node': agent_type}
    except Exception as e:
        error_msg = f"Ошибка выполнения: {str(e)}"
        save_message(user_id, agent_type, 'assistant', error_msg, model_name=model_override)
        return {'text': error_msg, 'active_node': agent_type}

def get_chat_history(uid): return get_chat_history_db(uid)
def is_copilot_configured(): return True
