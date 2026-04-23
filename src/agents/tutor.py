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
from src.db.conversations import get_history_text
from src.config import GEMINI_API_KEY, LOCAL_MODEL_URL, LOCAL_MODEL_NAME, get_agent_model

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
async def process(user_input: str, voice_path: str = None) -> dict:
    """
    Обрабатывает запрос к учителю немецкого.
    Возвращает {"text": str, "audio_path": str}.
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)

    model_key = get_agent_model(AGENT_NAME)
    client, model_name = _make_client(model_key)

    history = get_history_text(AGENT_NAME, limit=20)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
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
        max_tokens=512,
        temperature=0.7,
    )
    ai_reply = response.choices[0].message.content.strip()

    # TTS
    audio_path = os.path.join(AUDIO_DIR, f"{uuid.uuid4()}.mp3")
    communicate = edge_tts.Communicate(ai_reply.replace("*", ""), TTS_VOICE, rate=TTS_SPEED)
    await communicate.save(audio_path)

    return {"text": ai_reply, "audio_path": audio_path}
