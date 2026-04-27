import os
import sys
import logging
from pathlib import Path
from src.utils.obsidian import sync_code_to_obsidian

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "/home/alex/Документи/Obsidian")
CONTEXT_BANK_DIR = "01_Projects/Agents/02_Context_Bank"

# Директории для сканирования (относительно корня проекта Agents)
FOLDERS_TO_SCAN = ["src", "core"]
# Файлы в корне проекта, которые тоже нужно синхронизировать
ROOT_FILES_TO_SCAN = ["app.py", "bot.py", "config.py", "sync_memory.py"]

def run_sync():
    """
    Автоматически обходит указанные папки и файлы проекта,
    синхронизируя каждый .py файл с соответствующей заметкой в Obsidian.
    """
    print("🚀 Starting Automatic Memory Sync...")
    
    synced_count = 0
    
    # 1. Сканируем директории
    for folder_name in FOLDERS_TO_SCAN:
        folder_path = PROJECT_ROOT / folder_name
        if not folder_path.exists():
            logging.warning(f"Directory not found: {folder_path}")
            continue
            
        for py_file in folder_path.rglob("*.py"):
            # Пропускаем служебные файлы
            if py_file.name.startswith("__") or ".venv" in str(py_file):
                continue
                
            sync_file(py_file)
            synced_count += 1

    # 2. Сканируем отдельные файлы в корне
    for root_file_name in ROOT_FILES_TO_SCAN:
        root_file_path = PROJECT_ROOT / root_file_name
        if root_file_path.exists():
            sync_file(root_file_path)
            synced_count += 1
        else:
            logging.warning(f"Root file not found: {root_file_path}")

    print(f"🏁 Sync finished. Total files processed: {synced_count}")

def sync_file(file_path: Path):
    """
    Определяет путь к заметке и вызывает функцию синхронизации.
    """
    # Имя заметки = имя файла без расширения
    note_name = f"{file_path.stem}.md"
    # Общий путь в Context Bank
    note_path = os.path.join(CONTEXT_BANK_DIR, note_name)
    
    relative_source = file_path.relative_to(PROJECT_ROOT)
    print(f"📦 Processing {relative_source} -> {note_path}...")
    sync_code_to_obsidian(str(file_path), note_path)

if __name__ == "__main__":
    run_sync()
