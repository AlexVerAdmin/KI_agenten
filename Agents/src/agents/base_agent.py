"""
Базовый класс для агентов с интеграцией Obsidian.
Автоматически загружает контекст при инициализации.
"""

from pathlib import Path
from Agents.src.utils.obsidian import read_obsidian, append_dated_note
from Agents.src.config import OBSIDIAN_PROJECT


class AgentWithObsidian:
    """
    Базовый класс для агентов, использующих Obsidian для долговременной памяти.
    
    Дочерние классы должны определить:
    - agent_name: str — имя агента (например, "tutor")
    - memory_files: dict — файлы для чтения {"key": "path/to/file.md"}
    """
    
    agent_name: str = None
    memory_files: dict = {}
    
    def __init__(self):
        if not self.agent_name:
            raise ValueError("agent_name must be defined in subclass")
        
        self.agent_dir = OBSIDIAN_PROJECT / "agents" / self.agent_name
        self.memory = {}
        self._load_memory()
    
    def _load_memory(self):
        """Загружает файлы памяти из Obsidian."""
        for key, relative_path in self.memory_files.items():
            # Путь формируется относительно корня vault, если не начинается с 01_Projects
            full_path = relative_path if relative_path.startswith("01_Projects") else f"01_Projects/Agents/{relative_path}"
            content = read_obsidian(full_path)
            self.memory[key] = content
            
    def save_session_summary(self, summary: str) -> bool:
        """Сохраняет итог сессии в Obsidian."""
        memory_file = f"01_Projects/Agents/agents/{self.agent_name}/session_log.md"
        return append_dated_note(memory_file, summary)
    
    def get_context_for_prompt(self) -> str:
        """Формирует контекст из памяти для добавления в system prompt."""
        context_parts = []
        for key, content in self.memory.items():
            if content:
                context_parts.append(f"## {key.upper()}\n{content[:1000]}")  # Первые 1000 символов
        return "\n\n".join(context_parts)
