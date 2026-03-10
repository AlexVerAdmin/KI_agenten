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

def process_batch(track_name: str):
    """Берет файлы из incoming/{track} и генерирует summary в outgoing/{track}."""
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
        print(f"[{track_name}] Processing {file_path.name}...")
        
        # 1. Читаем данные
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # 2. Маскируем секреты перед любой обработкой
        safe_content = mask_secrets(content)
        
        # 3. Суммаризация
        summary = summarizer.generate_summary(safe_content)
        
        # 4. Сохраняем результат в outgoing
        timestamp = int(time.time())
        output_file = outgoing_track_dir / f"summary_{timestamp}_{file_path.name}.md"
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary)
            
        print(f"[{track_name}] Saved summary to {output_file.name}")
        
        # 5. Обновляем состояние
        state["processed_batches"].append({
            "filename": file_path.name,
            "processed_at": timestamp,
            "summary_file": output_file.name
        })
        
        # 6. В реальности мы бы удалили или переместили архив
        # Здесь в Phase 1 симуляция: удаляем из incoming
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
