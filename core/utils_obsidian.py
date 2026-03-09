import os
import logging
from datetime import datetime
from config import config

class ObsidianManager:
    def __init__(self, vault_path=None):
        self.vault_path = vault_path or config.obsidian_vault_path
        if not self.vault_path or not os.path.exists(self.vault_path):
            logging.error(f"Obsidian Vault path NOT FOUND at: {self.vault_path}")

    def list_files(self, subfolder="main", ext=".md"):
        """Список всех файлов в подпапке (например, main/Deutsch/Words)."""
        target_dir = os.path.join(self.vault_path, subfolder)
        if not os.path.exists(target_dir):
            return []
        
        files = []
        for root, _, filenames in os.walk(target_dir):
            for f in filenames:
                if f.endswith(ext):
                    files.append(os.path.join(root, f))
        return files

    def read_note(self, relative_path):
        """Читает содержимое заметки по относительному пути."""
        full_path = os.path.join(self.vault_path, relative_path)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None

    def capture_to_inbox(self, content, title=None):
        """Быстрое сохранение во входящие (Inbox)."""
        if not title:
            title = f"Capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        inbox_path = os.path.join(self.vault_path, "_Inbox", f"{title}.md")
        os.makedirs(os.path.dirname(inbox_path), exist_ok=True)
        
        with open(inbox_path, 'w', encoding='utf-8') as f:
            f.write(f"---\ncreated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\ntags: #inbox\n---\n\n{content}")
        return f"Saved to Inbox: {title}"

    def add_expense(self, category, amount, description=""):
        """Запись расхода в файл финансов (нейтральный формат)."""
        current_month = datetime.now().strftime("%Y-%m")
        finance_file = os.path.join(self.vault_path, "main", "Финансы", f"{current_month}_Expenses.md")
        os.makedirs(os.path.dirname(finance_file), exist_ok=True)
        
        timestamp = datetime.now().strftime("%H:%M")
        entry = f"| {timestamp} | {category} | {amount} | {description} |\n"
        
        if not os.path.exists(finance_file):
            header = f"# Расходы за {current_month}\n\n| Время | Категория | Сумма | Описание |\n| --- | --- | --- | --- |\n"
            with open(finance_file, 'w', encoding='utf-8') as f:
                f.write(header)
        
        with open(finance_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        return f"Запись сохранена: {amount} ({category})"

    def log_thought(self, content):
        """Запись мыслей в ежедневный файл (Daily Note)."""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_file = os.path.join(self.vault_path, "main", "Daily", f"{today}.md")
        os.makedirs(os.path.dirname(daily_file), exist_ok=True)
        
        timestamp = datetime.now().strftime("%H:%M")
        
        if not os.path.exists(daily_file):
            header = f"---\ndate: {today}\nstatus: active\n---\n\n# Заметки за {today}\n\n"
            with open(daily_file, 'w', encoding='utf-8') as f:
                f.write(header)
        
        entry = f"\n---\n> **{timestamp}**\n{content}\n"
        
        with open(daily_file, 'a', encoding='utf-8') as f:
            f.write(entry)
        return f"Сохранено в Daily/{today}.md"

    def cleanup_sync_conflicts(self):
        """Удаляет файлы конфликтов синхронизации (app (conflict...))."""
        count = 0
        for root, _, files in os.walk(self.vault_path):
            for f in files:
                if "(conflict" in f or ".sync-conflict" in f:
                    os.remove(os.path.join(root, f))
                    count += 1
        return f"Удалено {count} конфликтных файлов."

obsidian = ObsidianManager()

# --- Внешние функции-инструменты для агентов ---

def obsidian_capture_tool(content: str, title: str = None) -> str:
    """
    Инструмент для быстрого захвата текста в Obsidian Inbox.
    Используется агентами для сохранения слов, фраз и заметок.
    """
    return obsidian.capture_to_inbox(content, title)

def save_german_knowledge(content: str, category: str = "general") -> str:
    """
    Специализированный инструмент для Herr Max Klein.
    Сохраняет новые знания, слова или изменения в плане обучения в папку knowledge/german/.
    category: 'vocab' (слова), 'grammar' (правила), 'plan' (изменения в обучении), 'progress' (заметки об успехах).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    german_dir = os.path.abspath(os.path.join(base_dir, '..', 'knowledge', 'german'))
    os.makedirs(german_dir, exist_ok=True)
    
    filename = f"{category}.md"
    if category == "vocab":
        filename = "vocabulary.md"
    elif category == "plan":
        filename = "learning_plan.md"
        # Для плана мы перезаписываем (или дополняем), для вокабуляра — дополняем
    
    full_path = os.path.join(german_dir, filename)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    mode = 'a' if category != 'plan' else 'w'
    
    try:
        with open(full_path, mode, encoding='utf-8') as f:
            if category == 'plan':
                f.write(content)
            else:
                f.write(f"\n---\n> **{timestamp}**\n{content}\n")
        return f"Успешно сохранено в {filename}"
    except Exception as e:
        return f"Ошибка при сохранении: {str(e)}"
    return obsidian.capture_to_inbox(content, title)

def obsidian_read_note(relative_path: str) -> str:
    """
    Инструмент для чтения содержимого заметки из Obsidian.
    Пусть указывается относительно корня хранилища (например, 'main/Notes.md').
    """
    res = obsidian.read_note(relative_path)
    return res if res else "Заметка не найдена"

