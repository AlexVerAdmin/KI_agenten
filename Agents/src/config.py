"""
Централизованная конфигурация проекта.
Читает из переменных окружения (загружаются .env в main.py).
"""

import os

# ─── Модели ────────────────────────────────────────────────────────────────

# Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_MODEL_DEFAULT = os.environ.get("DEFAULT_AGENT_MODEL", "gemini/gemini-3-flash-preview")

# Локальная модель (llama-cpp, OpenAI-совместимый API)
LOCAL_MODEL_URL = os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1")
LOCAL_MODEL_NAME = os.environ.get("LOCAL_MODEL_NAME", "gemma-4")

# Список доступных моделей для UI (LiteLLM format: provider/model)
# Обновлено 2026-04-24: убраны deprecated модели
AVAILABLE_MODELS = {
    # Gemini (актуальные на апрель 2026)
    "gemini/gemini-2.5-flash":          "Gemini 2.5 Flash (fast, cheap)",
    "gemini/gemini-2.5-pro":            "Gemini 2.5 Pro (smart)",
    "gemini/gemini-3-flash-preview":    "Gemini 3 Flash Preview (newest)",
    # Anthropic Claude (актуальные на апрель 2026, проверено через API)
    # claude-3-7-sonnet-20250219 — НЕДОСТУПЕН для этого ключа
    "anthropic/claude-sonnet-4-5-20250929": "Claude Sonnet 4.5",
    "anthropic/claude-sonnet-4-6":          "Claude Sonnet 4.6 (latest)",
    # Локальная
    "local": f"Local: {LOCAL_MODEL_NAME} (:{LOCAL_MODEL_URL.split(':')[-1].split('/')[0]})",
}

# Список TTS-моделей для UI
TTS_MODELS = {
    "gemini-3.1-flash-tts-preview": "Gemini TTS 3.1 Flash (new)",
    "gemini-2.5-flash-preview-tts": "Gemini TTS 2.5 Flash",
    "gemini-2.5-pro-preview-tts":   "Gemini TTS 2.5 Pro",
    "edge-tts":                     "Edge TTS (fallback, offline)",
}

# ─── Пути ──────────────────────────────────────────────────────────────────

OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", "/home/alex/Документи/ICH/SysVSC/obsidian_vault_simulation")
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "/home/alex/Документи/ICH/SysVSC/Agents/data/conversations.sqlite")

# ─── Настройки агентов ──────────────────────────────────────────────────────

import json
from pathlib import Path

_data_dir = Path(SQLITE_DB_PATH).parent
_global_settings_path = _data_dir / "agent_settings.json"
_user_settings_path   = _data_dir / "user_settings.json"

# Языки интерфейса
UI_LANGUAGES = {
    "uk": "Українська",
    "de": "Deutsch",
    "en": "English",
    "pt": "Português",
}

