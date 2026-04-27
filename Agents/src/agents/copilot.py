"""
Агент: Copilot (архитектор проекта).
Регистрируется в router через @register("copilot").

Умеет:
  - читать файлы проекта (только src/) через function calling
  - записывать план в ~/Obsidian/00_Inbox/copilot/YYYY-MM-DD_HH-MM_<slug>.md

Workflow:
  Телефон/Веб → обсуждение → write_plan() → Syncthing → Ноутбук
"""

import os
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from Agents.src.llm import chat_completion

from Agents.src.gateway.router import register
from Agents.src.db.conversations import get_history
from Agents.src.config import (
    OBSIDIAN_VAULT, get_effective_settings,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "copilot"

# Корень проекта внутри контейнера (на VDS) и локально
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", "/app"))
SRC_ROOT = PROJECT_ROOT / "src"

# Папка для планов в Obsidian
PLANS_DIR = Path(OBSIDIAN_VAULT) / "00_Inbox" / "copilot"

# Codebase index — читается один раз при загрузке модуля
_CODEBASE_INDEX = """\
## Структура src/
src/
  config.py              — единая конфигурация (GEMINI_API_KEY, AVAILABLE_MODELS, get_agent_model)
  main.py                — точка входа: Telegram + Web
  agents/
    tutor.py             — учитель немецкого (@register("tutor"), TTS edge_tts)
    career.py            — карьерный коуч (@register("career"), без TTS)
    copilot.py           — ты сам (@register("copilot"))
  gateway/
    router.py            — @register декоратор, AGENT_LABELS, async process()
    bot.py               — Telegram gateway
    web.py               — FastAPI: GET /, WS /ws/{agent}, /api/history, /api/models, /api/settings, DELETE /api/message
  db/
    conversations.py     — SQLite WAL, save_message (AUTO_TRIM 500), get_history, delete_message
  utils/
    compress_session.py  — сжатие staging.md через локальную модель

## Добавление агента
1. src/agents/name.py с @register("name")
2. AGENT_LABELS в router.py
3. import src.agents.name в web.py

## Модели
AsyncOpenAI — всегда. Gemini: base_url=https://generativelanguage.googleapis.com/v1beta/openai/
Local: base_url=LOCAL_MODEL_URL, api_key="local"
"""

SYSTEM_PROMPT = f"""\
Ты Copilot — архитектор проекта Antigravity Agents.
Помогаешь обсуждать архитектуру и код через телефон/веб, когда ноутбук недоступен.
Отвечаешь на русском языке. Будь конкретен и лаконичен.

ПРАВИЛА:
- ВСЕГДА отвечай на ТЕКУЩИЙ вопрос пользователя напрямую.
- История чата — только справочный контекст о прошлых обсуждениях, НЕ список задач для анализа.
- Если вопрос простой (приветствие, уточнение, общий вопрос) — отвечай текстом БЕЗ инструментов.
- Используй read_file только когда нужно посмотреть конкретный файл для ответа.
- Используй write_plan только когда пользователь явно просит записать план.
- Не применяй изменения сам — только обсуждай и записывай план.

## Codebase Index
{_CODEBASE_INDEX}
"""

# ─── Определения инструментов ────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Читает файл проекта из src/. Укажи путь относительно src/, например 'agents/tutor.py'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к файлу относительно src/, например 'agents/tutor.py' или 'config.py'",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_plan",
            "description": "Записывает план изменений в Obsidian для выполнения на ноутбуке.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Краткое название задачи (2-5 слов, будет в имени файла)",
                    },
                    "content": {
                        "type": "string",
                        "description": "Содержимое плана в Markdown",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
]


# ─── Обработчики инструментов ────────────────────────────────────────────────

def _tool_read_file(path: str) -> str:
    """Безопасное чтение файла только из src/."""
    # Защита от path traversal
    safe = Path(path).parts
    if ".." in safe:
        return "ERROR: path traversal не разрешён"

    full_path = SRC_ROOT / path
    # Убеждаемся что файл внутри SRC_ROOT
    try:
        full_path.resolve().relative_to(SRC_ROOT.resolve())
    except ValueError:
        return "ERROR: доступ только к файлам внутри src/"

    if not full_path.exists():
        return f"ERROR: файл не найден: {full_path}"

    try:
        content = full_path.read_text(encoding="utf-8")
        # Ограничиваем размер чтобы не переполнить контекст
        if len(content) > 8000:
            content = content[:8000] + "\n\n... [обрезано, файл слишком большой]"
        return content
    except Exception as e:
        return f"ERROR: {e}"


