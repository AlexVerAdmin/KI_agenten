import os
import sqlite3
import json
import time
import hashlib
from pathlib import Path

# --- ПУТИ (На VDS используем /home/alexadmin/...) ---
PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH = PROJECT_ROOT / "chroma_db" / "chroma.sqlite3" # Предположим основная БД здесь
EXPORT_DIR = PROJECT_ROOT / "runtime_sync" / "export"
STATE_FILE = PROJECT_ROOT / "runtime_sync" / "state" / "vds_export_state.json"

# Папки для мониторинга (Obsidian Vault и Copilot History)
COPILOT_HISTORY_FILE = PROJECT_ROOT / "copilot_history.md"
OBSIDIAN_VAULT_DIR = PROJECT_ROOT / "obsidian_vault_simulation"

def load_export_state():
    if not STATE_FILE.exists():
        return {"last_sqlite_id": 0, "last_copilot_offset": 0, "obsidian_files": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_export_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

def export_sqlite_batch(state):
    """Экспорт новых записей из SQLite."""
    if not DB_PATH.exists():
        return 0
    
    # ПРИМЕЧАНИЕ: Название таблицы и полей должно соответствовать вашей БД
    # Здесь пример для гипотетической таблицы chat_history
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_history'")
        if not cursor.fetchone():
            return 0
            
        cursor.execute("SELECT id, timestamp, role, content FROM chat_history WHERE id > ? ORDER BY id ASC", (state["last_sqlite_id"],))
        rows = cursor.fetchall()
        
        if rows:
            batch_id = int(time.time())
            batch_data = [dict(zip(["id", "timestamp", "role", "content"], r)) for r in rows]
            
            output_file = EXPORT_DIR / "infra" / f"sqlite_batch_{batch_id}.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(batch_data, f, indent=4, ensure_ascii=False)
            
            state["last_sqlite_id"] = rows[-1][0]
            return len(rows)
    finally:
        conn.close()
    return 0

def export_copilot_history_delta(state):
    """Экспорт новых строк из copilot_history.md."""
    if not COPILOT_HISTORY_FILE.exists():
        return False
    
    file_size = COPILOT_HISTORY_FILE.stat().st_size
    last_offset = state.get("last_copilot_offset", 0)
    
    if file_size <= last_offset:
        return False

    with open(COPILOT_HISTORY_FILE, "r", encoding="utf-8") as f:
        f.seek(last_offset)
        new_content = f.read()
    
    if new_content.strip():
        batch_id = int(time.time())
        output_file = EXPORT_DIR / "copilot" / f"copilot_delta_{batch_id}.txt"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        state["last_copilot_offset"] = file_size
        return True
    return False

def export_obsidian_changes(state):
    """Экспорт измененных файлов Obsidian Vault Simulation (VDS)."""
    if not OBSIDIAN_VAULT_DIR.exists():
        return 0
    
    changed_count = 0
    obs_files_state = state.get("obsidian_files", {})
    
    for md_file in OBSIDIAN_VAULT_DIR.rglob("*.md"):
        rel_path = str(md_file.relative_to(OBSIDIAN_VAULT_DIR))
        mtime = md_file.stat().st_mtime
        
        if rel_path not in obs_files_state or mtime > obs_files_state[rel_path]:
            # Файл новый или изменен
            batch_id = int(time.time())
            target_file = EXPORT_DIR / "infra" / f"obs_sync_{batch_id}_{md_file.name}"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Копируем файл в экспорт
            import shutil
            shutil.copy2(md_file, target_file)
            
            obs_files_state[rel_path] = mtime
            changed_count += 1
            
    state["obsidian_files"] = obs_files_state
    return changed_count

if __name__ == "__main__":
    print("--- Starting VDS Incremental Export ---")
    state = load_export_state()
    
    q_count = export_sqlite_batch(state)
    print(f"Exported {q_count} new SQLite rows.")
    
    c_updated = export_copilot_history_delta(state)
    print(f"Copilot history updated: {c_updated}")
    
    o_count = export_obsidian_changes(state)
    print(f"Obsidian changes: {o_count} files.")
    
    save_export_state(state)
    print("--- Export Done ---")
