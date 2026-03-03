import streamlit as st
import uuid
import os
import subprocess
from core.orchestrator import (
    process_message, 
    get_chat_history, 
    clear_chat_history, 
    AGENT_REGISTRY, 
    get_agent_model, 
    set_agent_model
)
from utils.audio_utils import text_to_speech

st.set_page_config(page_title='Antigravity Agents', layout='wide')

# ФИКС ИСТОРИИ: ИСПОЛЬЗУЕМ ПОСТОЯННЫЙ ID ВМЕСТО РАНДОМНОГО
if 'user_id' not in st.session_state:
    st.session_state.user_id = '207398589' # Тот самый ID, который есть в базе
if 'agent_key' not in st.session_state:
    st.session_state.agent_key = 'general'
if 'voice_enabled' not in st.session_state:
    st.session_state.voice_enabled = False

current_agent_key = st.session_state.agent_key
agent_list = list(AGENT_REGISTRY.keys())
active_index = agent_list.index(current_agent_key) + 1 

# CSS (Красные кнопки и Геометрия)
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
        overflow: hidden !important;
    }}
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:nth-of-type({active_index + 1}) button {{
        background-color: #a01a1a !important;
        color: white !important;
        border: 2px solid #801010 !important;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.2) !important;
    }}
    [data-testid="stSidebar"] button:hover p {{
        color: inherit !important;
    }}
    </style>
    """, unsafe_allow_html=True)

st.sidebar.title('🧠 Агенты')

# ОТРИСОВКА КНОПОК
for key, agent in AGENT_REGISTRY.items():
    if st.sidebar.button(agent['name'], key=f"btn_{key}"):
        st.session_state.agent_key = key
        st.rerun()

st.sidebar.divider()

# МОДЕЛИ
available_models = {
    'Автоматически': 'auto',
    'Groq (Llama 3.3)': 'llama-3.3-70b-versatile',
    'Gemini 3.0 Flash': 'gemini-3-flash-preview',
    'Gemini 3.1 Pro': 'gemini-3.1-pro-preview'
}

saved_val = get_agent_model(current_agent_key) or 'auto'
model_labels = list(available_models.keys())
model_values = list(available_models.values())

sel_label = st.sidebar.selectbox('Модель:', options=model_labels, index=model_values.index(saved_val) if saved_val in model_values else 0)

if available_models[sel_label] != saved_val:
    set_agent_model(current_agent_key, available_models[sel_label])
    st.rerun()

actual = available_models[sel_label]
if actual == 'auto': actual = AGENT_REGISTRY[current_agent_key]['default_model']

st.sidebar.info(f"Активна: {actual}")
st.sidebar.toggle('🔊 Голос', key='voice_enabled')

st.sidebar.divider()
if st.sidebar.button('🔄 Обновить базу данных'):
    with st.spinner('Индексация...'):
        cmd = 'python -c "from core.memory import index_directory; index_directory(r\'D:\\Users\\Lenovo\\Documents\\JobSearch\'); index_directory(r\'D:\\Users\\Lenovo\\Obsidian\')"'
        subprocess.run(cmd, shell=True)
        st.sidebar.success("Готово!")

with st.sidebar.expander("🛠 Отладка"):
    if st.button('🗑 Очистить историю'):
        if clear_chat_history(st.session_state.user_id, current_agent_key): st.rerun()

# ЧАТ (Восстановление истории)
history = get_chat_history(st.session_state.user_id)
# Фильтруем за все время для текущего агента
agent_history = [m for m in history if m.get('agent') == current_agent_key]

for msg in agent_history:
    with st.chat_message('user' if msg['role'] == 'user' else 'assistant'):
        st.markdown(msg['content'])

if prompt := st.chat_input('Сообщение...'):
    st.chat_message('user').markdown(prompt)
    with st.chat_message('assistant'):
        with st.spinner():
            resp = process_message(prompt, st.session_state.user_id, agent_type=current_agent_key)
            st.markdown(resp['text'])
            if st.session_state.voice_enabled:
                audio = text_to_speech(resp['text'], current_agent_key)
                if audio: st.audio(audio, format='audio/mp3')
