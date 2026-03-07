import sqlite3
import json
import logging
import os
from datetime import datetime
from typing import Annotated, TypedDict, List
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from config import config
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from core.utils_obsidian import obsidian

DB_PATH = 'memory_v2.sqlite'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT, agent_type TEXT, role TEXT, content TEXT, timestamp DATETIME)')
    cur.execute('CREATE TABLE IF NOT EXISTS agent_settings (agent_type TEXT PRIMARY KEY, model_name TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS summaries (user_id TEXT, agent_type TEXT, content TEXT, timestamp DATETIME, PRIMARY KEY (user_id, agent_type))')
    # Добавляем таблицу для хранения текущего выбранного агента пользователя (для ТГ)
    cur.execute('CREATE TABLE IF NOT EXISTS user_sessions (user_id TEXT PRIMARY KEY, last_agent TEXT, timestamp DATETIME)')
    conn.commit()
    conn.close()

def set_user_agent(user_id, agent_type):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO user_sessions (user_id, last_agent, timestamp) VALUES (?, ?, ?)', (user_id, agent_type, datetime.now()))
    conn.commit()
    conn.close()

def get_user_agent(user_id):
    if not isinstance(user_id, str): user_id = str(user_id)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT last_agent FROM user_sessions WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 'general'

def save_summary(user_id, agent_type, content):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    if not isinstance(content, str):
        content = str(content)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO summaries (user_id, agent_type, content, timestamp) VALUES (?, ?, ?, ?)', (user_id, agent_type, content, datetime.now()))
    conn.commit()
    conn.close()

def get_summary(user_id, agent_type):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT content FROM summaries WHERE user_id = ? AND agent_type = ?', (user_id, agent_type))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def save_message(user_id, agent_type, role, content):
    if not isinstance(user_id, str): user_id = str(user_id)
    if not isinstance(agent_type, str): agent_type = str(agent_type)
    if not isinstance(role, str): role = str(role)
    
    # logging.info(f"DEBUG: save_message called for {user_id}, role={role}. Content type: {type(content)}")
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
        except Exception as e:
            # logging.error(f"DEBUG: Error serializing content: {e}")
            content = "[Unserializable Content]"
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO chat_history (user_id, agent_type, role, content, timestamp) VALUES (?, ?, ?, ?, ?)', 
                    (user_id, agent_type, role, content, datetime.now()))
        conn.commit()
    except Exception as e:
        # logging.error(f"CRITICAL SQL ERROR in save_message: {e}. Content: {content[:100]}")
        raise e
    finally:
        conn.close()

def get_chat_history(user_id, agent_type=None):
    if not isinstance(user_id, str): user_id = str(user_id)
    if agent_type and not isinstance(agent_type, str): agent_type = str(agent_type)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if agent_type:
        cur.execute('SELECT role, content, agent_type, timestamp FROM chat_history WHERE user_id = ? AND agent_type = ? ORDER BY timestamp ASC', (user_id, agent_type))
    else:
        cur.execute('SELECT role, content, agent_type, timestamp FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{'role': r[0], 'content': r[1], 'agent': r[2], 'time': r[3]} for r in rows]

def set_agent_model(agent_type, model_name):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO agent_settings (agent_type, model_name) VALUES (?, ?)', (agent_type, model_name))
    conn.commit()
    conn.close()

def get_agent_model(agent_type):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT model_name FROM agent_settings WHERE agent_type = ?', (agent_type,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

init_db()

CHROMA_PATH = 'chroma_db'
_vectorstore = None

def get_embeddings():
    return GoogleGenerativeAIEmbeddings(model='models/gemini-embedding-001', google_api_key=config.google_api_key)

def get_vectorstore():
    global _vectorstore
    if _vectorstore is None and os.path.exists(CHROMA_PATH):
        try:
            embeddings = get_embeddings()
            _vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
        except Exception as e:
            logging.error(f"Error loading Chroma: {e}")
    return _vectorstore

def search_knowledge(query, k=2):
    vs = get_vectorstore()
    if not vs: return ''
    try:
        docs = vs.similarity_search(query, k=k)
        return '\n'.join([d.page_content for d in docs])
    except: return ''

AGENT_REGISTRY = {
    'general': {'name': '🤖 Помощник', 'default_model': 'llama-3.3-70b-versatile'},
    'german': {'name': '🇩🇪 Herr Max Klein', 'default_model': 'gemini-3-flash-preview'},
    'career': {'name': '💼 HR-Эксперт', 'default_model': 'gemini-3.1-pro-preview', 'can_access_obsidian': True},
    'finance': {'name': '💰 Финансовый консультант', 'default_model': 'llama-3.1-8b-instant', 'can_access_obsidian': True}
}

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    agent_type: str
    user_id: str

def get_model(agent_type):
    model_name = get_agent_model(agent_type) or AGENT_REGISTRY[agent_type]['default_model']
    if 'gemini' in model_name:
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=config.google_api_key, temperature=0.4, timeout=30, version="v1beta")
    return ChatGroq(model_name=model_name, api_key=config.groq_api_key, temperature=0.3)

