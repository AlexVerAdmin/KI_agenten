import os
import sqlite3
import requests
import json
from datetime import datetime

# Настройки
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "memory_v2.sqlite") # Путь к БД с логами
OLLAMA_URL = "http://localhost:11434/api/generate" # URL локальной модели
MODEL_NAME = "llama3" # Или "mistral", "qwen", что стоит у тебя

def get_recent_history(limit=50):
    """Извлекает последние сообщения из SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        query = "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?"
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        conn.close()
        # Возвращаем в правильном хронологическом порядке
        return "\n".join([f"{r[0]}: {r[1]}" for r in reversed(rows)])
    except Exception as e:
        return f"Error reading DB: {e}"

def generate_summary(history_text):
    """Отправляет историю локальной модели для сжатия."""
    prompt = f"""
    Проанализируй следующую историю переписки. 
    ИЗВЛЕКИ ТОЛЬКО:
    1. Принятые технические решения (ADR).
    2. Изменения в планах.
    3. Текущий статус проекта (на чем остановились).
    
    ИСТОРИЯ:
    {history_text}
    
    ОТПРАВЬ ОТВЕТ ТОЛЬКО В ФОРМАТЕ MARKDOWN:
    """
    
    data = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=data)
        if response.status_code == 200:
            return response.json().get('response', 'No response from model')
        return f"Ollama Error: {response.status_code}"
    except Exception as e:
        return f"Connection Error: {e}"

def update_active_memory(summary_text):
    """Записывает результат в файл активной памяти."""
    memory_path = os.path.join(os.path.dirname(__file__), "active_memory.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    content = f"\n\n--- AUTO-SUMMARY ({timestamp}) ---\n{summary_text}\n"
    
    with open(memory_path, 'a', encoding='utf-8') as f:
        f.write(content)
    return "Memory Updated"

if __name__ == "__main__":
    # 1. Читаем логи
    history = get_recent_history(50)
    # 2. Сжимаем через Ollama
    summary = generate_summary(history)
    # 3. Записываем в файл
    print(update_active_memory(summary))
