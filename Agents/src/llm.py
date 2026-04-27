import os
import logging
import asyncio
import aiohttp
import litellm
from Agents.src.config import GEMINI_API_KEY, ANTHROPIC_API_KEY, LOCAL_MODEL_URL, LOCAL_MODEL_NAME

logger = logging.getLogger(__name__)

# Устанавливаем ключи для LiteLLM
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

def _normalize_model(model: str) -> str:
    """
    Добавляет провайдер-префикс к старым именам моделей без него.
    Приводит к формату, который понимает LiteLLM.
    """
    if not model:
        return "gemini/gemini-1.5-flash"
    
    if "/" in model or model == "local":
        return model  # уже нормализовано или локальная заглушка
    
    # Маппинг старых имен
    if model.startswith("gemini-"):
        return f"gemini/{model}"
    if model.startswith("claude-"):
        return f"anthropic/{model}"
    
    return model

async def chat_completion(
    model: str,
    messages: list[dict],
    tools: list | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    **kwargs
):
    """
    Универсальная функция для вызова LLM.
    """
    model = _normalize_model(model)
    
    params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs
    }
    
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"

    # Обработка локальной модели
    if model == "local":
        # Проверяем доступность перед вызовом
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{LOCAL_MODEL_URL}/models", timeout=aiohttp.ClientTimeout(total=3)
                ) as resp:
                    if resp.status >= 400:
                        raise ConnectionError()
        except Exception:
            raise litellm.InternalServerError(
                message=(
                    f"⚠️ Локальная модель недоступна ({LOCAL_MODEL_URL}). "
                    "Она работает только на ноутбуке. Выбери Gemini или Claude."
                ),
                llm_provider="openai",
                model=LOCAL_MODEL_NAME,
            )
        params["model"] = f"openai/{LOCAL_MODEL_NAME}"
        params["api_base"] = LOCAL_MODEL_URL
        params["api_key"] = "local"
        # Локальная модель: контекст 4096 — обрезаем историю и ответ
        params["max_tokens"] = min(params.get("max_tokens", 8192), 1024)
        # Оставляем: system + последние 6 сообщений (3 пары user/assistant) + текущий user
        msgs = params["messages"]
        system_msgs = [m for m in msgs if m["role"] == "system"]
        other_msgs = [m for m in msgs if m["role"] != "system"]
        params["messages"] = system_msgs + other_msgs[-7:]
    
    try:
        logger.info(f"LLM Call: {params['model']}")
        response = await litellm.acompletion(**params)
        return response
    except Exception as e:
        logger.error(f"LiteLLM Error ({model}): {e}")
        raise e
