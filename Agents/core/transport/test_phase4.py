import os
import sys

# Добавляем корень проекта в пути
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.skills.german_teacher import GermanTeacherSkills

def test_german_skills():
    print("--- Testing German Teacher Skills (Phase 4) ---")
    
    # Имитируем VDS (заставляем думать, что мы там)
    os.makedirs("obsidian_vault_simulation", exist_ok=True)
    
    skills = GermanTeacherSkills(workspace_root=os.getcwd())
    print(f"Current Mode: {skills.get_status()}")
    
    # 1. Добавление слова
    res1 = skills.update_vocabulary("der Tisch", "стол", "Der Tisch ist groß.")
    print(f"Add word: {res1}")
    
    # 2. Добавление грамматики
    res2 = skills.save_knowledge("Passiv Präsens: werden + Partizip II", "grammar")
    print(f"Add grammar: {res2}")
    
    # 3. Проверка файлов
    files = []
    for root, dirs, f_list in os.walk("obsidian_vault_simulation"):
        for f in f_list:
            files.append(os.path.join(root, f))
    
    print(f"Created files: {files}")
    
    if len(files) >= 2:
        print("✅ TEST PASSED: Skills created files in simulation folder.")
    else:
        print("❌ TEST FAILED: Verification files missing.")

if __name__ == "__main__":
    test_german_skills()
