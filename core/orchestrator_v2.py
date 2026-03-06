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
from core.admin_tools import admin_tools
from langchain_core.utils.function_calling import convert_to_openai_tool

# --- DB PERSISTENCE ---
DB_PATH = os.path.join(os.getcwd(), config.sqlite_db_path)
LOCAL_SERVER_URL = config.local_server_url

def init_db():
    print(f"DEBUG: Initializing database at {DB_PATH}")
    try:
        # Убеждаемся, что директория существует
        db_dir = os.path.dirname(os.path.abspath(DB_PATH))
        if not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Сначала создаем таблицы, если их нет
        cur.execute('''CREATE TABLE IF NOT EXISTS chat_history (
            user_id TEXT, 
            agent_type TEXT, 
            role TEXT, 
            content TEXT, 
            timestamp DATETIME
        )''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS agent_settings (
            user_id TEXT,
            agent_type TEXT,
            setting_key TEXT,
            setting_value TEXT,
            PRIMARY KEY (user_id, agent_type, setting_key)
        )''')
        
        # Теперь проверяем и добавляем колонку model_name в chat_history
        cur.execute("PRAGMA table_info(chat_history)")
        columns = [col[1] for col in cur.fetchall()]
        if 'model_name' not in columns:
            cur.execute('ALTER TABLE chat_history ADD COLUMN model_name TEXT')
        
        conn.commit()
        conn.close()
        print("DEBUG: Database initialization successful")
    except Exception as e:
        print(f"DEBUG: DATABASE ERROR: {str(e)}")

# Вызываем инициализацию при импорте модуля
init_db()

def save_message(user_id, agent_type, role, content, model_name=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT INTO chat_history (user_id, agent_type, role, content, timestamp, model_name) VALUES (?, ?, ?, ?, ?, ?)', 
                (user_id, agent_type, role, content, datetime.now(), model_name))
    conn.commit()
    conn.close()

def get_agent_setting(user_id, agent_type, key, default=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT setting_value FROM agent_settings WHERE user_id = ? AND agent_type = ? AND setting_key = ?', 
                    (user_id, agent_type, key))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default
    except sqlite3.OperationalError:
        # Если таблицы или колонки нет, пробуем пересоздать через init_db и возвращаем дефолт
        init_db()
        return default

def save_agent_setting(user_id, agent_type, key, value):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''INSERT OR REPLACE INTO agent_settings (user_id, agent_type, setting_key, setting_value) 
                       VALUES (?, ?, ?, ?)''', (user_id, agent_type, key, value))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        init_db()
        # Повторная попытка после исправления структуры
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''INSERT OR REPLACE INTO agent_settings (user_id, agent_type, setting_key, setting_value) 
                       VALUES (?, ?, ?, ?)''', (user_id, agent_type, key, value))
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

from core.memory import vector_db_search_tool as local_vector_search

def vector_db_search_tool(query: str, top_k: int = 3) -> str:
    """Поиск по базе знаний (Obsidian, документы). Перенаправляет на Home Lab, если настроен удаленный эндпоинт."""
    remote_worker = os.getenv("REMOTE_WORKER_URL", "none")
    api_secret = os.getenv("API_SECRET", "change_me_in_env")

    if remote_worker != "none":
        try:
            response = requests.post(
                f"{remote_worker.rstrip('/')}/search",
                params={"query": query},
                headers={"X-Token": api_secret},
                timeout=15
            )
            if response.status_code == 200:
                return response.json().get("results", "Ничего не найдено.")
            return f"Ошибка воркера: {response.status_code}"
        except Exception as e:
            return f"Нет связи с Home Lab RAG: {str(e)}"
    
    return local_vector_search(query, top_k)

OBSIDIAN_TOOLS = [obsidian_capture_tool, obsidian_read_note_tool, obsidian_log_thought_tool, vector_db_search_tool]
ADMIN_TOOLS = [
    admin_tools.check_connection,
    admin_tools.get_docker_status,
    admin_tools.get_gpu_info,
    admin_tools.request_shell_execution,
    vector_db_search_tool
]

# --- AGENT CORE ---
AGENT_REGISTRY = {
    'general': {'name': 'Общий ассистент'},
    'german': {'name': 'Herr Max Klein (Учитель)'},
    'career': {'name': 'HR-Эксперт'},
    'vds_admin': {'name': 'Админ VDS (DevOps)'},
    'local_admin': {'name': 'Админ Локальный (Home Lab)'}
}

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    agent_type: str
    model_override: str
    user_id: str

