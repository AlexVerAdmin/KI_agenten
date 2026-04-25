import os
import re
import datetime
import logging
from typing import Dict, List, Optional, Tuple

class GermanStorage:
    """
    Слой хранения для немецкого навыка.
    Отвечает за:
    - Построение путей (VDS vs Home)
    - Определение типа слова (существительное, глагол и т.д.)
    - Генерацию имен файлов (без артиклей для сущ., инфинитив для глаголов)
    - Создание и обновление заметок по шаблонам
    """
    
    def __init__(self, workspace_root: str = None):
        if workspace_root is None:
            # Находим корень проекта относительно этого файла (core/skills/german_storage.py)
            self.workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        else:
            self.workspace_root = workspace_root
            
        # Проверка режима VDS (через симуляцию vault)
        self.is_vds = os.path.exists(os.path.join(self.workspace_root, 'obsidian_vault_simulation'))
        
        # Базовый путь к немецкой части знаний
        if self.is_vds:
            self.base_dir = os.path.join(self.workspace_root, 'obsidian_vault_simulation', 'knowledge', 'german')
        else:
            self.base_dir = os.path.join(self.workspace_root, 'knowledge', 'german')
            
        self.template_dir = os.path.join(self.workspace_root, 'knowledge', 'german', '_templates')
        
        # Подпапки сущностей
        self.dirs = {
            'word': os.path.join(self.base_dir, 'words'),
            'phrase': os.path.join(self.base_dir, 'phrases'),
            'grammar': os.path.join(self.base_dir, 'grammar'),
            'plan': os.path.join(self.base_dir, 'plans'),
            'template': self.template_dir
        }
        
        # Создаем структуру папок
        for d in self.dirs.values():
            os.makedirs(d, exist_ok=True)

    def _slugify(self, text: str, preserve_case: bool = False) -> str:
        """Нормализация строки для имени файла."""
        text = text.strip()
        # Замена умлаутов для безопасности имен файлов
        replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}
        for char, rep in replacements.items():
            text = text.replace(char, rep)
            text = text.replace(char.upper(), rep.capitalize() if preserve_case else rep)
        if not preserve_case:
            text = text.lower()
        # Убираем все кроме букв, цифр и дефисов
        text = re.sub(r'[^A-Za-z0-9\s-]', '', text)
        text = re.sub(r'\s+', '-', text)
        return text

    def detect_word_type(self, wort_raw: str) -> Tuple[str, str]:
        """
        Определяет тип слова и возвращает (тип, чистое_имя_для_файла).
        Типы: 'noun', 'verb', 'other'.
        """
        w = wort_raw.strip()
        
        # 1. Существительное (начинается с артикля der/die/das или Ein/Eine)
        noun_match = re.match(r'^(der|die|das)\s+([A-ZÄÖÜ][a-zäöüß]+)', w, re.IGNORECASE)
        if noun_match:
            return 'noun', self._slugify(noun_match.group(2), preserve_case=True)
            
        # 2. Глагол (обычно содержит запятые для трех форм или заканчивается на -en/-eln/-ern)
        # Если есть запятые - скорее всего это формы глагола
        if ',' in w and (w.lower().endswith('en') or 'sein' in w.lower() or 'haben' in w.lower()):
            infinitiv = w.split(',')[0].strip()
            return 'verb', self._slugify(infinitiv)
        
        # Эвристика на окончание инфинитива
        if w.lower().endswith(('en', 'eln', 'ern')) and ' ' not in w:
            return 'verb', self._slugify(w)

        preserve_case = bool(re.match(r'^[A-ZÄÖÜ]', w))
        return 'other', self._slugify(w, preserve_case=preserve_case)

    def _read_template(self, template_name: str) -> str:
        path = os.path.join(self.template_dir, f"{template_name}_template.md")
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def save_word(self, wort_data: Dict) -> str:
        """
        wort_data: { 'wort': 'die Wohnung -en', 'plural': 'Wohnungen', 'uebersetzung': '...', 'beispiele': [...], 'beispiel_uebersetzungen': [...], 'notes': '...' }
        """
        raw_wort = wort_data.get('wort', '')
        w_type, filename_base = self.detect_word_type(raw_wort)
        
        filepath = os.path.join(self.dirs['word'], f"{filename_base}.md")
        template = self._read_template('word_note')
        
        if not template:
            return "Error: Word template not found"
            
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        beispiele = wort_data.get('beispiele', ["", ""])
        beispiel_uebersetzungen = wort_data.get('beispiel_uebersetzungen', ["", ""])
        b1 = beispiele[0] if len(beispiele) > 0 else ""
        b2 = beispiele[1] if len(beispiele) > 1 else ""
        b1_ru = beispiel_uebersetzungen[0] if len(beispiel_uebersetzungen) > 0 else ""
        b2_ru = beispiel_uebersetzungen[1] if len(beispiel_uebersetzungen) > 1 else ""
        
        content = template.replace('{{ wort }}', raw_wort)
        content = content.replace('{{ plural }}', wort_data.get('plural', ''))
        content = content.replace('{{ uebersetzung }}', wort_data.get('uebersetzung', ''))
        content = content.replace('{{ beispiel_1 }}', b1)
        content = content.replace('{{ beispiel_2 }}', b2)
        content = content.replace('{{ beispiel_1_translation }}', b1_ru)
        content = content.replace('{{ beispiel_2_translation }}', b2_ru)
        content = content.replace('{{ created }}', now)
        content = content.replace('{{ title }}', raw_wort)
        content = content.replace('{{ notes }}', wort_data.get('notes', ''))
        
        try:
            # Если файл существует, мы пока просто перезаписываем (согласно плану, аккуратное обновление - след. этап)
            # Но мы можем добавить проверку, чтобы не затирать ручные правки совсем
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            mode_str = "VDS/Transport" if self.is_vds else "Local/Direct"
            return f"Success: Saved word '{filename_base}' to {mode_str}"
        except Exception as e:
            return f"Error: {str(e)}"

    def save_phrase(self, phrase_data: Dict) -> str:
        """
        phrase_data: { 'phrase': '...', 'uebersetzung': '...', 'context': '...', 'usage': '...', 'beispiele': [...], 'notes': '...' }
        """
        raw_phrase = phrase_data.get('phrase', '')
        filename = self._slugify(raw_phrase)
        filepath = os.path.join(self.dirs['phrase'], f"{filename}.md")
        
        template = self._read_template('phrase_note')
        if not template: return "Error: Phrase template not found"
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        beispiele = phrase_data.get('beispiele', ["", ""])
        
        content = template.replace('{{ phrase }}', raw_phrase)
        content = content.replace('{{ uebersetzung }}', phrase_data.get('uebersetzung', ''))
        content = content.replace('{{ context }}', phrase_data.get('context', ''))
        content = content.replace('{{ created }}', now)
        content = content.replace('{{ title }}', raw_phrase)
        content = content.replace('{{ usage }}', phrase_data.get('usage', ''))
        content = content.replace('{{ beispiel_1 }}', beispiele[0] if len(beispiele) > 0 else "")
        content = content.replace('{{ beispiel_2 }}', beispiele[1] if len(beispiele) > 1 else "")
        content = content.replace('{{ notes }}', phrase_data.get('notes', ''))
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Success: Saved phrase '{filename}'"
        except Exception as e:
            return f"Error: {str(e)}"

    def update_learning_plan(self, plan_data: Dict) -> str:
        """
        Простое обновление файла плана (перезапись основного сектора)
        """
        filepath = os.path.join(self.dirs['plan'], "learning_plan.md")
        template = self._read_template('learning_plan')
        
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        content = template.replace('{{ created }}', now)
        content = content.replace('{{ updated }}', now)
        content = content.replace('{{ goal_1 }}', plan_data.get('goals', [""])[0])
        content = content.replace('{{ current_focus }}', plan_data.get('focus', ''))
        # и так далее для остальных плейсхолдеров...
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return "Success: Learning plan updated"
        except Exception as e:
            return f"Error updating plan: {str(e)}"