def _tool_write_plan(title: str, content: str) -> str:
    """Записывает план в Obsidian под постоянным именем.
    Если файл существует — дописывает в конец. Удаляется после выполнения на ноутбуке."""
    try:
        PLANS_DIR.mkdir(parents=True, exist_ok=True)
        # Имя файла = только заголовок, без даты (чтобы дополнять один и тот же файл)
        slug = re.sub(r"[^\w\s-]", "", title)
        slug = re.sub(r"[\s]+", "_", slug.strip())[:60]
        filename = f"{slug}.md"
        filepath = PLANS_DIR / filename

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        footer = (
            "\n\n---\n"
            f"> ⚠️ **Для Copilot на ноутбуке**: после выполнения плана "
            f"удали этот файл `00_Inbox/copilot/{filename}`\n"
        )

        if filepath.exists():
            existing = filepath.read_text(encoding="utf-8")
            # Убираем старый footer перед дополнением
            marker = "\n\n---\n> ⚠️ **Для Copilot на ноутбуке**"
            if marker in existing:
                existing = existing[:existing.rfind(marker)]
            addition = f"\n\n---\n\n## Дополнение {timestamp}\n\n{content}"
            filepath.write_text(existing + addition + footer, encoding="utf-8")
            return f"✅ План дополнен: 00_Inbox/copilot/{filename}"
        else:
            full_content = f"# {title}\n\n_{timestamp}_\n\n{content}{footer}"
            filepath.write_text(full_content, encoding="utf-8")
            return f"✅ План записан: 00_Inbox/copilot/{filename}"
    except Exception as e:
        return f"ERROR: не удалось записать план: {e}"


# ─── Основной процессор ──────────────────────────────────────────────────────

# _make_client removed, logic moved to src.llm


@register("copilot")
async def process(user_input: str, voice_path: str = None, user_id: str = "alex", **kwargs) -> dict:
    cfg = get_effective_settings(AGENT_NAME, user_id)
    model_key   = cfg["model"]
    temperature = float(cfg.get("temperature", 0.5))
    # Системный промпт: из настроек, но всегда дополняем codebase index
    base_prompt = cfg.get("system_prompt", "")
    effective_prompt = base_prompt + f"\n\n## Codebase Index\n{_CODEBASE_INDEX}"

    # Строим историю (фильтруем сообщения-ошибки — они сбивают агента с толку)
    history = get_history(AGENT_NAME, limit=20)
    messages = [{"role": "system", "content": effective_prompt}]
    for msg in history:
        content = msg["content"] or ""
        if content.startswith("❌") or "Достигнут лимит итераций" in content:
            continue
        messages.append({"role": msg["role"], "content": content})
    messages.append({"role": "user", "content": user_input})

    # Агентный цикл: модель может вызывать инструменты несколько раз
    for _ in range(5):  # максимум 5 итераций tool-calling
        response = await chat_completion(
            model=model_key,
            messages=messages,
            tools=TOOLS,
            temperature=temperature,
        )

        msg = response.choices[0].message

        # Если нет вызовов инструментов — финальный ответ
        if not msg.tool_calls:
            text = (msg.content or "").strip()
            if not text:
                # Gemini иногда возвращает None content при работе с tools — retry без tools
                retry = await chat_completion(
                    model=model_key,
                    messages=messages,
                    temperature=temperature,
                )
                text = (retry.choices[0].message.content or "").strip()
            return {"text": text, "audio_path": None}

        # Добавляем ответ модели с tool_calls в историю
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})

        # Выполняем инструменты
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            if tc.function.name == "read_file":
                result = _tool_read_file(args["path"])
            elif tc.function.name == "write_plan":
                result = _tool_write_plan(args["title"], args["content"])
            else:
                result = f"ERROR: неизвестный инструмент {tc.function.name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # Цикл tool-calling исчерпан — принудительно запрашиваем финальный ответ без tools
    messages.append({
        "role": "user",
        "content": "[Системное: ты уже собрал достаточно данных. Сформулируй финальный ответ пользователю. Не вызывай больше инструменты.]",
    })
    final_resp = await chat_completion(
        model=model_key,
        messages=messages,
        temperature=temperature,
    )
    text = (final_resp.choices[0].message.content or "").strip()
    return {"text": text or "Не удалось получить финальный ответ.", "audio_path": None}
