import os
import shutil
import subprocess
import time
from pathlib import Path
from common import (
    load_state, save_state, PROJECT_ROOT, OUTGOING_DIR
)

# --- НАСТРОЙКИ VDS ---
# Используем те же переменные из .env.transport
VDS_HOST = os.environ.get("VDS_SSH_HOST", "10.8.0.1")
VDS_PORT = os.environ.get("VDS_SSH_PORT", "31117")
VDS_USER = os.environ.get("VDS_SSH_USER", "alexadmin")
VDS_KEY = os.path.expanduser(os.path.expandvars(os.environ.get("VDS_SSH_KEY_PATH", "")))
VDS_REMOTE_IMPORT = os.environ.get("VDS_RUNTIME_IMPORT", "/home/alexadmin/AntigravityAgents/runtime_sync/import")

def push_to_vds(track_name: str) -> list:
    """Отправляет файлы на VDS через SCP."""
    local_source_dir = OUTGOING_DIR / track_name
    local_source_dir.mkdir(parents=True, exist_ok=True)
    
    remote_dst = f"{VDS_USER}@{VDS_HOST}:{VDS_REMOTE_IMPORT}/{track_name}/"
    
    print(f"--- [PUSH] Track: {track_name} to {VDS_HOST}:{VDS_PORT} ---")
    
    files_pushed = []
    # Перебираем файлы в outgoing/{track}
    files_list = [str(f) for f in local_source_dir.iterdir() if f.is_file()]
    
    if not files_list:
        print(f"No summary files to push for track {track_name}.")
        return []

    scp_cmd = ["scp", "-P", VDS_PORT]
    if VDS_KEY:
        # Используем абсолютный путь для Windows
        abs_key = os.path.abspath(VDS_KEY)
        scp_cmd.extend(["-i", abs_key])
        
    scp_cmd.extend(files_list + [remote_dst])
    
    try:
        result = subprocess.run(scp_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Successfully pushed {len(files_list)} files.")
            # После успешного пуша, очищаем локальный outgoing
            for f_path in files_list:
                Path(f_path).unlink()
                files_pushed.append(Path(f_path).name)
        else:
            print(f"SCP Error: {result.stderr}")
    except Exception as e:
        print(f"Execution Error: {str(e)}")
        
    return files_pushed

if __name__ == "__main__":
    # Тест
    # Сначала создадим тестовый файл в outgoing/copilot
    test_outgoing = OUTGOING_DIR / "copilot" / "summary_test_001.md"
    with open(test_outgoing, "w", encoding="utf-8") as f:
        f.write("# Summary Test 001\n- User: Hello\n- Agent: Hello there!")
        
    push_to_vds("copilot")
