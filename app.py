import streamlit as st
import uuid
import os
import subprocess

# Ленивый импорт тяжелых модулей
def get_orchestrator():
    from core.orchestrator_v2 import (
        process_message, 
        get_chat_history_db, 
        clear_chat_history, 
        AGENT_REGISTRY,
        is_ollama_online,
        get_agent_setting, 
        save_agent_setting
    )
    return (process_message, get_chat_history_db, clear_chat_history, 
            AGENT_REGISTRY, is_ollama_online, get_agent_setting, save_agent_setting)

# КЭШИРОВАНИЕ ДЛЯ УСКОРЕНИЯ ЗАГРУЗКИ
@st.cache_resource
def init_system():
    from core.orchestrator_v2 import app as langgraph_app
    from core.utils_obsidian import obsidian as obs_manager
    return langgraph_app, obs_manager

# Быстрый старт (теперь только кеш, без тяжелых импортов в глобальной области)
app_engine, obsidian_engine = init_system()
(process_message, get_chat_history_db, clear_chat_history, 
 AGENT_REGISTRY, is_ollama_online, get_agent_setting, save_agent_setting) = get_orchestrator()

from utils.audio_utils import text_to_speech

st.set_page_config(page_title='Personal Agents', layout='wide')

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
    /* Универсальный селектор: подсвечиваем кнопку, если в её тексте есть имя активного агента */
    [data-testid="stSidebar"] button div p:contains("{AGENT_REGISTRY[current_agent_key]['name']}") {{
        background-color: #a01a1a !important;
        color: white !important;
    }}
    /* Запасной вариант через data-testid и порядковый номер, но с поиском внутри блока кнопок */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] button:has(div p:contains("{AGENT_REGISTRY[current_agent_key]['name']}")) {{
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
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-of-type({active_index + 1}) button {{
        background-color: #a01a1a !important;
        color: white !important;
        border: 2px solid #801010 !important;
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
from core.orchestrator_v2 import get_agent_setting, save_agent_setting

# Список доступных моделей для выбора
MODEL_OPTIONS = {
    'gemini-3.1-pro-preview': '🏆 Gemini 3.1 Pro (Preview)',
    'gemini-3-flash-preview': '🚀 Gemini 3 Flash (Preview)',
    'gemini-2.5-pro': '💎 Gemini 2.5 Pro (Stable)',
    'gemini-2.5-flash': '⚡ Gemini 2.5 Flash (Stable)',
    'gemini-2.0-flash': '🚀 Gemini 2.0 Flash',
    'llama-3.3-70b-versatile': '🦙 Llama 3.3 70B (Groq)',
    'llama-3.1-70b-versatile': '🦙 Llama 3.1 70B (Groq)',
    'ollama/llama3.1:8b': '🏠 Llama 3.1 8B (Local GPU)',
    'ollama/mistral-nemo:12b': '🏠 Mistral Nemo 12B (Local GPU)',
    'ollama/qwen2.5:14b': '🏠 Qwen 2.5 14B (Local GPU)'
}

# Загружаем сохраненную модель для текущего агента
saved_model = get_agent_setting(st.session_state.user_id, current_agent_key, 'selected_model')
model_keys = list(MODEL_OPTIONS.keys())

# Определяем индекс для отображения в селектбоксе
if saved_model in model_keys:
    default_index = model_keys.index(saved_model)
else:
    # Дефолтные значения если ничего не сохранено
    if current_agent_key == 'german': default_index = model_keys.index('gemini-3.1-pro-preview')
    elif current_agent_key in ['vds_admin', 'local_admin']: default_index = model_keys.index('ollama/llama3.1:8b')
    else: default_index = model_keys.index('llama-3.3-70b-versatile')

selected_model_label = st.sidebar.selectbox(
    "Выбор модели:",
    options=model_keys,
    format_func=lambda x: MODEL_OPTIONS[x],
    index=default_index
)

# Сохраняем выбор в session_state и БД
st.session_state.model_override = selected_model_label
if selected_model_label != saved_model:
    save_agent_setting(st.session_state.user_id, current_agent_key, 'selected_model', selected_model_label)

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
        
        # --- HITL (Human-in-the-Loop) Кнопки подтверждения ---
        if not is_user and "pending_confirmation" in msg['content']:
            try:
                # Извлекаем данные из сообщения (оно сохранено как строка-json или содержит его)
                import re, json
                match = re.search(r'\{.*"status":\s*"pending_confirmation".*\}', msg['content'], re.DOTALL)
                if match:
                    tool_data = json.loads(match.group())
                    cmd = tool_data.get('command')
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Разрешить", key=f"confirm_{msg.get('timestamp')}_{hash(cmd)}"):
                            from core.admin_tools import admin_tools
                            with st.spinner("Выполнение..."):
                                result = admin_tools.execute_confirmed_command(cmd)
                                st.info(result)
                                # Сохраняем результат в историю, чтобы агент его увидел
                                save_message(st.session_state.user_id, current_agent_key, 'user', f"Результат выполнения {cmd}:\n{result}")
                                st.rerun()
                    with col2:
                        if st.button("❌ Отклонить", key=f"reject_{msg.get('timestamp')}_{hash(cmd)}"):
                            save_message(st.session_state.user_id, current_agent_key, 'user', "Операция отклонена пользователем.")
                            st.rerun()
            except Exception as e:
                st.error(f"Ошибка отрисовки кнопок: {e}")

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
