import os
import subprocess
import requests
import json
from typing import Optional, Dict, Any
from config import config

class AdminTools:
    """
    Класс инструментов для системных агентов (vds_admin и local_admin).
    Реализует безопасное выполнение команд с логикой подтверждения.
    """

    @staticmethod
    def check_connection(host_url: str) -> str:
        """Проверка доступности узла (VDS или Local). Передайте полный URL, например http://10.0.0.2:11434"""
        if not host_url.startswith("http"):
            host_url = f"http://{host_url}"
        
        try:
            response = requests.get(host_url, timeout=5)
            return f"Узел {host_url} ДОСТУПЕН. Код ответа: {response.status_code}"
        except Exception as e:
            return f"Узел {host_url} НЕДОСТУПЕН. Ошибка: {str(e)}"

    @staticmethod
    def get_docker_status(is_local: bool = False) -> str:
        """Получение списка контейнеров на текущем или удаленном (через VPN) хосте."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Image}}"],
                capture_output=True, text=True, check=True
            )
            return result.stdout
        except Exception as e:
            return f"Ошибка Docker: {str(e)}"

    @staticmethod
    def get_gpu_info() -> str:
        """Получение данных о GPU через nvidia-smi (только для локального сервера)."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            return result.stdout
        except FileNotFoundError:
            return "NVIDIA GPU не найден или драйверы не установлены."
        except Exception as e:
            return f"Ошибка при запросе GPU: {str(e)}"

    @staticmethod
    def request_shell_execution(command: str, reason: str) -> Dict[str, Any]:
        """
        ФОРМИРОВАНИЕ ЗАПРОСА НА ВЫПОЛНЕНИЕ КОМАНДЫ.
        """
        forbidden = ["rm -rf /", "mkfs", "chmod -R 777 /", "dd if="]
        for f in forbidden:
            if f in command:
                return {"status": "rejected", "error": "Команда в черном списке безопасности!"}

        return {
            "status": "pending_confirmation",
            "command": command,
            "reason": reason,
            "instruction": "Нажмите 'Разрешить' в чате для выполнения этой операции."
        }

    @staticmethod
    def execute_confirmed_command(command: str, is_local: bool = False) -> str:
        """
        Финальное выполнение после подтверждения.
        Если is_local=False, пробует отправить команду на Remote Worker (88.55).
        """
        # Если команда для локального воркера (Home Lab), шлем на API
        # В будущем тут можно добавить логику выбора адреса на основе agent_type
        is_remote_request = not (os.getenv("IS_VDS", "false").lower() == "true")
        remote_url = os.getenv("LOCAL_SERVER_URL", "http://192.168.88.55:8001").replace("11434", "8001")
        api_token = os.getenv("API_SECRET", "change_me_in_env")

        if not is_local and "192.168.88." in remote_url:
            try:
                print(f"DEBUG: Sending command to remote worker: {remote_url}/execute")
                response = requests.post(
                    f"{remote_url}/execute",
                    params={"command": command},
                    headers={"X-Token": api_token},
                    timeout=35
                )
                if response.status_code == 200:
                    res_json = response.json()
                    return f"Результат с удаленного воркера:\n{res_json.get('output', 'Нет вывода')}"
                else:
                    return f"Ошибка воркера ({response.status_code}): {response.text}"
            except Exception as e:
                return f"Ошибка связи с воркером: {str(e)}"

        # Иначе выполняем локально (на VDS или на ноуте, если мы в режиме отладки)
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            output = result.stdout if result.stdout else result.stderr
            return f"Результат (локально):\n{output}"
        except subprocess.TimeoutExpired:
            return "Ошибка: Превышено время ожидания (timeout)."
        except Exception as e:
            return f"Ошибка выполнения: {str(e)}"

admin_tools = AdminTools()
