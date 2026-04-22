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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import importlib

logger = logging.getLogger(__name__)

app = FastAPI(title="Antigravity Agents")

# Импортируем агентов чтобы они зарегистрировались в router
import src.agents.tutor  # noqa: F401

from src.gateway.router import process, AGENT_LABELS
from src.db.conversations import get_recent_messages

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
</style>
</head>
<body>

<div id="sidebar">
  <h2>Агенты</h2>
  <div id="agent-list"></div>
</div>

<div id="chat-area">
  <div id="chat-header">Выберите агента</div>
  <div id="messages"></div>
  <div id="input-area">
    <textarea id="msg-input" placeholder="Напишите сообщение..." rows="1"
              onkeydown="handleKey(event)"></textarea>
    <button id="send-btn" onclick="sendMessage()">Отправить</button>
  </div>
</div>

<script>
const AGENTS = AGENTS_JSON;
let currentAgent = null;
let ws = null;

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
  document.getElementById('chat-header').textContent = label;
  document.getElementById('messages').innerHTML = '';

  // Загрузить историю
  fetch(`/api/history/${key}`)
    .then(r => r.json())
    .then(msgs => {
      msgs.forEach(m => appendMessage(m.role, m.content, m.audio_path, m.source, false));
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
      appendMessage('assistant', data.text, data.audio_path, 'web', true);
      scrollBottom();
      document.getElementById('send-btn').disabled = false;
    }
  };
}

function appendMessage(role, content, audioPath, source, animate) {
  const msgs = document.getElementById('messages');
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
    div.appendChild(audio);
  }

  msgs.appendChild(div);
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
  ws.send(JSON.stringify({text}));
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


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws/{agent}")
async def websocket_endpoint(websocket: WebSocket, agent: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            text = data.get("text", "").strip()
            if not text:
                continue
            result = await process(agent=agent, user_input=text, source="web")
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
