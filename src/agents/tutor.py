"""
Агент: Учитель немецкого (Max Klein).
Регистрируется в router через @register("tutor").
Принимает текст или голосовой файл → возвращает текст + путь к аудио.
Модель выбирается динамически: Gemini cloud или локальная (llama-cpp OpenAI API).
"""

import os
import uuid
import logging
import edge_tts
from openai import AsyncOpenAI

from src.gateway.router import register
from src.db.conversations import get_history_text, get_history
from src.config import GEMINI_API_KEY, LOCAL_MODEL_URL, LOCAL_MODEL_NAME, get_agent_model
from src.utils.obsidian import read_obsidian, append_dated_note

logger = logging.getLogger(__name__)

TTS_VOICE = "de-DE-ConradNeural"
TTS_SPEED = "+0%"
AUDIO_DIR = "/tmp/tutor_audio"
AGENT_NAME = "tutor"

SYSTEM_PROMPT = (
    "Du bist Max Klein, ein freundlicher und geduldiger Deutschlehrer. "
    "Du unterrichtest Russisch-Muttersprachler auf B1-Niveau. "
    "Antworte auf Deutsch, erkläre kurz auf Russisch wenn nötig. "
    "Maximal 3-4 Sätze pro Antwort. "
    "Wenn der Schüler einen Fehler macht, korrigiere ihn sanft."
)

PROGRESS_PATH   = "01_Projects/Agents/tutor/progress.md"
VOCABULARY_PATH = "01_Projects/Agents/tutor/vocabulary.md"

# Записывать итог урока каждые N сообщений пользователя
SUMMARY_EVERY = 10


def _make_client(model: str) -> tuple[AsyncOpenAI, str]:
    """Возвращает (AsyncOpenAI client, model_name) в зависимости от выбранной модели."""
    if model == "local":
        client = AsyncOpenAI(base_url=LOCAL_MODEL_URL, api_key="local")
        return client, LOCAL_MODEL_NAME
    else:
        # Gemini через OpenAI-совместимый endpoint
        client = AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=GEMINI_API_KEY,
        )
        return client, model


@register("tutor")
async def process(user_input: str, voice_path: str = None, tts: bool = True) -> dict:
    """
    Обрабатывает запрос к учителю немецкого.
    tts=False — не генерировать аудио.
    Возвращает {"text": str, "audio_path": str|None}.
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)

    model_key = get_agent_model(AGENT_NAME)
    client, model_name = _make_client(model_key)

    history = get_history_text(AGENT_NAME, limit=20)

    # Загружаем прогресс и словарь из Obsidian
    progress   = read_obsidian(PROGRESS_PATH)
    vocabulary = read_obsidian(VOCABULARY_PATH)

    context_parts = [SYSTEM_PROMPT]
    if progress:
        context_parts.append(f"## Прогресс ученика:\n{progress}")
    if vocabulary:
        context_parts.append(f"## Словарь ученика (последние слова):\n{vocabulary[-1500:]}")

    messages = [{"role": "system", "content": "\n\n".join(context_parts)}]
    if history:
        messages.append({"role": "system", "content": f"История урока:\n{history}"})

    if voice_path and os.path.exists(voice_path):
        # Локальные модели не поддерживают аудио — транскрибируем текстово
        messages.append({
            "role": "user",
            "content": "[Schüler hat eine Sprachnachricht gesendet — bitte antworte als Max Klein]"
        })
    else:
        messages.append({"role": "user", "content": user_input})

    response = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=2048,
        temperature=0.7,
    )
    ai_reply = (response.choices[0].message.content or "").strip()

    # Gemini 2.5 Pro иногда возвращает пустой content (thinking mode).
    # Fallback на gemini-2.5-flash.
    if not ai_reply and model_name != "gemini-2.5-flash":
        logger.warning(f"Empty content from {model_name}, retrying with gemini-2.5-flash")
        fallback_client = AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=GEMINI_API_KEY,
        )
        response = await fallback_client.chat.completions.create(
            model="gemini-2.5-flash",
            messages=messages,
            max_tokens=2048,
            temperature=0.7,
        )
        ai_reply = (response.choices[0].message.content or "").strip()

    if not ai_reply:
        ai_reply = "(Keine Antwort vom Modell. Bitte nochmals versuchen.)"

    # Каждые SUMMARY_EVERY сообщений пользователя — запрашиваем краткий итог у модели
    history_count = len(get_history(AGENT_NAME, limit=500))
    if history_count > 0 and history_count % SUMMARY_EVERY == 0:
        try:
            summary_resp = await client.chat.completions.create(
                model=model_name,
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
        communicate = edge_tts.Communicate(ai_reply.replace("*", ""), TTS_VOICE, rate=TTS_SPEED)
        await communicate.save(audio_path)

    return {"text": ai_reply, "audio_path": audio_path}