def node_handler(state: AgentState):
    agent_type = state['agent_type']
    user_id = state.get('user_id', 'default_user')
    summary = get_summary(user_id, agent_type)
    
    llm = get_model(agent_type)
    
    # Реакция на Obsidian для German и других (добавляем инструменты)
    from core.utils_obsidian import obsidian_capture_tool
    tools = []
    if agent_type == 'german':
        tools = [obsidian_capture_tool]
    
    if tools:
        llm = llm.bind_tools(tools)

    last_msg = state['messages'][-1].content
    
    # Реакция на мысли и финансы (простой парсинг для начала)
    if agent_type == 'finance' and ('купил' in last_msg.lower() or 'потратил' in last_msg.lower()):
        # В реальности здесь нужен Tool Call, но для прототипа сделаем простой вызов
        obsidian.add_expense("Общее", "---", last_msg)
        return {'messages': [AIMessage(content="Я записал этот расход в ваш Obsidian.")]}
        
    if 'запиши мысль' in last_msg.lower() or 'впечатление:' in last_msg.lower():
        content = last_msg.replace('запиши мысль', '').replace('впечатление:', '').strip()
        obsidian.log_thought(content)
        return {'messages': [AIMessage(content="Ваша мысль бережно сохранена в Thoughts.md")]}

    ctx = search_knowledge(last_msg) if agent_type == 'career' else ''
    
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    prompts = {
        'german': (
            f'Ты Herr Max Klein, профессиональный учитель немецкого языка. Сегодня: {current_date}.\n'
            'ПРАВИЛА:\n'
            '1. ЕСЛИ УЧЕНИК ПЕРЕДАЕТ ТЕКСТ (на перевод или проверку): '
            'Проверь его на грамматику, лексику и пунктуацию. НЕ ДОПОЛНЯЙ текст своими мыслями.\n'
            '2. ДАВАЙ ОБРАТНУЮ СВЯЗЬ: Укажи на конкретные ошибки (например: "Хальдтих Кайт" -> "Nachhaltigkeit").\n'
            '3. СТИЛЬ: Говори как строгий, но дружелюбный учитель. Поясняй правила на русском.\n'
            '4. ЗАПРЕТ ГАЛЛЮЦИНАЦИЙ: Отвечай только на то, что слышишь. Не придумывай за ученика.'
        ),
        'career': f'Ты HR-Эксперт. Сегодня: {current_date}. Данные JobSearch:\n{ctx}\nИспользуй их для консультаций.',
        'finance': f'Ты Финансовый ассистент. Сегодня: {current_date}. Ты помогаешь вести расходы. Если пользователь говорит о тратах, ты должен их зафиксировать.',
        'general': f'Ты умный ИИ-помощник. Сегодня: {current_date}.'
    }
    
    system_content = prompts.get(agent_type, prompts['general'])
    if summary:
        system_content += f"\n\nКраткое содержание прошлых бесед:\n{summary}"
        
    msgs = [SystemMessage(content=system_content)] + state['messages']
    return {'messages': [llm.invoke(msgs)]}

workflow = StateGraph(AgentState)
workflow.add_node('agent', node_handler)

def tool_node(state: AgentState):
    from core.utils_obsidian import obsidian_capture_tool
    last_message = state['messages'][-1]
    tool_results = []
    if hasattr(last_message, 'tool_calls'):
        for tool_call in last_message.tool_calls:
            tool_name = tool_call['name']
            args = tool_call['args']
            if tool_name == 'obsidian_capture_tool':
                from core.utils_obsidian import obsidian
                result = obsidian.log_german_vocabulary(**args)
            else: result = f"Error: Tool {tool_name} not found."
            from langchain_core.messages import ToolMessage
            tool_results.append(ToolMessage(tool_call_id=tool_call['id'], content=str(result)))
    return {'messages': tool_results}

