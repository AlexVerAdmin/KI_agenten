"""
Утилита для чтения и записи файлов Obsidian.
Работает как на ноутбуке (~/Obsidian/), так и на VDS (/app/obsidian/).
"""

import os
import ast
import re
import logging
from pathlib import Path
from datetime import datetime

# Фиксированный путь, если переменная окружения не задана
OBSIDIAN_VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "/home/alex/Документи/Obsidian"))


def read_obsidian(relative_path: str) -> str:
    path = OBSIDIAN_VAULT / relative_path
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def write_obsidian(relative_path: str, content: str, append: bool = False) -> bool:
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
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    note = f"\n## {timestamp}\n{content}\n"
    return write_obsidian(relative_path, note, append=True)

def sync_code_to_obsidian(source_file_path: str, note_path: str):
    """
    Автоматически извлекает ВСЕ функции и классы из source_file_path 
    и обновляет секцию ## Implementation в заметке Obsidian по пути note_path.
    """
    try:
        if not os.path.exists(source_file_path):
            print(f"❌ Source file not found: {source_file_path}")
            return

        with open(source_file_path, 'r', encoding='utf-8') as f:
            source_code = f.read()
            tree = ast.parse(source_code)

        nodes = [node for node in tree.body 
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        
        if not nodes:
            print(f"⚠️ No functions or classes found in {source_file_path}")
            return

        lines = source_code.splitlines()
        all_code_blocks = []
        for node in nodes:
            block_code = "\n".join(lines[node.lineno-1 : node.end_lineno])
            all_code_blocks.append(block_code)
        
        combined_code = "\n\n".join(all_code_blocks)
        
        full_note_path = OBSIDIAN_VAULT / note_path
        marker = "## Implementation"
        code_block = f"```python\n{combined_code}\n```"

        if full_note_path.exists():
            content = full_note_path.read_text(encoding="utf-8")
            if marker in content:
                parts = re.split(f"{marker}", content)
                new_content = parts[0] + f"{marker}\n\n{code_block}"
                full_note_path.write_text(new_content, encoding="utf-8")
                print(f"✅ Updated {note_path}")
            else:
                new_content = content + f"\n\n{marker}\n\n{code_block}"
                full_note_path.write_text(new_content, encoding="utf-8")
                print(f"✅ Added {marker} to {note_path}")
        else:
            # Создаем новый файл, если его нет
            full_note_path.parent.mkdir(parents=True, exist_ok=True)
            note_name = full_note_path.stem.replace("_", " ").title()
            new_content = f"# {note_name}\n\n{marker}\n\n{code_block}"
            full_note_path.write_text(new_content, encoding="utf-8")
            print(f"🆕 Created new note: {note_path}")

    except Exception as e:
        print(f"❌ Error syncing {source_file_path}: {e}")

async def ping_obsidian() -> str:
    return "Obsidian MCP Server is connected and working!"
