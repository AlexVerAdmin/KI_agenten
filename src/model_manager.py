import subprocess
import time
import os
import signal
import sys

# Настройки
VENV_PYTHON = "/home/alex/Документи/ICH/SysVSC/Agents/venv/bin/python3"
MODEL_PATH = "/home/alex/Документи/ICH/SysVSC/Agents/models/gemma-4-E4B-it-Q4_K_M.gguf"
PORT = 8000
IDLE_TIMEOUT = 120 # Секунд до выгрузки

server_process = None
last_access_time = 0

def start_server():
    global server_process, last_access_time
    print(f"--- Запуск сервера Gemma 4 (Port {PORT}) ---")
    cmd = [
        VENV_PYTHON, "-m", "llama_cpp.server",
        "--model", MODEL_PATH,
        "--host", "0.0.0.0",
        "--port", str(PORT),
        "--n_ctx", "4096",
        "--n_threads", str(os.cpu_count())
    ]
    server_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    last_access_time = time.time()
    time.sleep(5) # Даем время на загрузку весов

def stop_server():
    global server_process
    if server_process:
        print("--- Выгрузка модели из памяти (Idle Timeout) ---")
        os.kill(server_process.pid, signal.SIGTERM)
        server_process = None

def monitor():
    global last_access_time
    print(f"Монитор RAM запущен. Тайм-аут: {IDLE_TIMEOUT} сек.")
    try:
        while True:
            # В реальном сценарии здесь должен быть перехват обращений к API
            # Но для начала сделаем ручной контроль или простое ожидание
            if server_process and (time.time() - last_access_time > IDLE_TIMEOUT):
                stop_server()
            time.sleep(10)
    except KeyboardInterrupt:
        stop_server()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--start":
        start_server()
        monitor()
    else:
        print("Используйте: python manager.py --start")
