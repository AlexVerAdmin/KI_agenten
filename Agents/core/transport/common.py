import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Загрузка env
load_dotenv(Path(__file__).parent.parent.parent / ".env.transport")

# --- ПУТИ ---
PROJECT_ROOT = Path(__file__).parent.parent.parent
RUNTIME_SYNC_DIR = PROJECT_ROOT / "runtime_sync"
STATE_DIR = RUNTIME_SYNC_DIR / "state"
INCOMING_DIR = RUNTIME_SYNC_DIR / "incoming"
OUTGOING_DIR = RUNTIME_SYNC_DIR / "outgoing"

# --- МАСКИРОВАНИЕ СЕКРЕТОВ ---
# Список паттернов для поиска секретов (API ключи, пароли и т.д.)
SECRET_PATTERNS = [
    re.compile(r'sk-[a-zA-Z0-9]{32,}', re.IGNORECASE),  # OpenAI keys
    re.compile(r'ghp_[a-zA-Z0-9]{36}', re.IGNORECASE),   # GitHub tokens
    re.compile(r'password\s*[:=]\s*[^\s]+', re.IGNORECASE),
    re.compile(r'key\s*[:=]\s*[^\s]+', re.IGNORECASE),
]

def mask_secrets(text: str) -> str:
    """Заменяет найденные секреты на [MASKED]."""
    if not text:
        return text
    masked_text = text
    for pattern in SECRET_PATTERNS:
        masked_text = pattern.sub("[MASKED]", masked_text)
    return masked_text

# --- РАБОТА СО STATE ---
def load_state(track_name: str) -> dict:
    """Загружает состояние для конкретного трека (copilot, german, career, infra)."""
    state_file = STATE_DIR / f"{track_name}.json"
    if not state_file.exists():
        return {
            "last_id": 0,
            "last_sync_at": None,
            "processed_batches": []
        }
    with open(state_file, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(track_name: str, state: dict):
    """Сохраняет состояние для конкретного трека."""
    state_file = STATE_DIR / f"{track_name}.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

# --- УТИЛИТЫ ---
def ensure_track_dirs(track_name: str):
    """Создает необходимые папки для трека если их нет."""
    (INCOMING_DIR / track_name).mkdir(parents=True, exist_ok=True)
    (OUTGOING_DIR / track_name).mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Runtime Sync: {RUNTIME_SYNC_DIR}")
    
    # Тест маскирования
    test_str = "My key is sk-1234567890abcdef1234567890abcdef and password: admin"
    print(f"Masked: {mask_secrets(test_str)}")
