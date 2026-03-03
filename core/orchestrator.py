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

DB_PATH = 'memory_v2.sqlite'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT, agent_type TEXT, role TEXT, content TEXT, timestamp DATETIME)')
    cur.execute('CREATE TABLE IF NOT EXISTS agent_settings (agent_type TEXT PRIMARY KEY, model_name TEXT)')
    conn.commit()
    conn.close()

def save_message(user_id, agent_type, role, content):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('INSERT INTO chat_history (user_id, agent_type, role, content, timestamp) VALUES (?, ?, ?, ?, ?)', (user_id, agent_type, role, content, datetime.now()))
    conn.commit()
    conn.close()

def get_chat_history(user_id, agent_type=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if agent_type:
        cur.execute('SELECT role, content, agent_type FROM chat_history WHERE user_id = ? AND agent_type = ? ORDER BY timestamp ASC', (user_id, agent_type))
    else:
        cur.execute('SELECT role, content, agent_type FROM chat_history WHERE user_id = ? ORDER BY timestamp ASC', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [{'role': r[0], 'content': r[1], 'agent': r[2]} for r in rows]

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
def get_vectorstore():
    global _vectorstore
    if _vectorstore is None and os.path.exists(CHROMA_PATH):
        try:
            embeddings = GoogleGenerativeAIEmbeddings(model='models/gemini-embedding-001', google_api_key=config.google_api_key)
            _vectorstore = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
        except: pass
    return _vectorstore

def search_knowledge(query, k=2):
    vs = get_vectorstore()
    if not vs: return ''
    try:
        docs = vs.similarity_search(query, k=k)
        return '\n'.join([d.page_content for d in docs])
    except: return ''

AGENT_REGISTRY = {
    'general': {'name': 'Общий ассистент', 'default_model': 'llama-3.3-70b-versatile'},
    'german': {'name': 'Herr Max Klein', 'default_model': 'gemini-3-flash-preview'},
    'career': {'name': 'HR-Эксперт', 'default_model': 'gemini-3.1-pro-preview'}
}

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    agent_type: str

def get_model(agent_type):
    model_name = get_agent_model(agent_type) or AGENT_REGISTRY[agent_type]['default_model']
    if 'gemini' in model_name:
        return ChatGoogleGenerativeAI(model=model_name, google_api_key=config.google_api_key, temperature=0.4, timeout=30)
    return ChatGroq(model_name=model_name, api_key=config.groq_api_key, temperature=0.3)

def node_handler(state: AgentState):
    agent_type = state['agent_type']
    llm = get_model(agent_type)
    last_msg = state['messages'][-1].content
    ctx = search_knowledge(last_msg) if agent_type == 'career' else ''
    prompts = {
        'german': 'Ты Herr Max Klein, учитель немецкого. Отвечай на немецком, поясняй на русском.',
        'career': f'Ты HR-Эксперт. Данные JobSearch:\n{ctx}\nИспользуй их.',
        'general': 'Ты умный ИИ-помощник (мощный Groq).'
    }
    msgs = [SystemMessage(content=prompts.get(agent_type, prompts['general']))] + state['messages']
    return {'messages': [llm.invoke(msgs)]}

workflow = StateGraph(AgentState)
workflow.add_node('agent', node_handler)
workflow.set_entry_point('agent')
workflow.add_edge('agent', END)
app = workflow.compile()

def process_message(text, user_id, agent_type='general', **kwargs):
    save_message(user_id, agent_type, 'user', text)
    history = get_chat_history(user_id, agent_type)
    msgs = []
    for m in history[-8:]:
        if m['role'] == 'user': msgs.append(HumanMessage(content=m['content']))
        else: msgs.append(AIMessage(content=m['content']))
    res = app.invoke({'messages': msgs, 'agent_type': agent_type})
    ai_text = res['messages'][-1].content
    save_message(user_id, agent_type, 'assistant', ai_text)
    return {'text': ai_text, 'active_node': agent_type}

def clear_chat_history(uid, ag):
    conn = sqlite3.connect(DB_PATH)
    conn.cursor().execute('DELETE FROM chat_history WHERE user_id = ? AND agent_type = ?', (uid, ag))
    conn.commit()
    conn.close()
    return True
