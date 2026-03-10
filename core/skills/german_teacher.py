import os
import datetime
from core.utils_obsidian import ObsidianManager

class GermanTeacherSkills:
    """
    Набор инструментов для Herr Max Klein (Учителя немецкого языка),
    адаптированный для работы как на VDS (с перенаправлением в транспорт),
    так и на Home Server (с прямой записью в Obsidian).
    """
    
    def __init__(self, workspace_root: str = None):
        if workspace_root is None:
            self.workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        else:
            self.workspace_root = workspace_root
            
        # Проверка на наличие obsidian_vault_simulation (маркер VDS)
        self.is_vds = os.path.exists(os.path.join(self.workspace_root, 'obsidian_vault_simulation'))
        
        # Базовая папка для немецкого языка
        if self.is_vds:
            self.german_dir = os.path.join(self.workspace_root, 'obsidian_vault_simulation', 'knowledge', 'german')
        else:
            # На Home Server пишем сразу в Master Vault (путь из .env обычно, но тут пока по структуре)
            # ВНИМАНИЕ: На Home Server папка knowledge/german должна существовать в Master Vault
            self.german_dir = os.path.join(self.workspace_root, 'knowledge', 'german')

    def save_knowledge(self, content: str, category: str = "vocab") -> str:
        """
        Сохраняет знания (лексику, грамматику, прогресс) в нужную категорию.
        category: 'vocab', 'grammar', 'progress', 'plan'
        """
        os.makedirs(self.german_dir, exist_ok=True)
        
        mapping = {
            "vocab": "vocabulary.md",
            "grammar": "grammar.md",
            "plan": "learning_plan.md",
            "progress": "progress.md"
        }
        
        filename = mapping.get(category, f"{category}.md")
        full_path = os.path.join(self.german_dir, filename)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Для плана 'w' (перезапись), для остального 'a' (дополнение)
        mode = 'w' if category == 'plan' else 'a'
        
        try:
            with open(full_path, mode, encoding='utf-8') as f:
                if category == 'plan':
                    f.write(content)
                else:
                    f.write(f"\n---\n> **Recorded at {timestamp}**\n{content}\n")
            
            status = " [Transport Queued]" if self.is_vds else " [Local Master Vault]"
            return f"Success: Saved to {filename}{status}"
        except Exception as e:
            return f"Error saving German knowledge: {str(e)}"

    def update_vocabulary(self, word: str, translation: str, example: str = "") -> str:
        """Специальный метод для быстрого добавления слов."""
        entry = f"**{word}** — {translation}"
        if example:
            entry += f"\n*Example: {example}*"
        return self.save_knowledge(entry, "vocab")

    def get_status(self) -> str:
        """Возвращает текущий режим работы навыка."""
        return "VDS Mode (Sync active)" if self.is_vds else "Home Server Mode (Direct access)"
