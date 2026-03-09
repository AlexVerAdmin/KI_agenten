import os
import sys
from datetime import datetime

class SessionMemory:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.memory_path = os.path.abspath(os.path.join(self.base_dir, '..', '..', 'history', 'copilot', 'active_memory.md'))
        self.checklist_path = os.path.abspath(os.path.join(self.base_dir, '..', '..', 'history', 'copilot', 'session_checklist.md'))

    def commit_snapshot(self, message):
        """Записывает важное решение или событие в активную память."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        snapshot_entry = f"\n\n### 🕒 Snapshot [{timestamp}]\n- **Decision:** {message}\n"
        
        try:
            with open(self.memory_path, 'a', encoding='utf-8') as f:
                f.write(snapshot_entry)
            print(f"Snapshot saved to {os.path.relpath(self.memory_path)}")
            return True
        except Exception as e:
            print(f"Error saving snapshot: {e}")
            return False

    def mark_completed(self, item_text):
        """Помечает пункт в чек-листе сессии как выполненный [x]."""
        if not os.path.exists(self.checklist_path):
            print("Checklist file not found.")
            return

        with open(self.checklist_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        with open(self.checklist_path, 'w', encoding='utf-8') as f:
            for line in lines:
                if item_text in line and '[ ]' in line:
                    line = line.replace('[ ]', '[x]')
                    print(f"Item marked as completed: {item_text}")
                f.write(line)

if __name__ == "__main__":
    memory = SessionMemory()
    if len(sys.argv) > 1:
        action = sys.argv[1]
        msg = " ".join(sys.argv[2:])
        if action == "commit":
            memory.commit_snapshot(msg)
        elif action == "done":
            memory.mark_completed(msg)
    else:
        print("Usage: python session_snapshot.py commit 'message' OR done 'item name'")
