import os
import sys

# Добавляем корень проекта в пути
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.skills.german_teacher import GermanTeacherSkills

def test_note_per_item():
    print("--- Testing Note-per-Item (German Refactor) ---")
    
    # Имитируем VDS
    os.makedirs("obsidian_vault_simulation", exist_ok=True)
    
    skills = GermanTeacherSkills(workspace_root=os.getcwd())
    print(skills.get_status())
    
    # 1. Тест существительного (должно стать wohnung.md)
    res1 = skills.save_word(
        wort="die Wohnung -en", 
        uebersetzung="квартира", 
        beispiel_1="Ich suche eine Wohnung.", 
        beispiel_2="Die Wohnung исто groß."
    )
    print(f"Noun Test: {res1}")
    
    # 2. Тест глагола (должно стать gehen.md)
    res2 = skills.save_word(
        wort="gehen, ging, ist gegangen", 
        uebersetzung="идти", 
        beispiel_1="Ich gehe nach Hause.",
        notes="Strong verb"
    )
    print(f"Verb Test: {res2}")
    
    # 3. Тест фразы (slugified name)
    res3 = skills.save_phrase(
        phrase="Wie geht es dir?",
        uebersetzung="Как дела?",
        context="Повседневный"
    )
    print(f"Phrase Test: {res3}")
    
    # Проверка файлов
    words_dir = "obsidian_vault_simulation/knowledge/german/words"
    phrases_dir = "obsidian_vault_simulation/knowledge/german/phrases"
    
    created_files = []
    for d in [words_dir, phrases_dir]:
        if os.path.exists(d):
            created_files.extend(os.listdir(d))
            
    print(f"Created files in simulation: {created_files}")
    
    required = ["wohnung.md", "gehen.md", "wie-geht-es-dir.md"]
    all_present = all(f in created_files for f in required)
    
    if all_present:
        print("✅ SUCCESS: All specific files created correctly.")
    else:
        print(f"❌ FAILURE: Missing files. Expected {required}")

if __name__ == "__main__":
    test_note_per_item()
