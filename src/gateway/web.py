"""
Web UI: FastAPI + WebSocket + HTML.
Маршруты:
  GET  /             → HTML страница (чат)
  GET  /audio/{file} → отдаёт .mp3 файл
  WS   /ws/{agent}   → WebSocket чат с агентом
  GET  /api/history/{agent} → история сообщений (JSON)
"""

import os
import asyncio
import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="Antigravity Agents")

# Импортируем агентов чтобы они зарегистрировались в router
import src.agents.tutor    # noqa: F401
import src.agents.career   # noqa: F401
import src.agents.copilot  # noqa: F401

from src.gateway.router import process, AGENT_LABELS
from src.db.conversations import get_recent_messages, delete_message
from src.config import (
    AVAILABLE_MODELS, TTS_MODELS, AGENT_DEFAULTS, UI_LANGUAGES,
    get_effective_settings, save_global_settings, save_user_setting, reset_user_setting,
    get_agent_model, set_agent_model,
)

AUDIO_DIR = "/tmp/tutor_audio"


# ─── Страница настроек /settings ────────────────────────────────────────────

SETTINGS_HTML = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Налаштування агентів</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e0e0e0; padding: 24px; max-width: 860px; margin: 0 auto; }
  h1 { font-size: 20px; color: #fff; margin-bottom: 6px; }
  .subtitle { color: #666; font-size: 13px; margin-bottom: 28px; }
  .subtitle a { color: #6b8cff; text-decoration: none; }

  .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid #2a2a2a;
          padding-bottom: 0; flex-wrap: wrap; }
  .tab-btn { padding: 8px 18px; border: none; background: none; color: #888; cursor: pointer;
             font-size: 14px; border-bottom: 2px solid transparent; margin-bottom: -1px;
             transition: color 0.15s; }
  .tab-btn:hover { color: #ccc; }
  .tab-btn.active { color: #fff; border-bottom-color: #6b8cff; }

  .tab-pane { display: none; }
  .tab-pane.active { display: block; }

  .section { margin-bottom: 24px; }
  .section-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1px;
                   color: #666; margin-bottom: 12px; }

  .field { margin-bottom: 16px; }
  label { display: block; font-size: 13px; color: #aaa; margin-bottom: 5px; }
  .field-row { display: flex; gap: 8px; align-items: flex-start; }
  input[type=text], input[type=number], select, textarea {
    background: #1a1a1a; border: 1px solid #333; color: #e0e0e0;
    padding: 8px 12px; border-radius: 6px; font-size: 14px; outline: none;
    width: 100%; font-family: inherit; }
  input:focus, select:focus, textarea:focus { border-color: #6b8cff; }
  textarea { resize: vertical; min-height: 120px; line-height: 1.5; }
  input[type=number] { max-width: 120px; }
  select { max-width: 320px; }

  .row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 600px) { .row-2 { grid-template-columns: 1fr; } }

  .reset-btn { padding: 7px 10px; background: none; border: 1px solid #444; color: #888;
               border-radius: 6px; cursor: pointer; font-size: 12px; white-space: nowrap;
               transition: all 0.15s; flex-shrink: 0; }
  .reset-btn:hover { border-color: #e05555; color: #e05555; }

  .save-btn { padding: 10px 24px; background: #4a6adf; color: #fff; border: none;
              border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500;
              transition: background 0.15s; }
  .save-btn:hover { background: #5a7aef; }
  .save-btn:disabled { background: #333; color: #666; cursor: not-allowed; }
  .save-btn.user { background: #2a6a4a; }
  .save-btn.user:hover { background: #3a8a5a; }
  .save-actions { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-top: 8px; }

  .info { font-size: 12px; color: #555; margin-top: 4px; }
  .badge-global { font-size: 10px; background: #1a3a2a; color: #5aba8a;
                  padding: 1px 7px; border-radius: 8px; margin-left: 6px; }
  .badge-user   { font-size: 10px; background: #3a2a1a; color: #dfaa5a;
                  padding: 1px 7px; border-radius: 8px; margin-left: 6px; }

  .toast { position: fixed; bottom: 24px; right: 24px; background: #1e3a1e;
           border: 1px solid #3a7a3a; color: #7ada7a; padding: 10px 18px;
           border-radius: 8px; font-size: 14px; opacity: 0;
           transition: opacity 0.3s; pointer-events: none; z-index: 999; }
  .toast.show { opacity: 1; }
  .toast.error { background: #3a1e1e; border-color: #7a3a3a; color: #da7a7a; }
</style>
</head>
<body>
<h1>⚙️ Налаштування агентів</h1>
<p class="subtitle">
  Глобальні налаштування (для всіх користувачів). Per-user overrides зберігаються окремо.<br>
  <a href="/">← Повернутись до чату</a>
</p>

<div class="tabs" id="tabs"></div>
<div id="panes"></div>

<div class="toast" id="toast"></div>

<script>
const AGENTS_INFO = {
  tutor:   { label: "Lehrer (Вчитель)", hasTts: true },
  career:  { label: "Career Coach",     hasTts: false },
  copilot: { label: "Copilot",          hasTts: false },
};

let models = {};
let ttsModels = {};
let uiLangs = {};
let agentSettings = {};  // agent → current effective settings

async function init() {
  [models, ttsModels, uiLangs] = await Promise.all([
    fetch('/api/models').then(r => r.json()),
    fetch('/api/tts-models').then(r => r.json()),
    fetch('/api/ui-languages').then(r => r.json()),
  ]);

  const tabs  = document.getElementById('tabs');
  const panes = document.getElementById('panes');

  for (const [agent, info] of Object.entries(AGENTS_INFO)) {
    const settings = await fetch(`/api/settings/${agent}`).then(r => r.json());
    agentSettings[agent] = settings;

    // Tab
    const btn = document.createElement('button');
    btn.className = 'tab-btn';
    btn.textContent = info.label;
    btn.dataset.agent = agent;
    btn.onclick = () => switchTab(agent);
    tabs.appendChild(btn);

    // Pane
    const pane = document.createElement('div');
    pane.className = 'tab-pane';
    pane.id = `pane-${agent}`;
    pane.innerHTML = buildPane(agent, info, settings);
    panes.appendChild(pane);
  }

  switchTab('tutor');
}

function buildPane(agent, info, s) {
  const modelOpts = Object.entries(models).map(([v, n]) =>
    `<option value="${v}" ${v === s.model ? 'selected' : ''}>${n}</option>`
  ).join('');

  const ttsVoices = ['Fenrir', 'Aoede', 'Charon', 'Kore', 'Puck', 'Leda', 'Orus', 'Schedar'];
  const ttsVoiceOpts = ttsVoices.map(v =>
    `<option value="${v}" ${v === (s.tts_voice || 'Fenrir') ? 'selected' : ''}>${v}</option>`
  ).join('');

  const ttsLangs = {'de-DE':'🇩🇪 Deutsch','uk-UA':'🇺🇦 Українська','en-US':'🇺🇸 English',
                    'ru-RU':'🇷🇺 Русский','pt-PT':'🇵🇹 Português'};
  const ttsLangOpts = Object.entries(ttsLangs).map(([v, n]) =>
    `<option value="${v}" ${v === (s.tts_lang || 'de-DE') ? 'selected' : ''}>${n}</option>`
  ).join('');

  const uiLangOpts = Object.entries(uiLangs).map(([v, n]) =>
    `<option value="${v}" ${v === (s.ui_lang || 'uk') ? 'selected' : ''}>${n}</option>`
  ).join('');

  const ttsSection = info.hasTts ? `
    <div class="section">
      <div class="section-title">TTS (синтез мовлення)</div>
      <div class="row-2">
        <div class="field">
          <label>Голос <span class="badge-global">global</span></label>
          <select id="${agent}-tts_voice">${ttsVoiceOpts}</select>
        </div>
        <div class="field">
          <label>Мова озвучування <span class="badge-global">global</span></label>
          <select id="${agent}-tts_lang">${ttsLangOpts}</select>
        </div>
      </div>
    </div>` : '';

  return `
    <div class="section">
      <div class="section-title">Модель та параметри</div>
      <div class="row-2">
        <div class="field">
          <label>Модель <span class="badge-global">global</span></label>
          <select id="${agent}-model">${modelOpts}</select>
        </div>
        <div class="field">
          <label>Мова інтерфейсу <span class="badge-global">global</span></label>
          <select id="${agent}-ui_lang">${uiLangOpts}</select>
        </div>
      </div>
      <div class="row-2">
        <div class="field">
          <label>Temperature</label>
          <input type="number" id="${agent}-temperature" value="${s.temperature ?? 0.7}"
                 min="0" max="2" step="0.1">
          <div class="info">0 = детерміновано, 1+ = творчо</div>
        </div>
        <div class="field">
          <label>Max tokens</label>
          <input type="number" id="${agent}-max_tokens" value="${s.max_tokens ?? 8192}"
                 min="256" max="65536" step="256">
        </div>
      </div>
    </div>
    ${ttsSection}
    <div class="section">
      <div class="section-title">Системний промпт <span class="badge-global">global</span></div>
      <div class="field">
        <textarea id="${agent}-system_prompt" rows="8">${escHtml(s.system_prompt || '')}</textarea>
        <div class="info">Це "особистість" агента. Кожен користувач може змінити під себе через особисті налаштування.</div>
      </div>
    </div>
    <div class="save-actions">
      <button class="save-btn" onclick="saveGlobal('${agent}')">💾 Зберегти глобально</button>
      <button class="save-btn user" onclick="saveForMe('${agent}')">👤 Зберегти для мене</button>
    </div>
    <div style="margin-top:8px; font-size:12px; color:#555;">
      <b>Глобально</b> — базові налаштування для всіх. <b>Для мене</b> — тільки твій override (поля: модель, промпт, голос TTS, мова UI).
    </div>
  `;
}

function switchTab(agent) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-agent="${agent}"]`).classList.add('active');
  document.getElementById(`pane-${agent}`).classList.add('active');
}

async function saveGlobal(agent) {
  const fields = ['model', 'system_prompt', 'temperature', 'max_tokens', 'tts_voice', 'tts_lang', 'ui_lang'];
  const body = {};
  for (const f of fields) {
    const el = document.getElementById(`${agent}-${f}`);
    if (!el) continue;
    body[f] = el.type === 'number' ? parseFloat(el.value) : el.value;
  }
  const res = await fetch(`/api/settings/${agent}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (data.ok) showToast('Збережено глобально ✓');
  else showToast('Помилка: ' + (data.error || '?'), true);
}

async function saveForMe(agent) {
  // тільки USER_OVERRIDABLE_FIELDS: model, system_prompt, tts_voice, tts_lang, ui_lang
  const fields = ['model', 'system_prompt', 'tts_voice', 'tts_lang', 'ui_lang'];
  const body = {};
  for (const f of fields) {
    const el = document.getElementById(`${agent}-${f}`);
    if (!el) continue;
    body[f] = el.value;
  }
  const res = await fetch(`/api/user-settings/${agent}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (data.ok) showToast('Збережено для тебе ✓');
  else showToast('Помилка: ' + (data.error || '?'), true);
}

function showToast(msg, isError = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' error' : '');
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function escHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

init();
</script>
</body>
</html>
"""


# ─── HTML страница ──────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Antigravity Agents</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e0e0e0; display: flex; height: 100vh; }

  /* Sidebar */
  #sidebar { width: 220px; background: #1a1a1a; border-right: 1px solid #2a2a2a;
             display: flex; flex-direction: column; padding: 16px 0; flex-shrink: 0; }
  #sidebar h2 { color: #888; font-size: 11px; text-transform: uppercase;
                letter-spacing: 1px; padding: 0 16px 12px; }
  .agent-btn { padding: 10px 16px; cursor: pointer; border: none; background: none;
               color: #ccc; text-align: left; width: 100%; font-size: 14px;
               border-radius: 0; transition: background 0.15s; }
  .agent-btn:hover { background: #2a2a2a; }
  .agent-btn.active { background: #2a2a3a; color: #fff; border-left: 2px solid #6b8cff; }

  /* Chat area */
  #chat-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  #chat-header { padding: 16px 20px; border-bottom: 1px solid #2a2a2a;
                 font-size: 16px; font-weight: 600; color: #fff; background: #141414; }
  #messages { flex: 1; overflow-y: auto; padding: 20px;
              display: flex; flex-direction: column; gap: 12px; }

  /* Messages */
  .msg { max-width: 72%; padding: 10px 14px; border-radius: 12px; line-height: 1.5;
         font-size: 14px; word-break: break-word; }
  .msg.user { background: #2a3a5a; align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.assistant { background: #1e2a1e; align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg .meta { font-size: 11px; color: #666; margin-top: 4px; }
  .msg audio { display: block; margin-top: 8px; width: 100%; max-width: 280px; }

  /* Input */
  #input-area { padding: 16px 20px; border-top: 1px solid #2a2a2a; background: #141414;
                display: flex; gap: 10px; align-items: center; }
  #msg-input { flex: 1; background: #222; border: 1px solid #333; color: #e0e0e0;
               padding: 10px 14px; border-radius: 8px; font-size: 14px; outline: none;
               resize: none; max-height: 120px; }
  #msg-input:focus { border-color: #6b8cff; }
  #send-btn { background: #4a6adf; color: white; border: none; padding: 10px 18px;
              border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500;
              transition: background 0.15s; white-space: nowrap; }
  #send-btn:hover { background: #5a7aef; }
  #send-btn:disabled { background: #333; color: #666; cursor: not-allowed; }

  /* Typing indicator */
  .typing { color: #666; font-size: 13px; font-style: italic; padding: 4px 0; }

  /* Source badge */
  .badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; margin-left: 6px;
           background: #333; color: #888; }
  .badge.telegram { background: #1a3a5a; color: #5b9bd5; }

  /* Model selector */
  #chat-header { display: flex; align-items: center; justify-content: space-between; }
  #model-select { background: #222; border: 1px solid #333; color: #aaa;
                  padding: 4px 8px; border-radius: 6px; font-size: 12px; outline: none; }
  #model-select:focus { border-color: #6b8cff; }
  #tts-model-select { background: #222; border: 1px solid #333; color: #aaa;
                      padding: 4px 8px; border-radius: 6px; font-size: 12px; outline: none;
                      display: none; }
  #tts-model-select:focus { border-color: #6b8cff; }

  /* Voice toggle */
  #voice-toggle { background: #222; border: 1px solid #333; color: #aaa;
                  padding: 4px 10px; border-radius: 6px; font-size: 14px;
                  cursor: pointer; transition: background 0.15s; }
  #voice-toggle.on  { background: #1a3a2a; border-color: #3a8a5a; color: #5aba8a; }
  #voice-toggle.off { background: #222;    border-color: #333;    color: #666; }
  /* Dialog mode toggle */
  #dialog-toggle { background: #222; border: 1px solid #333; color: #666;
                   padding: 4px 10px; border-radius: 6px; font-size: 13px;
                   cursor: pointer; transition: background 0.15s; }
  #dialog-toggle.on { background: #3a1a3a; border-color: #8a3a8a; color: #ca7aca; }
  #header-right { display: flex; align-items: center; gap: 8px; }
  /* Microphone button */
  #mic-btn { background: #222; border: 1px solid #333; color: #aaa;
             padding: 10px 14px; border-radius: 8px; font-size: 16px;
             cursor: pointer; transition: background 0.15s; }
  #mic-btn.listening { background: #3a1a1a; border-color: #e05555;
                       color: #e05555; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.5; } }
  #lang-select { background: #222; border: 1px solid #333; color: #888;
                 padding: 10px 8px; border-radius: 8px; font-size: 12px; outline: none; }
  #lang-select:focus { border-color: #6b8cff; }

  /* Delete button */
  .msg-wrap { position: relative; display: flex; }
  .msg-wrap.user { justify-content: flex-end; }
  .msg-wrap.assistant { justify-content: flex-start; }
  .msg { position: relative; }
  .del-btn { display: none; position: absolute; top: 4px; right: 6px;
             background: none; border: none; color: #666; cursor: pointer;
             font-size: 14px; line-height: 1; padding: 0 2px; }
  .msg:hover .del-btn { display: block; }
  .del-btn:hover { color: #e05555; }

  /* Hamburger (mobile only) */
  #menu-btn { display: none; background: none; border: none; color: #aaa;
              font-size: 22px; cursor: pointer; padding: 0 4px; line-height: 1; }

  /* Mobile */
  @media (max-width: 640px) {
    #menu-btn { display: block; }
    #sidebar { position: fixed; top: 0; left: 0; height: 100%; z-index: 200;
               transform: translateX(-100%); transition: transform 0.25s;
               width: 220px; }
    #sidebar.open { transform: translateX(0); box-shadow: 4px 0 20px #000a; }
    #sidebar-overlay { display: none; position: fixed; inset: 0; z-index: 199;
                       background: #0008; }
    #sidebar-overlay.open { display: block; }
    .agent-btn { padding: 14px 16px; font-size: 16px; }
    #chat-header { padding: 12px 12px; }
    #header-right { gap: 6px; }
    #voice-toggle, #dialog-toggle { padding: 8px 12px; font-size: 16px; }
    #tts-model-select, #model-select { font-size: 12px; max-width: 110px; }
    #messages { padding: 12px; }
    .msg { max-width: 90%; font-size: 15px; }
    #input-area { padding: 10px 12px; gap: 8px; }
    #msg-input { font-size: 16px; /* предотвращает zoom на iOS */ }
    #send-btn { padding: 10px 14px; font-size: 15px; }
    #mic-btn { padding: 10px 14px; font-size: 18px; }
    #lang-select { padding: 10px 6px; font-size: 13px; }
  }
</style>
</head>
<body>

<div id="sidebar-overlay" onclick="closeSidebar()"></div>
<div id="sidebar">
  <h2>Агенти</h2>
  <div id="agent-list"></div>
</div>

<div id="chat-area">
  <div id="chat-header">
    <div style="display:flex;align-items:center;gap:10px;min-width:0;">
      <button id="menu-btn" onclick="openSidebar()" title="Агенты">&#9776;</button>
      <span id="header-title" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Оберіть агента</span>
    </div>
    <div id="header-right">
      <button id="voice-toggle" class="off" onclick="toggleVoice()" title="Голосовой режим">&#x1F507;</button>
      <select id="tts-model-select" onchange="saveTtsModel(this.value)" title="TTS модель"></select>
      <button id="dialog-toggle" class="off" onclick="toggleDialog()" title="Авто-диалог: после ответа агента микрофон включается автоматически">&#x1F504;</button>
      <select id="model-select" style="display:none" onchange="saveModel(this.value)">
      </select>
    </div>
  </div>
  <div id="messages"></div>
  <div id="input-area">
    <textarea id="msg-input" placeholder="Напишіть повідомлення..." rows="1"
              onkeydown="handleKey(event)"></textarea>
    <select id="lang-select" title="Язык распознавания">
      <option value="auto">Авто</option>
      <option value="de-DE">🇩🇪 DE</option>
      <option value="ru-RU">🇷🇺 RU</option>
      <option value="uk-UA">🇺🇦 UK</option>
      <option value="en-US">🇺🇸 EN</option>
    </select>
    <button id="mic-btn" onclick="toggleMic()" title="Голосовой ввод">&#x1F3A4;</button>
    <button id="send-btn" onclick="sendMessage()">Надіслати</button>
  </div>
</div>

<script>
const AGENTS = AGENTS_JSON;
let currentAgent = null;
let ws = null;
let availableModels = {};
let voiceMode = false;
let dialogMode = false;
let availableTtsModels = {};
let selectedTtsModel = 'gemini-3.1-flash-tts-preview';

// i18n
const I18N = {
  uk: {
    agents:      "Агенти",
    choose:      "Оберіть агента",
    placeholder: "Напишіть повідомлення...",
    send:        "Надіслати",
    typing:      "Агент друкує…",
    delete:      "Видалити",
    voiceOn:     "Вимкнути звук",
    voiceOff:    "Увімкнути звук",
    dialogOn:    "Авто-діалог: увімкнено",
    dialogOff:   "Авто-діалог: вимкнено",
    lang_auto:   "Авто",
  },
  de: {
    agents:      "Agenten",
    choose:      "Agent auswählen",
    placeholder: "Nachricht eingeben...",
    send:        "Senden",
    typing:      "Agent tippt…",
    delete:      "Löschen",
    voiceOn:     "Ton ausschalten",
    voiceOff:    "Ton einschalten",
    dialogOn:    "Auto-Dialog: aktiv",
    dialogOff:   "Auto-Dialog: aus",
    lang_auto:   "Auto",
  },
  en: {
    agents:      "Agents",
    choose:      "Select agent",
    placeholder: "Type a message...",
    send:        "Send",
    typing:      "Agent is typing…",
    delete:      "Delete",
    voiceOn:     "Mute",
    voiceOff:    "Unmute",
    dialogOn:    "Auto-dialog: on",
    dialogOff:   "Auto-dialog: off",
    lang_auto:   "Auto",
  },
  pt: {
    agents:      "Agentes",
    choose:      "Selecione um agente",
    placeholder: "Digite uma mensagem...",
    send:        "Enviar",
    typing:      "Agente digitando…",
    delete:      "Excluir",
    voiceOn:     "Silenciar",
    voiceOff:    "Ativar som",
    dialogOn:    "Diálogo auto: ativado",
    dialogOff:   "Diálogo auto: desativado",
    lang_auto:   "Auto",
  },
};
let lang = 'uk';

function t(key) { return (I18N[lang] || I18N.uk)[key] || key; }

function applyLang(l) {
  lang = l || 'uk';
  document.getElementById('sidebar').querySelector('h2').textContent = t('agents');
  document.getElementById('header-title').textContent = currentAgent
    ? (AGENTS[currentAgent] || t('choose')) : t('choose');
  document.getElementById('msg-input').placeholder = t('placeholder');
  document.getElementById('send-btn').textContent = t('send');
  const langOpt = document.querySelector('#lang-select option[value="auto"]');
  if (langOpt) langOpt.textContent = t('lang_auto');
}

// Загрузить TTS-модели
fetch('/api/tts-models').then(r => r.json()).then(m => {
  availableTtsModels = m;
  const sel = document.getElementById('tts-model-select');
  Object.entries(m).forEach(([val, name]) => {
    const opt = document.createElement('option');
    opt.value = val; opt.textContent = name; sel.appendChild(opt);
  });
  sel.value = selectedTtsModel;
});

function saveTtsModel(val) {
  selectedTtsModel = val;
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let micActive = false;
let silenceTimer = null;
let finalTranscript = '';   // зафіксовані слова (isFinal=true)
const SILENCE_MS = 2500;

function getLang() {
  const sel = document.getElementById('lang-select').value;
  if (sel !== 'auto') return sel;
  return currentAgent === 'tutor' ? 'de-DE' : 'uk-UA';
}

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = (e) => {
    const input = document.getElementById('msg-input');
    let interim = '';

    // Обходимо тільки нові результати починаючи з e.resultIndex
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) {
        finalTranscript += t;
      } else {
        interim += t;
      }
    }

    input.value = finalTranscript + interim;

    // Скидаємо таймер тиші при кожному новому результаті
    clearTimeout(silenceTimer);
    silenceTimer = setTimeout(() => {
      if (micActive && input.value.trim()) {
        stopMic();
        setTimeout(() => sendMessage(), 100);
      }
    }, SILENCE_MS);
  };

  recognition.onerror = (e) => { clearTimeout(silenceTimer); stopMic(); };
  recognition.onend   = () => {
    // continuous=true запускає onend при помилках; перезапускаємо якщо мік ще активний
    if (micActive) { try { recognition.start(); } catch(e) { stopMic(); } }
  };
}

function toggleMic() {
  if (!recognition) { alert('Браузер не поддерживает Web Speech API'); return; }
  micActive ? stopMic() : startMic();
}

function startMic() {
  if (!recognition || !currentAgent) return;
  micActive = true;
  finalTranscript = '';   // скидаємо накопичений текст
  document.getElementById('msg-input').value = '';
  document.getElementById('mic-btn').className = 'listening';
  recognition.lang = getLang();
  try { recognition.start(); } catch(e) {}
}

function stopMic() {
  clearTimeout(silenceTimer);
  micActive = false;
  document.getElementById('mic-btn').className = '';
  try { recognition.stop(); } catch(e) {}
}

function toggleVoice() {
  voiceMode = !voiceMode;
  const btn = document.getElementById('voice-toggle');
  btn.textContent = voiceMode ? '\U0001F50A' : '\U0001F507';
  btn.className = voiceMode ? 'on' : 'off';
  btn.title = voiceMode ? 'Отключить звук' : 'Включить звук';
  document.getElementById('tts-model-select').style.display = voiceMode ? 'inline-block' : 'none';
  if (!voiceMode && dialogMode) toggleDialog();
}

function toggleDialog() {
  dialogMode = !dialogMode;
  const btn = document.getElementById('dialog-toggle');
  btn.className = dialogMode ? 'on' : 'off';
  btn.title = dialogMode ? 'Авто-диалог: включён' : 'Авто-диалог: выключен';
  if (dialogMode && !voiceMode) toggleVoice();
}

// Загрузить модели
 fetch('/api/models').then(r => r.json()).then(m => { availableModels = m; });
applyLang('uk');  // дефолт — украинский

// Строим sidebar
const list = document.getElementById('agent-list');
Object.entries(AGENTS).forEach(([key, label]) => {
  const btn = document.createElement('button');
  btn.className = 'agent-btn';
  btn.textContent = label;
  btn.dataset.agent = key;
  btn.onclick = () => selectAgent(key, label, btn);
  list.appendChild(btn);
});

function openSidebar() {
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebar-overlay').classList.add('open');
}
function closeSidebar() {
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

function selectAgent(key, label, btn) {
  if (currentAgent === key) return;
  currentAgent = key;
  closeSidebar();

  // UI
  document.querySelectorAll('.agent-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('header-title').textContent = label;
  document.getElementById('messages').innerHTML = '';

  // Выбор модели
  const sel = document.getElementById('model-select');
  sel.innerHTML = '';
  Object.entries(availableModels).forEach(([val, name]) => {
    const opt = document.createElement('option');
    opt.value = val; opt.textContent = name; sel.appendChild(opt);
  });
  sel.style.display = Object.keys(availableModels).length ? 'inline-block' : 'none';
  fetch(`/api/settings/${key}`).then(r => r.json()).then(s => {
    sel.value = s.model;
    if (s.ui_lang) applyLang(s.ui_lang);
  });

  // Загрузить историю
  fetch(`/api/history/${key}`)
    .then(r => r.json())
    .then(msgs => {
      msgs.forEach(m => appendMessage(m.role, m.content, m.audio_path, m.source, false, m.id));
      scrollBottom();
    });

  // WebSocket
  if (ws) ws.close();
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${key}`);
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    removeTyping();
    if (data.type === 'message') {
      appendMessage('assistant', data.text, data.audio_path, 'web', voiceMode, data.id);
      scrollBottom();
      document.getElementById('send-btn').disabled = false;
    }
  };
}

function saveModel(model) {
  if (!currentAgent) return;
  fetch(`/api/settings/${currentAgent}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model})
  });
}

function deleteMessage(id, wrapEl) {
  if (!id) return;
  fetch(`/api/message/${id}`, {method: 'DELETE'})
    .then(r => r.json())
    .then(d => { if (d.ok) wrapEl.remove(); });
}

function appendMessage(role, content, audioPath, source, animate, msgId) {
  const msgs = document.getElementById('messages');
  const wrap = document.createElement('div');
  wrap.className = `msg-wrap ${role}`;

  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const badge = source === 'telegram'
    ? '<span class="badge telegram">tg</span>' : '';

  div.innerHTML = `<div>${escHtml(content)}${badge}</div>`;

  if (audioPath && role === 'assistant') {
    const audio = document.createElement('audio');
    audio.controls = true;
    audio.src = `/audio/${audioPath.split('/').pop()}`;
    audio.autoplay = animate;
    if (animate && dialogMode) {
      audio.onended = () => { if (dialogMode) startMic(); };
    }
    div.appendChild(audio);
  }

  const delBtn = document.createElement('button');
  delBtn.className = 'del-btn';
  delBtn.title = t('delete');
  delBtn.textContent = '×';
  delBtn.onclick = () => deleteMessage(msgId, wrap);

  div.appendChild(delBtn);
  wrap.appendChild(div);
  msgs.appendChild(wrap);
}

function removeTyping() {
  document.querySelectorAll('.typing').forEach(e => e.remove());
}

function showTyping() {
  removeTyping();
  const div = document.createElement('div');
  div.className = 'typing';
  div.textContent = t('typing');
  document.getElementById('messages').appendChild(div);
  scrollBottom();
}

function sendMessage() {
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== 1) return;

  appendMessage('user', text, null, 'web', false);
  scrollBottom();
  ws.send(JSON.stringify({text, tts: voiceMode, tts_model: selectedTtsModel}));
  input.value = '';
  input.style.height = 'auto';
  document.getElementById('send-btn').disabled = true;
  showTyping();
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function scrollBottom() {
  const m = document.getElementById('messages');
  m.scrollTop = m.scrollHeight;
}

function escHtml(t) {
  return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
          .replace(/\\n/g,'<br>');
}
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    import json
    agents_json = json.dumps(AGENT_LABELS)
    return HTML.replace("AGENTS_JSON", agents_json)


@app.get("/audio/{filename}")
async def get_audio(filename: str):
    # Безопасность: только имя файла, без path traversal
    safe_name = Path(filename).name
    path = Path(AUDIO_DIR) / safe_name
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/history/{agent}")
async def history(agent: str):
    return get_recent_messages(agent, limit=50)


@app.delete("/api/message/{message_id}")
async def remove_message(message_id: int):
    ok = delete_message(message_id)
    if not ok:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"ok": True}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return SETTINGS_HTML


@app.get("/api/tts-models")
async def tts_models():
    return TTS_MODELS


@app.get("/api/models")
async def models():
    return AVAILABLE_MODELS


@app.get("/api/settings/{agent}")
async def get_settings(agent: str, request: Request):
    user_id = request.headers.get("X-Forwarded-User", "alex")
    return get_effective_settings(agent, user_id)


@app.put("/api/settings/{agent}")
async def save_settings(agent: str, request: Request):
    """Сохраняет глобальные настройки (admin). Вызывается со страницы /settings."""
    body = await request.json()
    allowed = {"model", "system_prompt", "temperature", "max_tokens", "tts_voice", "tts_lang", "ui_lang"}
    fields = {k: v for k, v in body.items() if k in allowed}
    if "model" in fields and fields["model"] not in AVAILABLE_MODELS:
        return JSONResponse({"error": "unknown model"}, status_code=400)
    save_global_settings(agent, fields)
    return {"ok": True}


@app.put("/api/user-settings/{agent}")
async def save_user_settings_endpoint(agent: str, request: Request):
    """Сохраняет пользовательские переопределения."""
    user_id = request.headers.get("X-Forwarded-User", "alex")
    body = await request.json()
    save_user_setting(user_id, agent, body)
    return {"ok": True}


@app.delete("/api/user-settings/{agent}/{field}")
async def reset_user_setting_endpoint(agent: str, field: str, request: Request):
    """Сбрасывает пользовательское переопределение одного поля до глобального."""
    user_id = request.headers.get("X-Forwarded-User", "alex")
    reset_user_setting(user_id, agent, field)
    return {"ok": True}


@app.get("/api/ui-languages")
async def ui_languages():
    return UI_LANGUAGES


@app.get("/api/agent-defaults")
async def agent_defaults():
    # Возвращаем дефолты (без system_prompt — слишком длинный для UI списка)
    result = {}
    for agent, d in AGENT_DEFAULTS.items():
        result[agent] = {k: v for k, v in d.items() if k != "system_prompt"}
    return result


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws/{agent}")
async def websocket_endpoint(websocket: WebSocket, agent: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            text = data.get("text", "").strip()
            tts = bool(data.get("tts", False))
            tts_model = data.get("tts_model", "gemini-3.1-flash-tts-preview")
            if not text:
                continue
            result = await process(agent=agent, user_input=text, source="web", tts=tts, tts_model=tts_model)
            await websocket.send_json({
                "type": "message",
                "text": result["text"],
                "audio_path": result.get("audio_path"),
                "id": result.get("id"),
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WS error: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass


def run():
    import uvicorn
    port = int(os.environ.get("WEB_PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
