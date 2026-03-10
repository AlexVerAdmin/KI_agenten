import os
import shutil
import json
import time
from pathlib import Path
from common import (
    load_state, save_state, INCOMING_DIR, OUTGOING_DIR, 
    mask_secrets, STATE_DIR, PROJECT_ROOT
)

# Импорт заготовки суммаризатора
# В реальности мы будем импортировать логику из core/memory_system/summarizer.py
import sys
sys.path.append(str(PROJECT_ROOT / "core" / "memory_system"))

try:
    from summarizer import Summarizer  # Предположим у нас есть класс Summarizer
except ImportError:
    # Заглушка: если не нашли боевой суммаризатор, сделаем свой
    class Summarizer:
        def generate_summary(self, text: str) -> str:
            return f"--- [SIMULATED SUMMARY] ---\nContent length: {len(text)}"

# Путь к вашему основному Obsidian Vault (Мастер-копия на сервере)
MASTER_OBSIDIAN_DIR = Path(os.environ.get("OBSIDIAN_VAULT_PATH", PROJECT_ROOT / "history" / "obsidian_master"))

def process_batch(track_name: str):
    """Берет файлы из incoming/{track} и распределяет их по назначению."""
    incoming_track_dir = INCOMING_DIR / track_name
    outgoing_track_dir = OUTGOING_DIR / track_name
    
    incoming_track_dir.mkdir(parents=True, exist_ok=True)
    outgoing_track_dir.mkdir(parents=True, exist_ok=True)

    state = load_state(track_name)
    summarizer = Summarizer()
    
    files_to_process = sorted([f for f in incoming_track_dir.iterdir() if f.is_file()])
    
    if not files_to_process:
        print(f"[{track_name}] No files to process in {incoming_track_dir}")
        return

    for file_path in files_to_process:
        filename = file_path.name
        print(f"[{track_name}] Routing {filename}...")
        
        # 1. МАРШРУТИЗАЦИЯ
        
        # СЛУЧАЙ А: Файлы Obsidian (приходят в infra)
        if filename.startswith("obs_sync_"):
            # Извлекаем оригинальное имя (удаляем префикс obs_sync_timestamp_)
            # Пример: obs_sync_123456_test.md -> test.md
            parts = filename.split("_")
            original_name = "_".join(parts[3:]) if len(parts) > 3 else filename
            
            target_path = MASTER_OBSIDIAN_DIR / original_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(file_path, target_path)
            print(f"  -> [OBSIDIAN] Synced to Master Vault: {target_path}")
            
        # СЛУЧАЙ Б: Дельта истории Copilot
        elif filename.startswith("copilot_delta_"):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            safe_content = mask_secrets(content)
            summary = summarizer.generate_summary(safe_content)
            
            timestamp = int(time.time())
            output_file = outgoing_track_dir / f"summary_{timestamp}_{filename}.md"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"  -> [SUMMARY] Created summary for history delta: {output_file.name}")

        # СЛУЧАЙ В: SQLite батчи
        elif filename.startswith("sqlite_batch_"):
            print(f"  -> [SQLITE] Processing structured logs (TBD logic)...")
            # Здесь можно добавить логику вставки в локальную БД если нужно

        # 2. ОЧИСТКА И ОБНОВЛЕНИЕ STATE
        state["processed_batches"].append({
            "filename": filename,
            "processed_at": int(time.time())
        })
        file_path.unlink()
        
    save_state(track_name, state)

if __name__ == "__main__":
    # Локальный тест для copilot
    # Сначала создадим тестовый файл в incoming/copilot
    test_incoming = INCOMING_DIR / "copilot" / "test_batch_local_001.txt"
    with open(test_incoming, "w", encoding="utf-8") as f:
        f.write("User: Привет!\nAgent: Привет, я Herr Max Klein. Давай учить немецкий!")
        
    process_batch("copilot")
    process_batch("german")
    process_batch("career")
