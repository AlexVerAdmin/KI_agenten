import streamlit as st
import uuid
import os
import subprocess
# Переключаемся на v2 оркестратор для поддержки инструментов Obsidian и правильной БД
from core.orchestrator_v2 import (
    process_message, 
    get_chat_history_db, 
    clear_chat_history, 
    AGENT_REGISTRY,
    is_ollama_online
)
from utils.audio_utils import text_to_speech

# КЭШИРОВАНИЕ ДЛЯ УСКОРЕНИЯ ЗАГРУЗКИ
@st.cache_resource
def init_system():
    from core.orchestrator_v2 import app as langgraph_app
    from core.utils_obsidian import obsidian as obs_manager
    return langgraph_app, obs_manager

# Быстрый старт
app_engine, obsidian_engine = init_system()

st.set_page_config(page_title='Antigravity Agents', layout='wide')

# ФИКС ИСТОРИИ
if 'user_id' not in st.session_state:
    st.session_state.user_id = '207398589'
if 'agent_key' not in st.session_state:
    st.session_state.agent_key = 'general'
if 'voice_enabled' not in st.session_state:
    st.session_state.voice_enabled = False

current_agent_key = st.session_state.agent_key
agent_list = list(AGENT_REGISTRY.keys())
active_index = agent_list.index(current_agent_key) + 1 

# CSS (Telegram-style Bubbles)
st.markdown(f"""
    <style>
    [data-testid="stSidebar"] [data-testid="stElementContainer"] {{
        width: 100% !important;
        display: block !important;
        margin: 0 !important;
        padding: 0 !important;
    }}
    [data-testid="stSidebar"] button {{
        width: 100% !important;
        min-width: 100% !important;
        max-width: 100% !important;
        height: 60px !important;
        background-color: #f0f2f6 !important;
        border: 1px solid #d1d5db !important;
        color: #1f2937 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        margin-bottom: 15px !important;
        display: block !important;
    }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-of-type({active_index + 1}) button {{
        background-color: #a01a1a !important;
        color: white !important;
        border: 2px solid #801010 !important;
    }}
    
    /* Стили пузырьков */
    [data-testid="stChatMessage"] {{
        border-radius: 18px !important;
        padding: 12px !important;
        margin-bottom: 8px !important;
        width: fit-content !important;
        max-width: 80% !important;
        display: flex !important;
    }}
    
    /* Сообщение пользователя - СМЕЩЕНИЕ ВПРАВО */
    [data-testid="stChatMessageUser"] {{
        background-color: #dcf8c6 !important;
        margin-left: auto !important;
        border-bottom-right-radius: 2px !important;
        flex-direction: row-reverse !important;
    }}
    [data-testid="stChatMessageUser"] .stMarkdown p {{
        color: #111111 !important;
        text-align: right !important;
    }}
    [data-testid="stChatMessageUser"] .stCaption {{
        text-align: right !important;
        width: 100% !important;
    }}
    
    /* Сообщение ассистента - СМЕЩЕНИЕ ВЛЕВО */
    [data-testid="stChatMessageAssistant"] {{
        background-color: #ffffff !important;
        border: 1px solid #e0e0e0 !important;
        margin-right: auto !important;
        border-bottom-left-radius: 2px !important;
    }}
    [data-testid="stChatMessageAssistant"] .stMarkdown p {{
        color: #111111 !important;
        text-align: left !important;
    }}

    /* Поддержка темной темы Streamlit */
    @media (prefers-color-scheme: dark) {{
        [data-testid="stChatMessageUser"] {{
            background-color: #056162 !important;
        }}
        [data-testid="stChatMessageUser"] .stMarkdown p {{
            color: #ffffff !important;
        }}
        [data-testid="stChatMessageAssistant"] {{
            background-color: #262d31 !important;
            border: 1px solid #3b4a54 !important;
        }}
        [data-testid="stChatMessageAssistant"] .stMarkdown p {{
            color: #eeeeee !important;
        }}
    }}
    
    /* Убираем лишние отступы контейнеров чата для чистого смещения */
    [data-testid="column"] > div > div > div > div.stChatMessage {{
        width: 100% !important;
    }}
    </style>
    """, unsafe_allow_html=True)

st.sidebar.title('🧠 Агенты')