def get_model(purpose='general', model_override=None, user_id=None):
    if not config.google_api_key or not config.groq_api_key:
        raise ValueError('Missing API keys in config.py')

    # Приоритет: 1. override из UI, 2. Сохраненная настройка из БД, 3. Default
    model_name = model_override
    if not model_name and user_id:
        model_name = get_agent_setting(user_id, purpose, 'selected_model')

    if not model_name:
        if purpose == 'german': model_name = 'gemini-3.1-pro-preview'
        elif purpose == 'career': model_name = 'gemini-2.5-flash'
        elif purpose in ['vds_admin', 'local_admin']: model_name = 'ollama/llama3.1:8b'
        else: model_name = 'llama-3.3-70b-versatile'

    # Поддержка Ollama через LangChain
    if model_name.startswith('ollama/'):
        from langchain_ollama import ChatOllama
        actual_model = model_name.replace('ollama/', '')
        return ChatOllama(model=actual_model, base_url=config.local_server_url)

    if 'gemini' in model_name:
        return ChatGoogleGenerativeAI(
            model=model_name, 
            google_api_key=config.google_api_key,
            convert_system_message_to_human=True,
            version="v1beta"
        )
        
    return ChatGroq(model_name=model_name, api_key=config.groq_api_key)

def is_ollama_online():
    """Проверка доступности Ollama через VPN (10.8.0.x), локальные сети (192.168.x.x) или Docker."""
    env_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip('/')
    
    # Список разрешенных сетей для безопасности
    ALLOWED_NETWORKS = ["10.8.0.", "192.168.88.", "192.168.2.", "http://ollama"]
    
    try:
        # 1. Проверка основного URL
        if any(net in env_url for net in ALLOWED_NETWORKS):
            response = requests.get(f"{env_url}/api/tags", timeout=3)
            if response.status_code == 200:
                return True
            
        # 2. Запасной вариант: внутренняя сеть Docker
        response = requests.get("http://ollama:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

def node_handler(state: AgentState):
    agent_type = state.get('agent_type', 'general')
    model_override = state.get('model_override')
    # Передаем user_id для поиска сохраненной модели
    # (состояние графа расширено в process_message ниже)
    user_id = state.get('user_id', '207398589') 
    
    llm = get_model(agent_type, model_override, user_id=user_id)
    
    # Привязываем инструменты в зависимости от типа агента
    if agent_type == 'german':
        llm_with_tools = llm.bind_tools(OBSIDIAN_TOOLS)
    elif agent_type in ['vds_admin', 'local_admin']:
        llm_with_tools = llm.bind_tools(ADMIN_TOOLS)
    else:
        llm_with_tools = llm
    
    system_prompts = {
        'german': 'Ты Herr Max Klein, профессиональный учитель немецкого. Ответы на немецком, пояснения на русском. Используй Sie. У тебя есть доступ к Obsidian через инструменты.',
        'career': 'Ты эксперт по карьере и HR. Помогай с резюме и стратегией роста. Твой тон профессиональный.',
        'vds_admin': 'Ты системный администратор VDS. Твоя задача — мониторинг контейнеров, сети Traefik и логов. Если хочешь выполнить опасную команду, используй request_shell_execution.',
        'local_admin': 'Ты администратор домашней лаборатории на Proxmox. У тебя есть доступ к данным о GPU P4000. Помогай настраивать локальные нейросети.',
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
            # Admin Tools
            elif tool_name == 'check_connection':
                result = admin_tools.check_connection(**args)
            elif tool_name == 'get_docker_status':
                result = admin_tools.get_docker_status(**args)
            elif tool_name == 'get_gpu_info':
                result = admin_tools.get_gpu_info()
            elif tool_name == 'request_shell_execution':
                result = admin_tools.request_shell_execution(**args)
            elif tool_name == 'obsidian_read_note_tool':
                result = obsidian_read_note_tool(**args)
            elif tool_name == 'obsidian_log_thought_tool':
                result = obsidian_log_thought_tool(**args)
            elif tool_name == 'vector_db_search_tool':
                result = vector_db_search_tool(**args)
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
    # Сохраняем модель в БД, если она была выбрана вручную в UI
    if model_override:
        save_agent_setting(user_id, agent_type, 'selected_model', model_override)
    
    save_message(user_id, agent_type, 'user', text, model_name=model_override)
    history_raw = get_chat_history_db(user_id, agent_type)
    msgs = []
    for m in history_raw[-10:]:
        if m['role'] == 'user': msgs.append(HumanMessage(content=m['content']))
        else: msgs.append(AIMessage(content=m['content']))
    
    inputs = {
        'messages': msgs, 
        'agent_type': agent_type, 
        'model_override': model_override,
        'user_id': user_id
    }
    
    # Увеличиваем лимит рекурсии до 50 для сложных запросов администратора
    res = app.invoke(inputs, config={"recursion_limit": 50})
    ai_text = res['messages'][-1].content
    save_message(user_id, agent_type, 'assistant', ai_text, model_name=model_override)
    return {'text': ai_text, 'active_node': agent_type}

def get_chat_history(uid): return get_chat_history_db(uid)

def is_copilot_configured(): return True
