import os
import sqlite3
import json
from datetime import datetime
from typing import Annotated, TypedDict, List, Union, Optional
# Удаляем проблемный импорт, так как Required есть в typing для Python 3.11+
# from typing_extensions import Required

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
# ПРИОРИТЕТ: локальная папка, если нет переменной Docker
DB_PATH = os.environ.get('SQLITE_DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'memory_v2.sqlite'))

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
            model_name TEXT,
            deleted_at DATETIME DEFAULT NULL
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
    if 'deleted_at' not in columns:
        try:
            cur.execute('ALTER TABLE chat_history ADD COLUMN deleted_at DATETIME DEFAULT NULL')
        except: pass
    conn.commit()
    conn.close()

init_db()

def save_message(user_id, agent_type, role, content, model_name=None):
    if not isinstance(content, str):
        try:
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        text_parts.append(item['text'])
                    elif hasattr(item, 'text'):
                        text_parts.append(item.text)
                    elif isinstance(item, str):
                        text_parts.append(item)
                    else:
                        text_parts.append(str(item))
                content = "".join(text_parts)
            else:
                content = str(content)
        except:
            content = "[Unserializable Content]"
    
    # ФИНАЛЬНАЯ ПРОВЕРКА ПЕРЕД SQL — только строки
    content = str(content)
    user_id = str(user_id) if user_id else "unknown"
    agent_type = str(agent_type) if agent_type else "general"
    role = str(role) if role else "assistant"
    model_name = str(model_name) if model_name else ""

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        # ПАРАМЕТР 4: index 3 (content). ЕСЛИ ОН ВСЕ ЕЩЕ ЛИСТ - ЭТО ЧУДО.
        cur.execute('INSERT INTO chat_history (user_id, agent_type, role, content, timestamp, model_name) VALUES (?, ?, ?, ?, ?, ?)', 
                    (user_id, agent_type, role, content, datetime.now().isoformat(), model_name))
        conn.commit()
    except Exception as e:
        import logging
        logging.error(f"SQL SAVE ERROR: {e}. Parameter types: user_id={type(user_id)}, agent={type(agent_type)}, role={type(role)}, content={type(content)}")
    finally:
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

def get_chat_history_db(user_id, agent_type=None, include_deleted=False):
    if not isinstance(user_id, str): user_id = str(user_id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Базовое условие: только не удаленные сообщения по умолчанию
    delete_filter = "" if include_deleted else " AND deleted_at IS NULL"
    
    if agent_type:
        if not isinstance(agent_type, str): agent_type = str(agent_type)
        query = f'SELECT role, content, agent_type, timestamp, id, deleted_at FROM chat_history WHERE user_id = ? AND agent_type = ?{delete_filter} ORDER BY timestamp ASC'
        cur.execute(query, (user_id, agent_type))
    else:
        query = f'SELECT role, content, agent_type, timestamp, id, deleted_at FROM chat_history WHERE user_id = ?{delete_filter} ORDER BY timestamp ASC'
        cur.execute(query, (user_id,))
        
    rows = cur.fetchall()
    conn.close()
    return [{'role': r[0], 'content': r[1], 'agent': r[2], 'timestamp': r[3], 'id': r[4], 'deleted_at': r[5]} for r in rows]

def soft_delete_message(message_id):
    """Помечает сообщение как удаленное (мягкое удаление)"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('UPDATE chat_history SET deleted_at = ? WHERE id = ?', (datetime.now().isoformat(), message_id))
    conn.commit()
    conn.close()
    return True

def restore_message(message_id):
    """Восстанавливает мягко удаленное сообщение"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('UPDATE chat_history SET deleted_at = NULL WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()
    return True

def cleanup_deleted_messages():
    """Окончательно удаляет сообщения, помеченные удаленными более 30 дней назад"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Удаляем записи, где deleted_at старше 30 дней
    cur.execute("DELETE FROM chat_history WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', '-30 days')")
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count

def clear_chat_history(user_id, agent_type=None):
    # Запускаем очистку старых сообщений при каждой очистке истории или по вызову
    cleanup_deleted_messages()
    
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
    # ПРИНУДИТЕЛЬНАЯ УСТАНОВКА API КЛЮЧА ИЗ КОНФИГА
    if model_name.startswith('gemini'):
        import os
        from config import config
        if config.google_api_key:
            os.environ["GOOGLE_API_KEY"] = config.google_api_key
        
        from langchain_google_genai import ChatGoogleGenerativeAI
        print(f"DEBUG: Initializing Gemini model: {model_name}")
        return ChatGoogleGenerativeAI(model=model_name, temperature=temperature)
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
    'german': """Ты Herr Max Klein, опытный преподаватель немецкого языка использующий 
    современные, проверенные и эффективные методики для обучения.
    Используй Obsidian через `obsidian_capture_tool` как долговременную память. Заноси туда
слова или фразы, которые считаешь важными для запоминания и используй их для "интервального
повторения" с учеником.
Новое немецкое слово заносится в Obsidian по правилам:
- имя заметки - это само слово на немецком для существительного без артикля, для глагола - инфинитив.
- в шапке заметки поля:
    - wort: слово на немецком(для существительного с артиклем и окончанием множественного числа (-en),
        для глагола - три его формы)
    - übersetzung: перевод на русский
    - Beispiel: пара примеров употребления в немецком с переводом на русский
    - Synonyme: синонимы (если есть)
    - created: дата и время создания заметки
    - tags: #Deutsch #Words
    - status: нова (для новых слов)
    - in_dict: false
- тело заметки
    само слово
    Заметка о нюансах использования.
В отдельной заметке сохраняй все пожелания ученика и свои идеи по улучшению обучения.
Периодически просматривай эту заметку и вноси изменения в методику обучения, основываясь на пожеланиях ученика и своем опыте.

""",
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
    agent_type = state.get('agent_type', 'general')
    model_name = state.get('model_override') or 'gemini-3.1-flash-lite-preview'
    llm = get_model(model_name)
    tools = get_tools_for_agent(agent_type)
    
    # СИСТЕМНЫЙ ПРОМПТ
    sys_msg_text = SYSTEM_PROMPTS.get(agent_type, SYSTEM_PROMPTS['general'])
    
    # --- ДИНАМИЧЕСКИЙ КОНТЕКСТ ДЛЯ УЧИТЕЛЯ ---
    if agent_type == 'german':
        try:
            profile_path = os.path.join(os.path.dirname(__file__), '..', 'knowledge', 'german', 'student_profile.md')
            plan_path = os.path.join(os.path.dirname(__file__), '..', 'knowledge', 'german', 'learning_plan.md')
            
            profile_content = ""
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile_content = f.read()
            
            plan_content = ""
            if os.path.exists(plan_path):
                with open(plan_path, 'r', encoding='utf-8') as f:
                    plan_content = f.read()
            
            if profile_content or plan_content:
                sys_msg_text += f"\n\n### ДАННЫЕ УЧЕНИКА И ПЛАН:\n{profile_content}\n\n{plan_content}"
                sys_msg_text += "\n\nПРАВИЛО: Если ты обсуждаешь с учеником план, обязательно обнови файл learning_plan.md с помощью инструмента obsidian_capture_tool."
        except Exception as e:
            print(f"Error loading german context: {e}")

    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ДЛЯ GEMINI 3/2.0+
    # Модели Google API очень чувствительны к "пустым сообщениям" в истории.
    # Ошибка 'contents are required' возникает, когда в запросе есть сообщение с пустым content.
    formatted_messages = [SystemMessage(content=sys_msg_text)]
    
    for m in state['messages']:
        content = m.content
        
        # 1. Извлекаем текст (может быть списком в некоторых версиях LangChain)
        if isinstance(content, list):
            text_parts = [p['text'] if isinstance(p, dict) and 'text' in p else str(p) for p in content]
            content = " ".join(text_parts)
        
        content = str(content).strip() if content else ""
        
        # 2. Защита от пустоты
        if not content:
            if isinstance(m, ToolMessage):
                content = "Action success."
            elif isinstance(m, AIMessage) and hasattr(m, 'tool_calls') and m.tool_calls:
                content = "I'll do that."
            else:
                content = "..." # Минимальный заполнитель

        # 3. Пересборка
        if isinstance(m, HumanMessage):
            formatted_messages.append(HumanMessage(content=content))
        elif isinstance(m, AIMessage):
            t_calls = getattr(m, 'tool_calls', [])
            formatted_messages.append(AIMessage(content=content, tool_calls=t_calls))
        elif isinstance(m, ToolMessage):
            formatted_messages.append(ToolMessage(content=content, tool_call_id=m.tool_call_id))
    
    # Привязка инструментов
    if tools:
        llm = llm.bind_tools(tools)
    
    try:
        response = llm.invoke(formatted_messages)
        return {'messages': [response]}
    except Exception as e:
        error_str = str(e)
        # fallback для 'contents are required': отправляем только sys + last human
        if "contents are required" in error_str.lower() and len(formatted_messages) > 1:
            print(f"DEBUG: Falling back to minimal context for {model_name}...")
            # Пытаемся взять системный промпт и ПОСЛЕДНЕЕ сообщение от пользователя
            fallback_msgs = [formatted_messages[0], formatted_messages[-1]]
            response = llm.invoke(fallback_msgs)
            return {'messages': [response]}
        raise e

def tool_node(state: AgentState):
    from core.admin_tools import admin_tools
    from core.utils_obsidian import obsidian_capture_tool
    last_message = state['messages'][-1]
    tool_results = []
    if hasattr(last_message, 'tool_calls'):
        for tool_call in last_message.tool_calls:
            tool_name = tool_call['name']
            args = tool_call['args']
            if tool_name == 'get_docker_status': result = admin_tools.get_docker_status(**args)
            elif tool_name == 'check_connection': result = admin_tools.check_connection(**args)
            elif tool_name == 'run_remote_command': result = admin_tools.run_remote_command(**args)
            elif tool_name == 'obsidian_capture_tool': result = obsidian_capture_tool(**args)
            else: result = f"Error: Tool {tool_name} not found."
            
            # CRITICAL: Ensure tool output content is NOT empty
            tool_content = str(result) if result else "Success (no output)"
            if not tool_content.strip():
                tool_content = "Action completed."
                
            tool_results.append(ToolMessage(tool_call_id=tool_call['id'], content=tool_content))
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
    
    # Filter out or convert messages with empty content to prevent "contents are required" error
    for m in history_raw[-15:]:
        content = m['content']
        if not content or str(content).strip() == "":
            continue # Skip empty messages
        if m['role'] == 'user': 
            msgs.append(HumanMessage(content=str(content)))
        elif m['role'] == 'assistant': 
            # ВАЖНО: Если в базе сохранен JSON с tool_calls, восстанавливаем их для LangGraph
            ai_extra = {}
            if "tool_calls" in content and (content.startswith("[") or content.startswith("{")):
                try:
                    # Попытка распарсить, если мы когда-то сохраняли сырой JSON (на всякий случай)
                    calls = json.loads(content)
                    ai_extra["tool_calls"] = calls
                    content = "Executing tools..."
                except: pass
            msgs.append(AIMessage(content=str(content), **ai_extra))
    
    # Ensure at least one message is present or use the current clean_text
    if not msgs:
        msgs.append(HumanMessage(content=clean_text))
    
    # ПЕЧАТЬ ДЛЯ ДЕБАГА
    print(f"DEBUG: Processing message for {user_id}. Agent: {agent_type}. Model: {model_override}")
    print(f"DEBUG: Messages structure: {[(m.type, m.content) for m in msgs]}")
    
    inputs = {
        'messages': msgs, 
        'agent_type': agent_type, 
        'model_override': model_override, 
        'user_id': user_id
    }
    try:
        # Убеждаемся, что в inputs есть все необходимые ключи для узла
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