for key, agent in AGENT_REGISTRY.items():
    if st.sidebar.button(agent['name'], key=f"btn_{key}"):
        st.session_state.agent_key = key
        st.rerun()

st.sidebar.divider()
st.sidebar.info(f"👤 Активен: {AGENT_REGISTRY[current_agent_key]['name']}")

# ВЫБОР МОДЕЛИ (Model Override)
MODEL_OPTIONS = {
    'gemini-2.5-pro': '💎 Gemini 2.5 Pro',
    'gemini-2.5-flash': '⚡ Gemini 2.5 Flash',
    'llama-3.3-70b-versatile': '🦙 Llama 3.3 70B (Groq)'
}

selected_model_label = st.sidebar.selectbox(
    "Выбор модели:",
    options=list(MODEL_OPTIONS.keys()),
    format_func=lambda x: MODEL_OPTIONS[x],
    index=1 if current_agent_key == 'german' else 0 # По умолчанию Flash для учителя (безопасно)
)
st.session_state.model_override = selected_model_label

# Мониторинг локального сервера
ollama_status = is_ollama_online()
if ollama_status:
    st.sidebar.success("🟢 Local GPU Нода: ONLINE")
else:
    st.sidebar.error("🔴 Local GPU Нода: OFFLINE")

st.sidebar.toggle('🔊 Голос', key='voice_enabled')

st.sidebar.divider()
if st.sidebar.button('🔄 Обновить базу данных'):
    with st.spinner('Индексация...'):
        # Используем пути из config, которые могут переопределяться через .env или ENV (Docker)
        from config import config
        from core.memory import index_directory
        
        # Индексируем по одному, чтобы избежать проблем с кавычками в subprocess
        if config.job_search_path and os.path.exists(config.job_search_path):
            index_directory(config.job_search_path)
            st.sidebar.info(f"💼 Карьера: {os.path.basename(config.job_search_path)} - OK")
            
        if config.obsidian_vault_path and os.path.exists(config.obsidian_vault_path):
            index_directory(config.obsidian_vault_path)
            st.sidebar.info(f"📓 Obsidian: {os.path.basename(config.obsidian_vault_path)} - OK")
            
        st.sidebar.success("База данных обновлена!")

with st.sidebar.expander("🛠 Отладка"):
    if st.button('🗑 Очистить историю'):
        if clear_chat_history(st.session_state.user_id, current_agent_key): st.rerun()

# ЧАТ
history = get_chat_history_db(st.session_state.user_id, current_agent_key)

for msg in history:
    is_user = (msg['role'] == 'user')
    with st.chat_message('user' if is_user else 'assistant'):
        st.markdown(msg['content'])
        
        # Исправляем отображение имен и времени
        display_name = "Вы" if is_user else AGENT_REGISTRY.get(msg['agent'], {}).get('name', 'Оркестратор')
        
        # Получаем время из кортежа или словаря (зависит от того как sqlite возвращает данные)
        # В нашем случае get_chat_history_db возвращает список словарей
        # {'role': r[0], 'content': r[1], 'agent': r[2]} - ОЙ, в orchestrator_v2.py не возвращается timestamp!
        ts_val = msg.get('timestamp', 'Неизвестно')
        if ts_val and ts_val != 'Неизвестно':
            ts = str(ts_val).split('.')[0]
        else:
            ts = ""
            
        st.caption(f"👤 {display_name} {('| 🕒 ' + ts) if ts else ''}")

if prompt := st.chat_input('Сообщение...'):
    st.chat_message('user').markdown(prompt)
    with st.chat_message('assistant'):
        with st.spinner():
            # Передаем выбранную модель в процесс обработки сообщения
            resp = process_message(
                prompt, 
                st.session_state.user_id, 
                agent_type=current_agent_key,
                model_override=st.session_state.get('model_override')
            )
            st.markdown(resp['text'])
            agent_name = AGENT_REGISTRY.get(resp.get('active_node'), {}).get('name', 'Оркестратор')
            st.caption(f"👤 {agent_name} | 🕒 Только что")
            
            if st.session_state.voice_enabled:
                audio = text_to_speech(resp['text'], current_agent_key)
                if audio: st.audio(audio, format='audio/mp3')
