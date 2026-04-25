"""
Агент: Учитель немецкого (Max Klein).
Регистрируется в router через @register("tutor").
Принимает текст или голосовой файл → возвращает текст + путь к аудио.
Модель выбирается динамически: Gemini cloud или локальная (llama-cpp OpenAI API).
"""

import os
import uuid
import json
import logging
import edge_tts
from src.llm import chat_completion

from src.gateway.router import register
from src.db.conversations import get_history_text, get_history
from src.config import GEMINI_API_KEY, LOCAL_MODEL_URL, LOCAL_MODEL_NAME, get_effective_settings
from src.utils.obsidian import read_obsidian, append_dated_note, write_obsidian
from src.agents.base_agent import AgentWithObsidian

logger = logging.getLogger(__name__)

TTS_SPEED = "+0%"
AUDIO_DIR = "/tmp/tutor_audio"
AGENT_NAME = "tutor"

PROGRESS_PATH   = "01_Projects/Agents/tutor/progress.md"
VOCABULARY_PATH = "01_Projects/Agents/tutor/vocabulary.md"

class TutorAgent(AgentWithObsidian):
    agent_name = "tutor"
    memory_files = {
        "progress": "agents/tutor/progress.md",
        "vocabulary": "agents/tutor/vocabulary.md",
    }

_tutor_agent = TutorAgent()

# Записывать итог урока каждые N сообщений пользователя
SUMMARY_EVERY = 10

