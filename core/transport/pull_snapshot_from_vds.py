import os
import shutil
import subprocess
from pathlib import Path
from common import load_state, save_state, PROJECT_ROOT, INCOMING_DIR

# --- НАСТРОЙКИ VDS ---
VDS_HOST = os.environ.get("VDS_SSH_HOST", "10.8.0.1")
VDS_PORT = os.environ.get("VDS_SSH_PORT", "31117")
VDS_USER = os.environ.get("VDS_SSH_USER", "alexadmin")
VDS_KEY = os.path.expanduser(os.path.expandvars(os.environ.get("VDS_SSH_KEY_PATH", "")))
VDS_REMOTE_EXPORT = os.environ.get("VDS_RUNTIME_EXPORT", "/home/alexadmin/stack/Agents/runtime_sync/export")

def pull_from_vds(track_name: str) -> list:
    """Забирает файлы из VDS через SCP и удаляет их на VDS после успеха."""
    local_target_dir = INCOMING_DIR / track_name
    local_target_dir.mkdir(parents=True, exist_ok=True)
    
    remote_src_dir = f"{VDS_REMOTE_EXPORT}/{track_name}"
    remote_src_wildcard = f"{remote_src_dir}/*"
    
    print(f"--- [PULL] Track: {track_name} from {VDS_HOST}:{VDS_PORT} ---")
    
    # 1. Сначала проверяем, есть ли файлы на VDS, чтобы не спамить SCP ошибками
    check_cmd = ["ssh", "-P", VDS_PORT] if "VDS_PORT" in locals() else ["ssh", "-p", VDS_PORT] 
    # В Windows ssh использует -p (маленькая), в scp -P (большая). Исправим для универсальности:
    ssh_base = ["ssh", "-p", VDS_PORT]
    if VDS_KEY:
        ssh_base.extend(["-i", os.path.abspath(VDS_KEY)])
    
    ls_cmd = ssh_base + [f"{VDS_USER}@{VDS_HOST}", f"ls {remote_src_wildcard}"]
    
    ls_result = subprocess.run(ls_cmd, capture_output=True, text=True)
    if ls_result.returncode != 0:
        print(f"[{track_name}] No files to pull (or directory empty/missing on VDS).")
        return []

    # 2. Команда SCP для копирования
    scp_cmd = ["scp", "-P", VDS_PORT]
    if VDS_KEY:
        abs_key = os.path.abspath(VDS_KEY)
        scp_cmd.extend(["-i", abs_key])
    
    scp_cmd.extend([
        f"{VDS_USER}@{VDS_HOST}:{remote_src_wildcard}", 
        str(local_target_dir)
    ])
    
    try:
        result = subprocess.run(scp_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            files_pulled = [f.name for f in local_target_dir.iterdir()]
            print(f"Successfully pulled {len(files_pulled)} files to {local_target_dir}")
            
            # 3. УДАЛЕНИЕ на VDS после успешного копирования
            print(f"[{track_name}] Cleaning up VDS export directory...")
            rm_cmd = ssh_base + [f"{VDS_USER}@{VDS_HOST}", f"rm {remote_src_wildcard}"]
            subprocess.run(rm_cmd, capture_output=True)
            return files_pulled
        else:
            print(f"SCP Error: {result.stderr}")
    except Exception as e:
        print(f"Execution Error: {str(e)}")
        
    return []

if __name__ == "__main__":
    # Тест
    # Создать тестовый файл в симуляции VDS
    sim_vds_dir = PROJECT_ROOT / "temp" / "vds_simulation" / "export" / "copilot"
    sim_vds_dir.mkdir(parents=True, exist_ok=True)
    with open(sim_vds_dir / "test_batch_001.json", "w", encoding="utf-8") as f:
        f.write('{"test": "data", "secrets": "sk-12345"}')
        
    pull_from_vds("copilot")
