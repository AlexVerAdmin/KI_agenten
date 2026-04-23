"""
Единая точка входа для всех агентов.
Telegram-бот и Web UI вызывают router.process() — не агентов напрямую.
Router: сохраняет сообщение пользователя → вызывает агента → сохраняет ответ → возвращает результат.
"""

import logging
from src.db.conversations import save_message

logger = logging.getLogger(__name__)

# Реестр агентов: имя → функция обработки
# Каждый агент реализует: async process(user_input, voice_path=None) -> dict
_REGISTRY: dict = {}


def register(name: str):
    """Декоратор для регистрации агента."""
    def decorator(fn):
        _REGISTRY[name] = fn
        return fn
    return decorator


AGENT_LABELS = {
    "tutor":     "🇩🇪 Макс (Учитель немецкого)",
    "career":    "💼 Карьерный коуч",
    "finance":   "💰 Учёт финансов",
    "secretary": "📋 Личный секретарь",
    "ct2001":    "🖥️ Агент HomeLab",
    "vds":       "☁️ Агент VDS",
    "copilot":   "🧠 Copilot (Архитектор)",
}


async def process(
    agent: str,
    user_input: str,
    source: str = "telegram",
    voice_path: str = None,
    **kwargs,
) -> dict:
    """
    Обрабатывает входящее сообщение через нужного агента.

    Возвращает:
        {
            "text": str,           # текстовый ответ
            "audio_path": str|None # путь к .mp3 если агент генерировал голос
            "agent": str,          # имя агента
            "agent_label": str,    # человекочитаемое имя
        }
    """
    if agent not in _REGISTRY:
        return {
            "text": f"Агент '{agent}' не найден.",
            "audio_path": None,
            "agent": agent,
            "agent_label": agent,
        }

    # Сохраняем сообщение пользователя
    display_input = user_input or "[Голосовое сообщение]"
    user_msg_id = save_message(agent=agent, role="user", content=display_input, source=source)

    # Вызываем агента
    try:
        result = await _REGISTRY[agent](user_input, voice_path=voice_path, **kwargs)
    except Exception as e:
        logger.error(f"Agent '{agent}' error: {e}", exc_info=True)
        result = {"text": f"❌ Ошибка агента: {e}", "audio_path": None}

    text = result.get("text", "")
    audio_path = result.get("audio_path")

    # Сохраняем ответ агента
    msg_id = save_message(agent=agent, role="assistant", content=text, source=source, audio_path=audio_path)

    return {
        "text": text,
        "audio_path": audio_path,
        "id": msg_id,
        "user_msg_id": user_msg_id,
        "agent": agent,
        "agent_label": AGENT_LABELS.get(agent, agent),
    }
