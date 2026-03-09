import os
import sqlite3
import requests
import json
from datetime import datetime

# Настройки
# Используем memory_v2.sqlite как основной источник логов чата
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "memory_v2.sqlite") 
OLLAMA_URL = "http://localhost:11434/api/generate" 
MODEL_NAME = "llama3" 

def archive_and_get_history(limit=50):
    """Извлекает сообщения и помечает их как заархивированные (deleted_at)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # 1. Выбираем только не удаленные сообщения
        query = "SELECT id, role, content FROM chat_history WHERE deleted_at IS NULL ORDER BY id DESC LIMIT ?"
        cur.execute(query, (limit,))
        rows = cur.fetchall()
        
        if not rows:
            conn.close()
            return None, []

        msg_ids = [r[0] for r in rows]
        # Формируем текст истории (от старых к новым)
        history_text = "\n".join([f"{r[1]}: {r[2]}" for r in reversed(rows)])
        
        # 2. Мягкое удаление: помечаем как заархивированные
        timestamp = datetime.now().isoformat()
        mark_query = f"UPDATE chat_history SET deleted_at = ? WHERE id IN ({','.join(['?']*len(msg_ids))})"
        cur.execute(mark_query, (f"archived_{timestamp}", *msg_ids))
        
        conn.commit()
        conn.close()
        return history_text, msg_ids
    except Exception as e:
        return f"Error connecting to DB: {e}", []

def generate_summary(history_text):
    """Отправляет историю локальной модели Ollama для суммаризации."""
    prompt = f"""
    ### ИНСТРУКЦИЯ ДЛЯ AI-АРХИВАРИУСА:
    Проанализируй историю переписки ниже и создай СТРОГУЮ выжимку для долговременной памяти.
    
    ИЗВЛЕКИ ТОЛЬКО:
    1. Принятые ТЕХНИЧЕСКИЕ решения (архитектура, папки, инструменты).
    2. Изменения в ПЛАНАХ (что перенесли, что отменили).
    3. Текущий СТАТУС (где точка остановки).
    
    ИСТОРИЯ ДЛЯ АНАЛИЗА:
    {history_text}
    
    ОТПРАВЬ ОТВЕТ ТОЛЬКО В ФОРМАТЕ MARKDOWN (без лишних слов):
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
        return f"Connection Error (Check if Ollama is running): {e}"

def update_active_memory(summary_text):
    """Дописывает результат суммаризации в файл активной памяти основного проекта."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # Исправленный путь к папке history
    memory_path = os.path.abspath(os.path.join(base_dir, '..', '..', 'history', 'copilot', 'active_memory.md'))
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"\n\n--- 🧊 АРХИВНАЯ ВЫЖИМКА ({timestamp}) ---\n{summary_text}\n"
    
    if not os.path.exists(os.path.dirname(memory_path)):
        os.makedirs(os.path.dirname(memory_path))
        
    with open(memory_path, 'a', encoding='utf-8') as f:
        f.write(content)
    return f"Memory Updated in {os.path.basename(memory_path)}"

if __name__ == "__main__":
    print(f"Starting Summarizer... Target DB: {DB_PATH}")
    history, ids = archive_and_get_history(100)
    
    if history and not isinstance(history, str):
        print(f"Found {len(ids)} new messages. Consulting Ollama ({MODEL_NAME})...")
        summary = generate_summary(history)
        
        if "Error" not in summary:
            result = update_active_memory(summary)
            print(result)
        else:
            print(summary)
    else:
        print(history if history else "No new messages to archive.")
