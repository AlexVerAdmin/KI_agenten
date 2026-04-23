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
from src.config import AVAILABLE_MODELS, TTS_MODELS, get_agent_model, set_agent_model

AUDIO_DIR = "/tmp/tutor_audio"


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
</style>
</head>
<body>

<div id="sidebar">
  <h2>Агенты</h2>
  <div id="agent-list"></div>
</div>

<div id="chat-area">
  <div id="chat-header">
    <span id="header-title">Выберите агента</span>
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
    <textarea id="msg-input" placeholder="Напишите сообщение..." rows="1"
              onkeydown="handleKey(event)"></textarea>
    <select id="lang-select" title="Язык распознавания">
      <option value="auto">Авто</option>
      <option value="de-DE">🇩🇪 DE</option>
      <option value="ru-RU">🇷🇺 RU</option>
      <option value="uk-UA">🇺🇦 UK</option>
      <option value="en-US">🇺🇸 EN</option>
    </select>
    <button id="mic-btn" onclick="toggleMic()" title="Голосовой ввод">&#x1F3A4;</button>
    <button id="send-btn" onclick="sendMessage()">Отправить</button>
  </div>
</div>

<script>
const AGENTS = AGENTS_JSON;
let currentAgent = null;
let ws = null;
let availableModels = {};
let voiceMode = false;   // TTS + автоплей
let dialogMode = false;  // авто-диалог: после ответа mic включается сам
let availableTtsModels = {};
let selectedTtsModel = 'gemini-3.1-flash-tts-preview';

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
const SILENCE_MS = 2500;  // пауза тишины перед отправкой

function getLang() {
  const sel = document.getElementById('lang-select').value;
  if (sel !== 'auto') return sel;
  return currentAgent === 'tutor' ? 'de-DE' : 'ru-RU';
}

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = (e) => {
    const input = document.getElementById('msg-input');
    let transcript = '';
    for (let i = 0; i < e.results.length; i++) {
      transcript += e.results[i][0].transcript;
    }
    input.value = transcript;

    // Сбрасываем таймер паузы при каждом новом результате
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
    // continuous=true запускает onend при ошибках; перезапускаем если мик ещё активен
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

function selectAgent(key, label, btn) {
  if (currentAgent === key) return;
  currentAgent = key;

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
  fetch(`/api/settings/${key}`).then(r => r.json()).then(s => { sel.value = s.model; });

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
  delBtn.title = 'Удалить';
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
  div.textContent = 'Агент печатает…';
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


@app.get("/api/tts-models")
async def tts_models():
    return TTS_MODELS


@app.get("/api/models")
async def models():
    return AVAILABLE_MODELS


@app.get("/api/settings/{agent}")
async def get_settings(agent: str):
    return {"model": get_agent_model(agent)}


@app.put("/api/settings/{agent}")
async def save_settings(agent: str, request: Request):
    body = await request.json()
    model = body.get("model", "")
    if model not in AVAILABLE_MODELS:
        return JSONResponse({"error": "unknown model"}, status_code=400)
    set_agent_model(agent, model)
    return {"ok": True, "model": model}


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
