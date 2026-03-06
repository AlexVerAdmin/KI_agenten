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
    
    check_port(target_url, target_port)
    
    if worker_url != "none":
        w_ip = worker_url.replace("http://", "").split(":")[0]
        w_port = 8001
        check_port(w_ip, w_port)
