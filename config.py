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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

# Initialize and validate settings
config = Settings()
