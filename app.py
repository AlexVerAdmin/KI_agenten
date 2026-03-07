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
    
    /* Стили для мягко удаленных сообщений */
    .deleted-message {{
        opacity: 0.5;
        font-style: italic;
        text-decoration: line-through;
    }}
    .soft-delete-btn button {{
        height: 24px !important;
        padding: 0 8px !important;
        font-size: 12px !important;
        min-height: 24px !important;
        margin-top: 5px !important;
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

# Настройки отображения корзины
show_deleted = st.sidebar.toggle('🗓 Показать удаленные (30д)', key='show_deleted')

st.sidebar.toggle('🔊 Голос', key='voice_enabled')

st.sidebar.divider()
if st.sidebar.button('🔄 Обновить базу данных'):
    with st.spinner('Индексация...'):
        # Предварительная очистка просроченных сообщений
        from core.orchestrator_v2 import cleanup_deleted_messages
        deleted_count = cleanup_deleted_messages()
        if deleted_count > 0:
            st.sidebar.info(f"🧹 Очищено старых сообщений: {deleted_count}")

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
history = get_chat_history_db(st.session_state.user_id, current_agent_key, include_deleted=st.session_state.get('show_deleted', False))

for msg in history:
    is_user = (msg['role'] == 'user')
    msg_id = msg.get('id')
    is_deleted = msg.get('deleted_at') is not None
    
    with st.chat_message('user' if is_user else 'assistant'):
        if is_deleted:
            st.markdown(f'<div class="deleted-message">{msg["content"]}</div>', unsafe_allow_html=True)
            st.caption("🗑 Сообщение удалено (хранится 30 дней)")
            if st.button("🔄 Восстановить", key=f"restore_{msg_id}"):
                from core.orchestrator_v2 import restore_message
                restore_message(msg_id)
                st.rerun()
        else:
            st.markdown(msg['content'])
        
        # --- HITL (Human-in-the-Loop) Кнопки подтверждения в ИСТОРИИ ---
        if not is_user:
            try:
                import re, json
                full_text = msg['content']
                # Ищем JSON список или отдельные объекты
                commands_to_show = []
                list_match = re.search(r'\[\s*\{.*\}\s*\]', full_text, re.DOTALL)
                if list_match:
                    try:
                        list_data = json.loads(list_match.group())
                        if isinstance(list_data, list):
                            for item in list_data:
                                cmd = item.get('command') or item.get('arguments', {}).get('command') or item.get('args', {}).get('command')
                                if cmd: commands_to_show.append(cmd)
                    except: pass
                
                if not commands_to_show:
                    json_matches = re.findall(r'\{[^{}]*\}', full_text, re.DOTALL)
                    for match_str in json_matches:
                        try:
                            data = json.loads(match_str)
                            cmd = data.get('command') or data.get('arguments', {}).get('command') or data.get('args', {}).get('command')
                            if cmd and cmd not in commands_to_show: commands_to_show.append(cmd)
                        except: continue

                if commands_to_show:
                    for idx, cmd in enumerate(commands_to_show):
                        with st.container(border=True):
                            st.write(f"**Команда #{idx+1}:** `{cmd}`")
                            c1, c2 = st.columns(2)
                            ts_key = msg.get('timestamp', 'now').replace(' ', '_').replace(':', '_')
                            with c1:
                                if st.button(f"✅ ВЫПОЛНИТЬ #{idx+1}", key=f"hist_confirm_{ts_key}_{idx}_{hash(cmd)}", use_container_width=True):
                                    from core.admin_tools import admin_tools
                                    with st.spinner("Выполняю..."):
                                        res = admin_tools.execute_confirmed_command(cmd)
                                        st.success("Готово!")
                                        st.code(res)
                                        save_message(st.session_state.user_id, current_agent_key, 'user', f"Результат выполнения {cmd}:\n{res}")
                                        st.rerun()
                            with c2:
                                if st.button(f"❌ ОТКЛОНИТЬ #{idx+1}", key=f"hist_reject_{ts_key}_{idx}_{hash(cmd)}", use_container_width=True):
                                    save_message(st.session_state.user_id, current_agent_key, 'user', f"Операция {cmd} отклонена.")
                                    st.rerun()
            except Exception as e:
                pass # Игнорируем ошибки отрисовки в истории

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
            
        c_meta, c_del = st.columns([10, 1])
        with c_meta:
            st.caption(f"👤 {display_name} {('| 🕒 ' + ts) if ts else ''}")
        with c_del:
            if not is_deleted:
                # Кнопка удаления в каждом сообщении (мягкое)
                if st.button("🗑", key=f"del_{msg_id}", help="Мягкое удаление (на 30 дней)"):
                    from core.orchestrator_v2 import soft_delete_message
                    soft_delete_message(msg_id)
                    st.rerun()

if prompt := st.chat_input('Сообщение...'):
    st.chat_message('user').markdown(prompt)
    with st.chat_message('assistant'):
        with st.spinner():
            resp = process_message(
                prompt, 
                st.session_state.user_id, 
                agent_type=current_agent_key,
                model_override=st.session_state.get('model_override')
            )
            
            # --- ВЫВОД ОТВЕТА АССИСТЕНТА ---
            full_text = resp['text']
            st.markdown(full_text)
            
            # --- НОВАЯ УЛЬТРА-АГРЕССИВНАЯ ЛОГИКА HITL КНОПОК ---
            import re, json
            
            # Список индикаторов, что модель хочет выполнить команду
            is_confirmation_request = (
                "pending_confirmation" in full_text or 
                "request_shell_execution" in full_text or
                "command" in full_text or
                "arguments" in full_text
            )
            
            if is_confirmation_request:
                try:
                    # УЛУЧШЕННЫЙ ПОИСК: Ищем все вхождения JSON структур
                    # Сначала пробуем найти список [...], если модель вернула его
                    list_match = re.search(r'\[\s*\{.*\}\s*\]', full_text, re.DOTALL)
                    commands_to_show = []
                    
                    if list_match:
                        try:
                            list_data = json.loads(list_match.group())
                            if isinstance(list_data, list):
                                for item in list_data:
                                    cmd = item.get('command') or item.get('arguments', {}).get('command') or item.get('args', {}).get('command')
                                    if cmd: commands_to_show.append(cmd)
                        except: pass
                    
                    # Если как список не распарсилось, ищем отдельные объекты { }
                    if not commands_to_show:
                        json_matches = re.findall(r'\{[^{}]*\}', full_text, re.DOTALL)
                        if json_matches:
                            for match_str in json_matches:
                                try:
                                    data = json.loads(match_str)
                                    cmd = data.get('command') or data.get('arguments', {}).get('command') or data.get('args', {}).get('command')
                                    if cmd: commands_to_show.append(cmd)
                                except: continue
                    
                    if commands_to_show:
                        st.subheader("🛠 Подтверждение команд")
                        for idx, cmd in enumerate(commands_to_show):
                            with st.container(border=True):
                                st.write(f"**Команда #{idx+1}:** `{cmd}`")
                                c1, c2 = st.columns(2)
                                with c1:
                                    if st.button(f"✅ ВЫПОЛНИТЬ #{idx+1}", key=f"force_confirm_{idx}_{hash(cmd)}", use_container_width=True):
                                        from core.admin_tools import admin_tools
                                        with st.spinner(f"Выполняю {cmd}..."):
                                            res = admin_tools.execute_confirmed_command(cmd)
                                            st.success("Готово!")
                                            st.code(res)
                                            # Сохраняем результат
                                            save_message(st.session_state.user_id, current_agent_key, 'user', f"Результат выполнения {cmd}:\n{res}")
                                            # Не делаем rerun сразу, чтобы дать нажать остальные кнопки, если их много
                                            # Но для обновления истории лучше сделать
                                            st.rerun()
                                with c2:
                                    if st.button(f"❌ ОТКЛОНИТЬ #{idx+1}", key=f"force_reject_{idx}_{hash(cmd)}", use_container_width=True):
                                        save_message(st.session_state.user_id, current_agent_key, 'user', f"Операция {cmd} отклонена.")
                                        st.rerun()
                    else:
                        st.warning("🤖 Модель предложила выполнить команду, но я не смог извлечь её параметры автоматически.")
                except Exception as hitl_err:
                    st.error(f"Ошибка HITL: {hitl_err}")

            agent_name = AGENT_REGISTRY.get(resp.get('active_node'), {}).get('name', 'Оркестратор')
            st.caption(f"👤 {agent_name} | 🕒 Только что")
            
            if st.session_state.voice_enabled:
                audio = text_to_speech(resp['text'], current_agent_key)
                if audio: st.audio(audio, format='audio/mp3')
