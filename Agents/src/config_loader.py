import os
import yaml
import json
from pathlib import Path
from typing import Any, Dict

class ConfigLoader:
    """
    Класс для загрузки и объединения конфигураций проекта Antigravity.
    Поддерживает 4 уровня: Система (/etc), Глобальный (~/.config), Пользователь (~/.config), Проект (./.antigravity).
    """
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.config: Dict[str, Any] = {}
        
        # Пути к файлам в порядке возрастания приоритета
        self.paths = [
            Path("/etc/antigravity/config.yaml"),
            Path.home() / ".config" / "antigravity" / "global.yaml",
            Path.home() / ".config" / "antigravity" / "user.yaml",
            self.project_root / ".antigravity" / "settings.yaml",
        ]
        
    def _deep_merge(self, base: Dict, over: Dict) -> Dict:
        """Рекурсивное слияние словарей. Значения из 'over' перекрывают 'base'."""
        for key, value in over.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def load(self) -> Dict[str, Any]:
        """Загружает и объединяет все файлы конфигурации по порядку."""
        merged_config = {}
        for path in self.paths:
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    try:
                        data = yaml.safe_load(f)
                        if data:
                            self._deep_merge(merged_config, data)
                    except yaml.YAMLError as e:
                        print(f"Ошибка при загрузке {path}: {e}")
        
        self.config = merged_config
        return self.config

    def get(self, key_path: str, default: Any = None) -> Any:
        """Получает значение по пути через точку (например, 'user.name')."""
        keys = key_path.split('.')
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

if __name__ == "__main__":
    # Тестовый запуск
    loader = ConfigLoader()
    full_config = loader.load()
    print("--- Объединенная конфигурация ---")
    print(json.dumps(full_config, indent=2, ensure_ascii=False))
    print("\n--- Проверка ---")
    print(f"Имя пользователя: {loader.get('user.name')}")
    print(f"Приватность: {loader.get('workflow.privacy_level')}")
    print(f"Тип VPN: {loader.get('infrastructure.vpn.type')}")
    print(f"Оркестратор: {loader.get('models.orchestrator')}")
