"""
Агент: Карьерный коуч.
Регистрируется в router через @register("career").
Помогает с поиском работы, подготовкой к интервью, развитием карьеры.
Отвечает на русском языке.
"""

import logging
from openai import AsyncOpenAI

from src.gateway.router import register
from src.db.conversations import get_history_text
from src.config import GEMINI_API_KEY, LOCAL_MODEL_URL, LOCAL_MODEL_NAME, get_agent_model

logger = logging.getLogger(__name__)

AGENT_NAME = "career"

SYSTEM_PROMPT = (
    "Ты опытный карьерный коуч. Помогаешь людям с поиском работы, "
    "подготовкой к собеседованиям, составлением резюме, развитием карьеры "
    "и профессиональным ростом. "
    "Отвечай на русском языке. Будь конкретен и практичен. "
    "Задавай уточняющие вопросы если нужно больше контекста. "
    "Максимум 4-5 предложений за раз, если не просят подробнее."
)


def _make_client(model: str) -> tuple[AsyncOpenAI, str]:
    if model == "local":
        return AsyncOpenAI(base_url=LOCAL_MODEL_URL, api_key="local"), LOCAL_MODEL_NAME
    else:
        return AsyncOpenAI(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            api_key=GEMINI_API_KEY,
        ), model


@register("career")
async def process(user_input: str, voice_path: str = None, **kwargs) -> dict:
    model_key = get_agent_model(AGENT_NAME)
    client, model_name = _make_client(model_key)

    history_text = get_history_text(AGENT_NAME, limit=20)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history_text:
        messages.append({
            "role": "system",
            "content": f"История разговора:\n{history_text}",
        })

    messages.append({"role": "user", "content": user_input})

    response = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
    )

    text = response.choices[0].message.content.strip()
    return {"text": text, "audio_path": None}
