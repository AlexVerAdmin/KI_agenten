"""
Утилита для чтения и записи файлов Obsidian.
Работает как на ноутбуке (~/Obsidian/), так и на VDS (/app/obsidian/).
"""

import os
from pathlib import Path
from datetime import datetime

OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/home/alex/Obsidian"))


def read_obsidian(relative_path: str) -> str:
    """
    Читает файл из Obsidian vault.
    relative_path: путь относительно vault, например '01_Projects/Agents/tutor/progress.md'
    Возвращает содержимое или пустую строку если файл не найден.
    """
    path = OBSIDIAN_VAULT / relative_path
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def write_obsidian(relative_path: str, content: str, append: bool = False) -> bool:
    """
    Пишет файл в Obsidian vault.
    append=True — дописывает в конец, False — перезаписывает.
    Возвращает True при успехе.
    """
    path = OBSIDIAN_VAULT / relative_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if append and path.exists():
            existing = path.read_text(encoding="utf-8")
            path.write_text(existing + "\n" + content, encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def append_dated_note(relative_path: str, content: str) -> bool:
    """
    Дописывает заметку с датой в конец файла.
    Используется агентами для записи итогов сессий.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note = f"\n## {timestamp}\n{content}\n"
    return write_obsidian(relative_path, note, append=True)
