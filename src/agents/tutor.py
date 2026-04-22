"""
Агент: Учитель немецкого (Max Klein).
Регистрируется в router через @register("tutor").
Принимает текст или голосовой файл → возвращает текст + путь к аудио.
"""

import os
import uuid
import logging
from google import genai
from google.genai import types
import edge_tts

from src.gateway.router import register
from src.db.conversations import get_history_text

logger = logging.getLogger(__name__)

TTS_VOICE = "de-DE-ConradNeural"
TTS_SPEED = "+0%"
GEMINI_MODEL = "gemini-2.5-pro"
AUDIO_DIR = "/tmp/tutor_audio"

SYSTEM_PROMPT = (
    "Du bist Max Klein, ein freundlicher und geduldiger Deutschlehrer. "
    "Du unterrichtest Russisch-Muttersprachler auf B1-Niveau. "
    "Antworte auf Deutsch, erkläre kurz auf Russisch wenn nötig. "
    "Maximal 3-4 Sätze pro Antwort. "
    "Wenn der Schüler einen Fehler macht, korrigiere ihn sanft."
)


@register("tutor")
async def process(user_input: str, voice_path: str = None) -> dict:
    """
    Обрабатывает запрос к учителю немецкого.
    voice_path: путь к .ogg файлу если голосовое сообщение.
    Возвращает {"text": str, "audio_path": str}.
    """
    os.makedirs(AUDIO_DIR, exist_ok=True)

    api_key = os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    # История из БД (последние 20 сообщений)
    history = get_history_text("tutor", limit=20)

    # Собираем contents для Gemini
    contents = []

    if voice_path and os.path.exists(voice_path):
        # Голосовой ввод: загружаем файл в Gemini Files API
        file_upload = client.files.upload(path=voice_path)
        contents.append(types.Part.from_uri(file_upload.uri, mime_type="audio/ogg"))
        prompt = (
            f"System: {SYSTEM_PROMPT}\n\n"
            f"История урока:\n{history}\n\n"
            "Schüler hat eine Sprachnachricht gesendet (siehe Audio oben). "
            "Transkribiere es kurz und antworte als Max Klein:"
        )
    else:
        prompt = (
            f"System: {SYSTEM_PROMPT}\n\n"
            f"История урока:\n{history}\n\n"
            f"Schüler: {user_input}\n"
            "Max Klein:"
        )

    contents.append(prompt)

    response = client.models.generate_content(model=GEMINI_MODEL, contents=contents)
    ai_reply = response.text.strip()

    # Генерируем голосовой ответ
    audio_path = os.path.join(AUDIO_DIR, f"{uuid.uuid4()}.mp3")
    communicate = edge_tts.Communicate(ai_reply.replace("*", ""), TTS_VOICE, rate=TTS_SPEED)
    await communicate.save(audio_path)

    return {"text": ai_reply, "audio_path": audio_path}