# Дефолтные настройки агентов (используются если ничего не сохранено)
AGENT_DEFAULTS: dict[str, dict] = {
    "tutor": {
        "model":         GEMINI_MODEL_DEFAULT,
        "temperature":   0.7,
        "max_tokens":    8192,
        "system_prompt": (
            "# System Prompt: German Language Tutor Agent\n\n"
            "## ROLE & IDENTITY\n"
            "You are Max — a demanding, results-driven German language tutor and coach. "
            "You are not a chatbot that makes the user feel good. You are a professional who gets results. "
            "You motivate through honest feedback, measurable progress, and real challenges — not compliments.\n\n"
            "Your student: Alex — a data analyst, B2 certificate holder (but self-assessed as 'rusty'), "
            "living in Germany, actively seeking employment as a Data Analyst. Daily sessions. "
            "Goal: communicate clearly and be understood — not to speak perfectly.\n\n"
            "Your mission: take Alex from 'rusty B2' to confident B2+ spoken fluency in the shortest time possible, "
            "with a specific focus on professional and everyday life in Germany.\n\n"
            "## CORE PHILOSOPHY\n"
            "1. Communication over perfection.\n"
            "2. Lexical chunks before isolated words.\n"
            "3. Output-first sessions.\n"
            "4. Implicit grammar.\n"
            "5. Real-world tasks.\n"
            "6. Spaced repetition mindset.\n"
            "7. Experiment freely.\n\n"
            "## LANGUAGE OF INTERACTION\n"
            "Mix of German (practice) and Russian (explanations). "
            "Phase 1 target: 50% German / 50% Russian.\n\n"
            "Full methodology and phases are documented in Obsidian. Always check progress.md and vocabulary.md."
        ),
        "tts_voice":     "Fenrir",
        "tts_lang":      "de-DE",
        "ui_lang":       "uk",
        "realtime_enabled": False,
        "realtime_silence_ms": 2000,
        "realtime_speech_rate": 1.0,
        "realtime_voice_mode": "auto-pause",
    },
    "career": {
        "model":         GEMINI_MODEL_DEFAULT,
        "temperature":   0.7,
        "max_tokens":    8192,
        "system_prompt": (
            "Ти досвідчений кар'єрний коуч. Допомагаєш людям з пошуком роботи, "
            "підготовкою до співбесід, складанням резюме, розвитком кар'єри "
            "та професійним зростанням. "
            "Відповідай українською мовою. Будь конкретним і практичним. "
            "Задавай уточнюючі питання якщо потрібно більше контексту. "
            "Максимум 4-5 речень за раз, якщо не просять докладніше."
        ),
        "ui_lang":       "uk",
    },
    "copilot": {
        "model":         GEMINI_MODEL_DEFAULT,
        "temperature":   0.5,
        "max_tokens":    8192,
        "system_prompt": (
            "Ти Copilot — архітектор проекту Antigravity Agents. "
            "Допомагаєш обговорювати архітектуру та код через телефон/веб, коли ноутбук недоступний. "
            "Відповідай українською мовою. Будь конкретним і лаконічним. "
            "Коли обговорення завершено і є конкретний план — використовуй write_plan. "
            "Не застосовуй зміни сам — лише обговорюй і записуй план."
        ),
        "ui_lang":       "uk",
    },
}

# Поля доступные для per-user переопределения
USER_OVERRIDABLE_FIELDS = {
    "model", "system_prompt", "tts_voice", "tts_lang", "ui_lang",
    "realtime_enabled", "realtime_silence_ms", "realtime_speech_rate", "realtime_voice_mode"
}


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_effective_settings(agent: str, user_id: str = "alex") -> dict:
    """
    Возвращает итоговые настройки агента для пользователя:
    AGENT_DEFAULTS → глобальные настройки → пользовательские переопределения.
    """
    result = dict(AGENT_DEFAULTS.get(agent, {}))
    result.setdefault("model", GEMINI_MODEL_DEFAULT)

    # Применяем глобальные настройки
    global_data = _load_json(_global_settings_path)
    for k, v in global_data.get(agent, {}).items():
        result[k] = v

    # Применяем пользовательские переопределения (только разрешённые поля)
    user_data = _load_json(_user_settings_path)
    for k, v in user_data.get(user_id, {}).get(agent, {}).items():
        if k in USER_OVERRIDABLE_FIELDS:
            result[k] = v

    return result


def save_global_settings(agent: str, fields: dict) -> None:
    """Сохраняет глобальные настройки агента (admin)."""
    data = _load_json(_global_settings_path)
    data.setdefault(agent, {}).update(fields)
    _save_json(_global_settings_path, data)


def save_user_setting(user_id: str, agent: str, fields: dict) -> None:
    """Сохраняет пользовательские переопределения для агента."""
    data = _load_json(_user_settings_path)
    data.setdefault(user_id, {}).setdefault(agent, {}).update(
        {k: v for k, v in fields.items() if k in USER_OVERRIDABLE_FIELDS}
    )
    _save_json(_user_settings_path, data)


def reset_user_setting(user_id: str, agent: str, field: str) -> None:
    """Сбрасывает пользовательское переопределение одного поля."""
    data = _load_json(_user_settings_path)
    data.get(user_id, {}).get(agent, {}).pop(field, None)
    _save_json(_user_settings_path, data)


# ─── Обратная совместимость ──────────────────────────────────────────────────

def get_agent_model(agent: str, user_id: str = "alex") -> str:
    return get_effective_settings(agent, user_id).get("model", GEMINI_MODEL_DEFAULT)


def set_agent_model(agent: str, model: str) -> None:
    save_global_settings(agent, {"model": model})
