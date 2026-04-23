"""
Централизованная конфигурация проекта.
Читает из переменных окружения (загружаются .env в main.py).
"""

import os

# ─── Модели ────────────────────────────────────────────────────────────────

# Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL_DEFAULT = os.environ.get("DEFAULT_AGENT_MODEL", "gemini-2.5-flash")

# Локальная модель (llama-cpp, OpenAI-совместимый API)
LOCAL_MODEL_URL = os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1")
LOCAL_MODEL_NAME = os.environ.get("LOCAL_MODEL_NAME", "gemma-4")

# Список доступных моделей для UI
AVAILABLE_MODELS = {
    "gemini-2.5-flash":          "Gemini 2.5 Flash (fast, stable)",
    "gemini-2.5-pro":            "Gemini 2.5 Pro (smart, slow)",
    "gemini-3-flash-preview":    "Gemini 3 Flash Preview (new)",
    "gemini-3.1-pro-preview":    "Gemini 3.1 Pro Preview (new, smart)",
    "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite Preview (new, fast)",
    "local":                     f"Local: {LOCAL_MODEL_NAME} (:{LOCAL_MODEL_URL.split(':')[-1].split('/')[0]})",
}

# Список TTS-моделей для UI
TTS_MODELS = {
    "gemini-3.1-flash-tts-preview": "Gemini TTS 3.1 Flash (new)",
    "gemini-2.5-flash-preview-tts": "Gemini TTS 2.5 Flash",
    "gemini-2.5-pro-preview-tts":   "Gemini TTS 2.5 Pro",
    "edge-tts":                     "Edge TTS (fallback, offline)",
}

# ─── Пути ──────────────────────────────────────────────────────────────────

OBSIDIAN_VAULT = os.environ.get("OBSIDIAN_VAULT_PATH", "/home/alex/Obsidian")
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", "/app/data/conversations.sqlite")

# ─── Настройки агентов (хранятся в agent_settings.json рядом с БД) ─────────

import json
from pathlib import Path

_settings_path = Path(SQLITE_DB_PATH).parent / "agent_settings.json"


def get_agent_model(agent: str) -> str:
    """Возвращает модель для агента. Если не задана — дефолт из .env."""
    try:
        if _settings_path.exists():
            data = json.loads(_settings_path.read_text())
            return data.get(agent, {}).get("model", GEMINI_MODEL_DEFAULT)
    except Exception:
        pass
    return GEMINI_MODEL_DEFAULT


def set_agent_model(agent: str, model: str) -> None:
    """Сохраняет выбор модели для агента."""
    try:
        _settings_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if _settings_path.exists():
            data = json.loads(_settings_path.read_text())
        data.setdefault(agent, {})["model"] = model
        _settings_path.write_text(json.dumps(data, indent=2))
    except Exception:
        pass
