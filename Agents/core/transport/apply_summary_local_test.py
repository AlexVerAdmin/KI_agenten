import os
import json
import time
from pathlib import Path
from common import (
    load_state, save_state, PROJECT_ROOT, RUNTIME_SYNC_DIR
)

# --- ПУТИ ПРИМЕНЕНИЯ ---
# Где лежат файлы на VDS (в симуляции - папка temp/vds_simulation)
VDS_SIM_DIR = PROJECT_ROOT / "temp" / "vds_simulation"
VDS_ACTIVE_MEMORY_PATH = VDS_SIM_DIR / "active_memory.md"
VDS_GERMAN_PLAN_PATH = VDS_SIM_DIR / "german_plan.md"
VDS_CAREER_PLAN_PATH = VDS_SIM_DIR / "career_plan.md"

def apply_summary_on_vds_sim(track_name: str):
    """Применяет summary из import/{track} к Markdown-файлам на VDS."""
    import_track_dir = VDS_SIM_DIR / "import" / track_name
    import_track_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Выбираем файл для применения
    target_files = {
        "copilot": VDS_ACTIVE_MEMORY_PATH,
        "german": VDS_GERMAN_PLAN_PATH,
        "career": VDS_CAREER_PLAN_PATH
    }
    
    target_file = target_files.get(track_name)
    if not target_file:
        print(f"[{track_name}] No target Markdown file for this track.")
        return

    # 2. Ищем новые summary-файлы в import
    summary_files = sorted([f for f in import_track_dir.iterdir() if f.is_file()])
    
    if not summary_files:
        print(f"[{track_name}] No new summary files in VDS simulated import.")
        return

    for summary_file in summary_files:
        print(f"[{track_name}] Applying {summary_file.name} to {target_file.name}...")
        
        # 3. Читаем summary
        with open(summary_file, "r", encoding="utf-8") as fs:
            summary_content = fs.read()
            
        # 4. Читаем и дополняем target
        target_content = ""
        if target_file.exists():
            with open(target_file, "r", encoding="utf-8") as ft:
                target_content = ft.read()
                
        # Простая конкатенация для теста (в будущем - умная вставка)
        new_content = f"{target_content}\n\n## Summary from {summary_file.name}\n{summary_content}\n"
        
        with open(target_file, "w", encoding="utf-8") as ft:
            ft.write(new_content)
            
        print(f"[{track_name}] Updated {target_file.name}")
        
        # 5. Убираем из 'import' (в реальности или архивируем)
        summary_file.unlink()

if __name__ == "__main__":
    # Локальный тест
    # 1. Создаем пустые Markdown в VDS-симуляции
    VDS_ACTIVE_MEMORY_PATH.touch()
    VDS_GERMAN_PLAN_PATH.touch()
    VDS_CAREER_PLAN_PATH.touch()
    
    # 2. Положим тестовый summary
    test_import_dir = VDS_SIM_DIR / "import" / "copilot"
    test_import_dir.mkdir(parents=True, exist_ok=True)
    with open(test_import_dir / "summary_12345.md", "w", encoding="utf-8") as f:
        f.write("- User learned SSH basic concepts.")
        
    # 3. Пробуем применить
    apply_summary_on_vds_sim("copilot")