# Описание инструментов — добавляется к system_prompt автоматически
_TOOLS_CONTEXT = """\
## Deine Werkzeuge (nutze sie selbst, bitte den Schüler NICHT, etwas aufzuschreiben):
- add_to_vocabulary(word, translation, example) — neues Wort zum Vokabular des Schülers hinzufügen
- update_progress(note) — Fortschrittsnotiz, Thema oder Fehler des Schülers aufschreiben

Wenn du ein neues Wort erklärst oder der Schüler danach fragt — rufe sofort add_to_vocabulary auf.
Sag NIEMALS "schreib das auf" oder "füge es zum Wörterbuch hinzu" — tue es selbst."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_to_vocabulary",
            "description": "Fügt ein Wort oder eine Phrase zum Vokabular des Schülers in Obsidian hinzu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "word":        {"type": "string", "description": "Das deutsche Wort oder die Phrase"},
                    "translation": {"type": "string", "description": "Übersetzung ins Russische oder Ukrainische"},
                    "example":     {"type": "string", "description": "Beispielsatz (optional)"},
                },
                "required": ["word", "translation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_progress",
            "description": "Schreibt eine Fortschrittsnotiz über die Unterrichtsstunde in Obsidian.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string", "description": "Notiz über Fortschritt, Thema oder Fehler"},
                },
                "required": ["note"],
            },
        },
    },
]


def _tool_add_vocabulary(word: str, translation: str, example: str = "") -> str:
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d")
    line = f"- **{word}** — {translation}"
    if example:
        line += f" | _Bsp.:_ {example}"
    line += f" _{ts}_"
    ok = write_obsidian(VOCABULARY_PATH, line + "\n", append=True)
    return f"✅ Wort gespeichert: {word}" if ok else "⚠️ Fehler beim Speichern"


def _tool_update_progress(note: str) -> str:
    ok = append_dated_note(PROGRESS_PATH, note)
    return "✅ Fortschritt gespeichert" if ok else "⚠️ Fehler beim Speichern"


# _make_client removed, logic moved to src.llm


@register("tutor")
async def process(user_input: str, voice_path: str = None, tts: bool = True, tts_model: str = None, user_id: str = "alex", **kwargs) -> dict:
    """
    Обрабатывает запрос к учителю.
    tts=False — не генерировать аудио.
    Возвращает {"text": str, "audio_path": str|None}.
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)

    cfg = get_effective_settings(AGENT_NAME, user_id)
    model_key  = cfg["model"]
    tts_voice  = cfg.get("tts_voice", "Fenrir")
    tts_lang   = cfg.get("tts_lang", "de-DE")
    system_prompt = cfg.get("system_prompt", "")
    temperature   = float(cfg.get("temperature", 0.7))
    max_tokens    = int(cfg.get("max_tokens", 8192))
    if tts_model is None:
        tts_model = "gemini-3.1-flash-tts-preview"
    # Edge TTS voice (IETF-tag from tts_lang)
    edge_voice = f"{tts_lang}-ConradNeural" if tts_lang.startswith("de") else "uk-UA-OstapNeural"

    history = get_history_text(AGENT_NAME, limit=20)

    # Загружаем прогресс и словарь из Obsidian
    progress   = read_obsidian(PROGRESS_PATH)
    vocabulary = read_obsidian(VOCABULARY_PATH)

    context_parts = [system_prompt + "\n\n" + _TOOLS_CONTEXT]
    if progress:
        context_parts.append(f"## Прогресс ученика:\n{progress}")
    if vocabulary:
        context_parts.append(f"## Словарь ученика (последние слова):\n{vocabulary[-1500:]}")

    messages = [{"role": "system", "content": "\n\n".join(context_parts)}]
    if history:
        messages.append({"role": "system", "content": f"История урока:\n{history}"})

    if voice_path and os.path.exists(voice_path):
        messages.append({
            "role": "user",
            "content": "[Schüler hat eine Sprachnachricht gesendet — bitte antworte als Lehrer]"
        })
    else:
        messages.append({"role": "user", "content": user_input})

    # Агентный цикл: модель может вызывать инструменты
    ai_reply = ""
    for _ in range(5):
        response = await chat_completion(
            model=model_key,
            messages=messages,
            tools=TOOLS,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            ai_reply = (msg.content or "").strip()
            break

        # Обрабатываем tool calls
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except Exception:
                args = {}
            if tc.function.name == "add_to_vocabulary":
                result = _tool_add_vocabulary(**args)
            elif tc.function.name == "update_progress":
                result = _tool_update_progress(**args)
            else:
                result = f"Unknown tool: {tc.function.name}"
            logger.info(f"Tool {tc.function.name}: {result}")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Fallback: пустой ответ — retry
    if not ai_reply:
        logger.warning(f"Empty content from {model_key}, retrying with basic settings")
        response = await chat_completion(
            model=model_key,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        ai_reply = (response.choices[0].message.content or "").strip()

    if not ai_reply:
        ai_reply = "(Keine Antwort vom Modell. Bitte nochmals versuchen.)"

    # Каждые SUMMARY_EVERY сообщений пользователя — запрашиваем краткий итог у модели
    history_count = len(get_history(AGENT_NAME, limit=500))
    if history_count > 0 and history_count % SUMMARY_EVERY == 0:
        try:
            summary_resp = await chat_completion(
                model=model_key,
                messages=[
                    {"role": "system", "content": "Ты ассистент-секретарь. Напиши краткий итог урока на русском языке (3-5 пунктов): темы, ошибки ученика, новые слова."},
                    {"role": "user", "content": f"Итог урока:\n{history}"},
                ],
                max_tokens=300,
                temperature=0.3,
            )
            summary = summary_resp.choices[0].message.content.strip()
            append_dated_note(PROGRESS_PATH, summary)
        except Exception as e:
            logger.warning(f"Не удалось записать итог урока: {e}")

    # TTS (только если запрошено)
    audio_path = None
    if tts:
        audio_path = os.path.join(AUDIO_DIR, f"{uuid.uuid4()}.mp3")
        if tts_model == "edge-tts":
            communicate = edge_tts.Communicate(ai_reply.replace("*", ""), edge_voice, rate=TTS_SPEED)
            await communicate.save(audio_path)
        else:
            ok = await _gemini_tts(ai_reply, audio_path, model=tts_model, lang=tts_lang, voice=tts_voice)
            if not ok:
                logger.warning(f"Gemini TTS ({tts_model}) failed, falling back to edge-tts")
                communicate = edge_tts.Communicate(ai_reply.replace("*", ""), edge_voice, rate=TTS_SPEED)
                await communicate.save(audio_path)

    return {"text": ai_reply, "audio_path": audio_path}


async def _gemini_tts(text: str, audio_path: str, model: str = "gemini-3.1-flash-tts-preview",
                      lang: str = "de-DE", voice: str = "Fenrir") -> bool:
    """Генерирует аудио через Gemini TTS. Возвращает True при успехе."""
    import httpx
    import base64
    import subprocess

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice}
                },
                "languageCode": lang,
            },
        },
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as http:
            resp = await http.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        parts = data["candidates"][0]["content"]["parts"]
        audio_b64 = None
        mime_type = "audio/pcm"
        for part in parts:
            inline = part.get("inlineData", {})
            if inline:
                audio_b64 = inline.get("data")
                mime_type = inline.get("mimeType", "audio/pcm")
                break

        if not audio_b64:
            logger.warning("Gemini TTS: нет аудио в ответе")
            return False

        raw_audio = base64.b64decode(audio_b64)

        if "wav" in mime_type:
            wav_path = audio_path.replace(".mp3", ".wav")
            with open(wav_path, "wb") as f:
                f.write(raw_audio)
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, audio_path],
                capture_output=True, timeout=30
            )
            os.remove(wav_path)
        else:
            # Raw PCM16 LE, 24kHz, mono
            pcm_path = audio_path.replace(".mp3", ".pcm")
            with open(pcm_path, "wb") as f:
                f.write(raw_audio)
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                 "-i", pcm_path, audio_path],
                capture_output=True, timeout=30
            )
            os.remove(pcm_path)

        return result.returncode == 0

    except Exception as e:
        logger.warning(f"Gemini TTS error: {e}")
        return False
