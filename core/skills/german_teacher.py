import os
import datetime
from .german_storage import GermanStorage

class GermanTeacherSkills:
    """
    Интерфейс учителя Herr Max Klein для работы с Obsidian через GermanStorage.
    """
    
    def __init__(self, workspace_root: str = None):
        self.storage = GermanStorage(workspace_root)
        self.is_vds = self.storage.is_vds

    def save_word(self, wort: str, uebersetzung: str, beispiel_1: str = "", beispiel_2: str = "", notes: str = "") -> str:
        """
        Сохраняет отдельное слово (существительное или глагол) по шаблону в Obsidian.
        Для существительного имя файла будет без артикаля.
        Для глагола — инфинитив.
        """
        data = {
            'wort': wort,
            'uebersetzung': uebersetzung,
            'beispiele': [beispiel_1, beispiel_2],
            'notes': notes
        }
        return self.storage.save_word(data)

    def save_phrase(self, phrase: str, uebersetzung: str, context: str = "", usage: str = "", beispiel_1: str = "", beispiel_2: str = "", notes: str = "") -> str:
        """
        Сохраняет отдельную фразу по шаблону.
        """
        data = {
            'phrase': phrase,
            'uebersetzung': uebersetzung,
            'context': context,
            'usage': usage,
            'beispiele': [beispiel_1, beispiel_2],
            'notes': notes
        }
        return self.storage.save_phrase(data)

    def update_learning_plan(self, goals: list = None, focus: str = "") -> str:
        """Обновление файла плана обучения (инициализация/фокус)."""
        data = {
            'goals': goals or [],
            'focus': focus
        }
        return self.storage.update_learning_plan(data)

    def save_knowledge(self, content: str, category: str = "vocab") -> str:
        """
        Legacy-фасад для обратной совместимости. 
        Перенаправляет в новые методы сохранения, если это возможно.
        """
        if category == "vocab":
            # Simple fallback
            return self.save_word(content, "Auto-extracted", notes="Legacy input")
            
        return f"Warning: Category '{category}' is legacy. Use save_word/save_phrase/update_plan."

    def update_vocabulary(self, word: str, translation: str, example: str = "") -> str:
        """Legacy-метод, теперь использует поштучное сохранение."""
        return self.save_word(word, translation, beispiel_1=example)

    def get_status(self) -> str:
        mode = "VDS (Sync-Ready)" if self.is_vds else "Home Server (Direct Vault)"
        return f"Herr Max Klein is active in {mode} Mode."
