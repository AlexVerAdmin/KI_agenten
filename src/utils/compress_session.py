"""
Сжатие session_staging.md через локальную модель (Gemma 4 :8000).
Записывает результат в ~/Obsidian/00_Inbox/memory_update.md.
Сбрасывает staging после успеха.

Запуск: python -m src.utils.compress_session
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI

# Пути
STAGING = Path.home() / "Obsidian" / "00_Inbox" / "session_staging.md"
OUTPUT = Path.home() / "Obsidian" / "00_Inbox" / "memory_update.md"
LOCK = Path("/tmp/compress_session.lock")

# Настройки модели — читаем из .env если доступно
def _load_env():
    env_file = Path(__file__).parents[2] / ".env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env

_env = _load_env()
LOCAL_MODEL_URL = _env.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1")
LOCAL_MODEL_NAME = _env.get("LOCAL_MODEL_NAME", "gemma-4")

PROMPT = """Ты — AI-архивариус. Проанализируй сырые заметки сессии разработки ниже.
Создай структурированную выжимку для долгосрочной памяти в формате:

## Завершённые задачи
- ...

## Ключевые факты и решения
- ...

## Новые грабли (проблемы и решения)
- Проблема: ... → Решение: ...

## Отложено / следующий шаг
- ...

Будь кратким. Только факты. Не добавляй ничего, чего нет в заметках.

--- ЗАМЕТКИ СЕССИИ ---
{content}
--- КОНЕЦ ЗАМЕТОК ---"""


def is_staging_empty(text: str) -> bool:
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#") and not l.startswith("<!--")]
    return len(lines) == 0


def compress():
    # Проверяем lock (защита от повторного запуска)
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < 3600:  # 1 час
            print("[compress] Lock active, skipping.")
            return False
        LOCK.unlink()

    if not STAGING.exists():
        print("[compress] staging.md not found, skipping.")
        return False

    content = STAGING.read_text(encoding="utf-8")
    if is_staging_empty(content):
        print("[compress] staging.md is empty, nothing to compress.")
        return False

    print(f"[compress] Compressing staging.md via {LOCAL_MODEL_NAME} @ {LOCAL_MODEL_URL} ...")

    # Создаём lock
    LOCK.write_text(datetime.now().isoformat())

    try:
        client = OpenAI(base_url=LOCAL_MODEL_URL, api_key="local")
        response = client.chat.completions.create(
            model=LOCAL_MODEL_NAME,
            messages=[{"role": "user", "content": PROMPT.format(content=content)}],
            max_tokens=1024,
            temperature=0.3,
        )
        summary = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[compress] ERROR calling model: {e}")
        LOCK.unlink(missing_ok=True)
        return False

    # Записываем результат
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        f"# Memory Update — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{summary}\n",
        encoding="utf-8"
    )

    # Сбрасываем staging
    STAGING.write_text(
        f"# Session Staging — очищен {datetime.now().strftime('%Y-%m-%d')}\n"
        "<!-- Сырые заметки. Будут сжаты compress_session.py при следующем запуске -->\n",
        encoding="utf-8"
    )

    LOCK.unlink(missing_ok=True)
    print(f"[compress] Done. memory_update.md written to {OUTPUT}")
    return True


if __name__ == "__main__":
    ok = compress()
    sys.exit(0 if ok else 1)