def should_continue(state: AgentState):
    last_message = state['messages'][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return 'tools'
    return END

workflow.add_node('tools', tool_node)
workflow.set_entry_point('agent')
workflow.add_conditional_edges('agent', should_continue)
workflow.add_edge('tools', 'agent')
app = workflow.compile()

def summarize_history(user_id, agent_type, msgs):
    """Сжимает историю чата, если она стала слишком длинной."""
    if len(msgs) < 10:
        return
        
    llm = ChatGroq(model_name="llama-3.3-70b-versatile", api_key=config.groq_api_key)
    summary_prompt = "Сделай краткое резюме (summary) этой переписки на русском языке. Выдели основные факты, прогресс в обучении или важные детали. Это резюме будет использоваться как контекст для следующего сообщения.\n\nПереписка:\n"
    for m in msgs:
        role = "Пользователь" if isinstance(m, HumanMessage) else "Ассистент"
        m_content = m.content
        if isinstance(m_content, list):
            m_content = "".join([part['text'] for part in m_content if isinstance(part, dict) and 'text' in part])
        summary_prompt += f"{role}: {m_content}\n"
        
    summary_res = llm.invoke([HumanMessage(content=summary_prompt)])
    save_summary(user_id, agent_type, summary_res.content)
    logging.info(f"Summary updated for {agent_type}")

def process_message(text, user_id, agent_type=None, thread_id=None, **kwargs):
    # --- МАППИНГ ТЕМ (Topics) В ТЕЛЕГРАМЕ ---
    topic_mapping = {
        2: "german",   # Учитель
        8: "career",   # Консультант/HR
        11: "finance"  # Финансы
    }
    
    # Если мы в группе и ID темы совпадает с маппингом - ПРИНУДИТЕЛЬНО меняем агента
    if thread_id in topic_mapping:
        agent_type = topic_mapping[thread_id]
        # Запоминаем выбор и для обычного чата, чтобы синхронизировать
        set_user_agent(user_id, agent_type)
    
    # Если agent_type не передан явно (из UI) и не определен темой, берем из сессии
    if agent_type is None:
        agent_type = get_user_agent(user_id)
        
    # --- СТРОГИЙ ПРЕФИКСНЫЙ ПЕРЕКЛЮЧАТЕЛЬ ---
    lower_text = text.lower()
    clean_text = text
    
    # 1. Сначала проверяем явные команды переключения (они меняют текущего агента сессии)
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
    
    # Если после очистки текст пустой, оставляем оригинал
    if not clean_text: clean_text = text

    # Предотвращаем дублирование истории между агентами.
    save_message(user_id, agent_type, 'user', clean_text)
    history = get_chat_history(user_id, agent_type)
    
    # Собираем историю (последние 10 сообщений для контекста ИМЕННО ЭТОГО агента)
    all_msgs = []
    for m in history:
        if m['role'] == 'user': 
            all_msgs.append(HumanMessage(content=m['content']))
        else: 
            all_msgs.append(AIMessage(content=m['content']))
    
    # Если история выросла, обновляем Саммари (раз в 15 сообщений)
    if len(all_msgs) > 15 and len(all_msgs) % 5 == 0:
        summarize_history(user_id, agent_type, all_msgs[:-5])
        
    # Передаем только актуальное окно (8 сообщений) + Саммари (через ноду)
    context_window = all_msgs[-8:]
    
    # ПРЯМО ПЕРЕДАЕМ agent_type в состояние графа
    res = app.invoke({'messages': context_window, 'agent_type': agent_type, 'user_id': user_id}, 
                     config={"configurable": {"thread_id": f"{user_id}_{agent_type}"}, "recursion_limit": 50})
    
    ai_msg = res['messages'][-1]
    ai_text = ai_msg.content
    
    # Обработка разных форматов Gemini (как в orchestrator_v2)
    if isinstance(ai_text, list):
        text_parts = [part['text'] for part in ai_text if isinstance(part, dict) and 'text' in part]
        ai_text = "".join(text_parts)
    elif not isinstance(ai_text, str):
        ai_text = str(ai_text)

    save_message(user_id, agent_type, 'assistant', ai_text)
    return {'text': ai_text, 'active_node': agent_type}

def clear_chat_history(uid, ag):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute('DELETE FROM chat_history WHERE user_id = ? AND agent_type = ?', (uid, ag))
    conn.commit()
    conn.close()
    return True
