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
    """Забирает файлы из VDS через SCP."""
    local_target_dir = INCOMING_DIR / track_name
    local_target_dir.mkdir(parents=True, exist_ok=True)
    
    remote_src = f"{VDS_REMOTE_EXPORT}/{track_name}/*"
    
    print(f"--- [PULL] Track: {track_name} from {VDS_HOST}:{VDS_PORT} ---")
    
    # Команда SCP для копирования всех файлов из папки экпорта
    scp_cmd = ["scp", "-P", VDS_PORT]
    if VDS_KEY:
        # Используем абсолютный путь для Windows
        abs_key = os.path.abspath(VDS_KEY)
        scp_cmd.extend(["-i", abs_key])
    
    scp_cmd.extend([
        f"{VDS_USER}@{VDS_HOST}:{remote_src}", 
        str(local_target_dir)
    ])
    
    files_pulled = []
    try:
        # Пытаемся забрать файлы
        result = subprocess.run(scp_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            # После успешного скачивания, нужно было бы удалить их на VDS, 
            # но SCP не умеет удалять. В Фазе 2 пока просто качаем.
            files_pulled = [f.name for f in local_target_dir.iterdir()]
            print(f"Successfully pulled files to {local_target_dir}")
        else:
            if "No such file or directory" in result.stderr or "not matched" in result.stderr:
                print("No new files to pull or remote directory empty.")
            else:
                print(f"SCP Error: {result.stderr}")
    except Exception as e:
        print(f"Execution Error: {str(e)}")
        
    return files_pulled

if __name__ == "__main__":
    # Тест
    # Создать тестовый файл в симуляции VDS
    sim_vds_dir = PROJECT_ROOT / "temp" / "vds_simulation" / "export" / "copilot"
    sim_vds_dir.mkdir(parents=True, exist_ok=True)
    with open(sim_vds_dir / "test_batch_001.json", "w", encoding="utf-8") as f:
        f.write('{"test": "data", "secrets": "sk-12345"}')
        
    pull_from_vds("copilot")
