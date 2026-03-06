import socket
import os
from config import config

def check_port(ip, port):
    print(f"🔍 Testing connection to {ip}:{port}...")
    try:
        with socket.create_connection((ip, port), timeout=5):
            print(f"✅ SUCCESS: Port {port} is OPEN on {ip}")
            return True
    except socket.timeout:
        print(f"❌ ERROR: Timeout reaching {ip}:{port}")
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
    return False

if __name__ == "__main__":
    # Get IP from config or env
    target_url = config.local_server_url.replace("http://", "").split(":")[0]
    target_port = 11434
    
    # Also check worker port if remote_worker_url is set
    worker_url = config.remote_worker_url
    
    # 1. Базовая проверка порта
    if check_port(target_url, target_port):
        print("\n🌐 Testing full HTTP Request to Ollama API...")
        import requests
        try:
            # Пытаемся получить список моделей для начала
            r_tags = requests.get(config.local_server_url + "/api/tags", timeout=5)
            if r_tags.status_code == 200:
                models = [m['name'] for m in r_tags.json().get('models', [])]
                print(f"🟢 Available models on your Home Server: {models}")
            
            print(f"🔍 Sending test prompt to Ollama...")
            payload = {"model": "llama3.1:8b", "prompt": "Hi", "stream": False}
            r = requests.post(config.local_server_url + "/api/generate", json=payload, timeout=15)
            print(f"🟢 STATUS: {r.status_code}")
            if r.status_code == 200:
                print(f"🟢 RESPONSE: {r.json().get('response', 'Empty response field')}")
            else:
                print(f"🔴 ERROR BODY: {r.text}")
        except Exception as e:
            print(f"🔴 HTTP ERROR: {str(e)}")

