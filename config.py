import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    telegram_bot_token: str
    groq_api_key: str
    allowed_telegram_user_ids: str = ""
    ollama_base_url: str = "http://localhost:11434"
    obsidian_vault_path: str = ""
    job_search_path: str = ""
    google_api_key: str = ""
    github_copilot_token: str = ""
    sqlite_db_path: str = "data/memory_v2.sqlite"
    local_server_url: str = "http://localhost:11434"
    remote_worker_url: str = "none"
    api_secret: str = "change_me_in_env"
    nextcloud_url: str = ""
    nextcloud_user: str = ""
    nextcloud_pass: str = ""
    nextcloud_remote_dir: str = "ObsidianVault"

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="allow",
        env_prefix="" # Чтобы Pydantic искал переменные без преффикса
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Принудительно устанавливаем local_server_url из OLLAMA_BASE_URL, если он есть
        env_url = os.getenv("OLLAMA_BASE_URL")
        if env_url:
            self.local_server_url = env_url

# Initialize and validate settings
config = Settings()

# ОБЯЗАТЕЛЬНОЕ ПЕРЕОПРЕДЕЛЕНИЕ (Pydantic иногда игнорирует env при инициализации в Docker)
if os.getenv("OLLAMA_BASE_URL"):
    config.local_server_url = os.getenv("OLLAMA_BASE_URL")
