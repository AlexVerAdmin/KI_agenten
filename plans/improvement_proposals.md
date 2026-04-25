# 🔧 Предложения по улучшению проекта Personal Agents

**Дата:** 2026-04-25  
**Статус:** Анализ и рекомендации  
**Приоритет:** Высокий

---

## 🎯 Выявленные проблемы

### 1. ❌ Плохо работает сохранение истории общения
**Симптомы:**
- История теряется между сессиями
- Контекст разговора не сохраняется корректно
- Дубликаты или пропуски сообщений

### 2. ❌ Плохо работает чтение информации из долговременной памяти
**Симптомы:**
- Модель не использует информацию из knowledge base
- Забывает ранее принятые решения
- Не учитывает контекст из `active_memory.md`

---

## 💡 Предлагаемые решения

### Проблема 1: Сохранение истории общения

#### Решение 1.1: Улучшение логики сохранения в orchestrator_v2.py

**Проверить текущую реализацию:**

```python
# В orchestrator_v2.py, функция save_message()
# ПРОБЛЕМА: content может быть не строкой
def save_message(user_id, agent_type, role, content, model_name=None):
    # Текущая логика сериализации content
    if not isinstance(content, str):
        # Преобразование в строку
        content = str(content)
```

**Предложение:**
```python
def save_message(user_id, agent_type, role, content, model_name=None):
    """Улучшенное сохранение с валидацией"""
    # 1. Нормализация content
    if isinstance(content, list):
        # Извлечь только текстовые части
        text_parts = []
        for item in content:
            if isinstance(item, dict) and 'text' in item:
                text_parts.append(item['text'])
            elif hasattr(item, 'text'):
                text_parts.append(item.text)
            elif isinstance(item, str):
                text_parts.append(item)
        content = "\n".join(text_parts)
    elif not isinstance(content, str):
        content = str(content)
    
    # 2. Валидация перед сохранением
    if not content or content.strip() == "":
        logging.warning(f"Попытка сохранить пустое сообщение от {role}")
        return
    
    # 3. Добавление метаданных
    metadata = {
        'has_tool_calls': False,
        'content_type': 'text',
        'length': len(content)
    }
    
    # 4. Транзакционное сохранение
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO chat_history 
            (user_id, agent_type, role, content, timestamp, model_name, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(user_id), 
            str(agent_type), 
            str(role), 
            content, 
            datetime.now().isoformat(), 
            str(model_name) if model_name else "",
            json.dumps(metadata)
        ))
        conn.commit()
        logging.info(f"Сохранено: {role} в {agent_type}, длина: {len(content)}")
    except Exception as e:
        logging.error(f"Ошибка сохранения: {e}")
        conn.rollback()
    finally:
        conn.close()
```

**Действия:**
1. Добавить колонку `metadata` в таблицу `chat_history`
2. Улучшить логирование для отладки
3. Добавить валидацию перед сохранением

#### Решение 1.2: Добавить middleware для отслеживания сообщений

**Создать `core/middleware/message_tracker.py`:**
```python
import logging
from datetime import datetime
from typing import Optional

class MessageTracker:
    """Middleware для отслеживания всех сообщений"""
    
    def __init__(self):
        self.session_messages = []
        logging.basicConfig(
            filename='data/message_tracker.log',
            level=logging.DEBUG,
            format='%(asctime)s - %(message)s'
        )
    
    def track_message(self, 
                     user_id: str,
                     agent_type: str, 
                     role: str, 
                     content: str,
                     saved: bool = False):
        """Логирование каждого сообщения"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'agent': agent_type,
            'role': role,
            'content_preview': content[:100] if content else "[EMPTY]",
            'saved_to_db': saved
        }
        self.session_messages.append(entry)
        logging.debug(f"MESSAGE: {entry}")
    
    def get_session_report(self):
        """Отчет по текущей сессии"""
        total = len(self.session_messages)
        saved = sum(1 for m in self.session_messages if m['saved_to_db'])
        return f"Всего сообщений: {total}, Сохранено: {saved}"
```

**Интеграция в orchestrator:**
```python
from core.middleware.message_tracker import MessageTracker

tracker = MessageTracker()

def process_message(user_id, agent_type, message, model_override=None):
    # Отслеживание входящего
    tracker.track_message(user_id, agent_type, 'user', message, saved=False)
    
    # ... основная логика ...
    
    # Отслеживание ответа
    tracker.track_message(user_id, agent_type, 'assistant', response, saved=True)
    
    return response
```

#### Решение 1.3: Проверка целостности базы данных

**Создать скрипт `core/utils/db_health_check.py`:**
```python
import sqlite3
import os
from datetime import datetime, timedelta

def check_db_health(db_path='data/memory_v2.sqlite'):
    """Проверка здоровья базы данных"""
    
    if not os.path.exists(db_path):
        return {"status": "error", "message": "База данных не найдена"}
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. Проверка структуры
    cur.execute("PRAGMA table_info(chat_history)")
    columns = {col[1] for col in cur.fetchall()}
    required = {'id', 'user_id', 'agent_type', 'role', 'content', 'timestamp'}
    missing = required - columns
    
    # 2. Статистика
    cur.execute("SELECT COUNT(*) FROM chat_history")
    total_messages = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM chat_history WHERE deleted_at IS NULL")
    active_messages = cur.fetchone()[0]
    
    # 3. Проверка на пустые сообщения
    cur.execute("SELECT COUNT(*) FROM chat_history WHERE content IS NULL OR content = ''")
    empty_messages = cur.fetchone()[0]
    
    # 4. Проверка последних 24 часов
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    cur.execute("SELECT COUNT(*) FROM chat_history WHERE timestamp > ?", (yesterday,))
    recent_messages = cur.fetchone()[0]
    
    conn.close()
    
    return {
        "status": "ok" if not missing else "warning",
        "missing_columns": list(missing),
        "total_messages": total_messages,
        "active_messages": active_messages,
        "empty_messages": empty_messages,
        "messages_24h": recent_messages,
        "health_score": calculate_health_score(total_messages, empty_messages, recent_messages)
    }

def calculate_health_score(total, empty, recent):
    """Оценка здоровья 0-100"""
    if total == 0:
        return 0
    
    empty_ratio = empty / total if total > 0 else 1
    recent_ratio = recent / total if total > 0 else 0
    
    score = 100
    score -= empty_ratio * 50  # Штраф за пустые
    score += recent_ratio * 20  # Бонус за активность
    
    return max(0, min(100, score))

if __name__ == "__main__":
    report = check_db_health()
    print("=== DB Health Report ===")
    for key, value in report.items():
        print(f"{key}: {value}")
```

---

### Проблема 2: Чтение информации из долговременной памяти

#### Решение 2.1: Улучшение загрузки контекста в System Prompt

**Текущая проблема:**
```python
# В orchestrator_v2.py
def node_handler(state: AgentState):
    agent_type = state.get('agent_type', 'general')
    # System prompt задается статически
    system_prompt = SYSTEM_PROMPTS.get(agent_type, 'Ты помощник')
```

**Предложение - динамический System Prompt:**
```python
def build_system_prompt(agent_type: str, user_id: str) -> str:
    """Построение System Prompt с учетом долговременной памяти"""
    
    # 1. Базовый промпт
    base_prompt = SYSTEM_PROMPTS.get(agent_type, 'Ты помощник')
    
    # 2. Загрузка активной памяти
    active_memory = load_active_memory(agent_type)
    
    # 3. Загрузка профиля пользователя (если есть)
    user_profile = load_user_profile(agent_type, user_id)
    
    # 4. Загрузка последних решений (ADR)
    recent_decisions = load_recent_decisions(agent_type, limit=5)
    
    # 5. Сборка полного промпта
    full_prompt = f"""
{base_prompt}

## ДОЛГОВРЕМЕННАЯ ПАМЯТЬ

### Активный контекст:
{active_memory}

### Профиль пользователя:
{user_profile}

### Недавние решения:
{recent_decisions}

## ПРАВИЛА
- Всегда учитывай информацию из долговременной памяти
- Если информация устарела, сообщи об этом
- Обновляй память при важных событиях
"""
    
    return full_prompt

def load_active_memory(agent_type: str) -> str:
    """Загрузка active_memory.md для агента"""
    
    memory_files = {
        'general': 'history/copilot/active_memory.md',
        'german': 'knowledge/german/student_profile.md',
        'career': 'knowledge/career/active_context.md'
    }
    
    file_path = memory_files.get(agent_type)
    if not file_path or not os.path.exists(file_path):
        return "Нет данных в долговременной памяти"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Берем только последние N строк для экономии токенов
            lines = content.split('\n')
            return '\n'.join(lines[-50:])  # Последние 50 строк
    except Exception as e:
        logging.error(f"Ошибка загрузки памяти: {e}")
        return "Ошибка загрузки памяти"

def load_recent_decisions(agent_type: str, limit: int = 5) -> str:
    """Загрузка последних архитектурных решений"""
    
    # Поиск секций ### Snapshot в active_memory.md
    memory_path = f'history/{agent_type}/active_memory.md'
    if not os.path.exists(memory_path):
        return "Нет записей о решениях"
    
    with open(memory_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Извлечение последних snapshot
    snapshots = re.findall(r'### 🕒 Snapshot \[.*?\]\n- \*\*Decision:\*\* (.*?)(?=\n\n|\Z)', 
                           content, re.DOTALL)
    
    recent = snapshots[-limit:] if len(snapshots) > limit else snapshots
    
    return '\n'.join([f"- {decision.strip()}" for decision in recent])
```

**Интеграция:**
```python
def node_handler(state: AgentState):
    agent_type = state.get('agent_type', 'general')
    user_id = state.get('user_id')
    
    # НОВОЕ: Динамический System Prompt
    system_prompt = build_system_prompt(agent_type, user_id)
    
    system_msg = SystemMessage(content=system_prompt)
    # ... остальная логика
```

#### Решение 2.2: Добавить explicit memory tool

**Создать `core/skills/memory_manager.py`:**
```python
from langchain.tools import tool

@tool
def read_memory(query: str, agent_type: str = "general") -> str:
    """
    Читает информацию из долговременной памяти по запросу.
    
    Args:
        query: Что нужно найти (например: "последний план обучения")
        agent_type: Тип агента (german, career, general)
    
    Returns:
        Найденная информация или сообщение об отсутствии данных
    """
    
    memory_paths = {
        'german': 'knowledge/german/',
        'career': 'knowledge/career/',
        'general': 'history/copilot/'
    }
    
    base_path = memory_paths.get(agent_type, 'knowledge/')
    
    # Поиск по файлам
    results = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.md'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Простой текстовый поиск (можно заменить на semantic search)
                        if query.lower() in content.lower():
                            results.append({
                                'file': file,
                                'path': file_path,
                                'excerpt': extract_excerpt(content, query)
                            })
                except:
                    continue
    
    if not results:
        return f"В памяти '{agent_type}' не найдено информации по запросу: {query}"
    
    # Форматирование результатов
    output = f"Найдено {len(results)} совпадений:\n\n"
    for r in results[:3]:  # Топ-3
        output += f"**{r['file']}:**\n{r['excerpt']}\n\n"
    
    return output

@tool
def update_memory(key: str, value: str, agent_type: str = "general") -> str:
    """
    Обновляет информацию в долговременной памяти.
    
    Args:
        key: Ключ (например: "current_focus")
        value: Новое значение
        agent_type: Тип агента
    
    Returns:
        Статус операции
    """
    
    memory_file = f'history/{agent_type}/active_memory.md'
    
    if not os.path.exists(memory_file):
        return f"Файл памяти не найден: {memory_file}"
    
    try:
        with open(memory_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Добавление нового snapshot
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_entry = f"\n\n### 🕒 Snapshot [{timestamp}]\n- **{key}**: {value}\n"
        
        with open(memory_file, 'a', encoding='utf-8') as f:
            f.write(new_entry)
        
        return f"Память обновлена: {key} = {value}"
    
    except Exception as e:
        return f"Ошибка обновления памяти: {e}"

def extract_excerpt(content: str, query: str, context_lines: int = 2) -> str:
    """Извлечение фрагмента с контекстом"""
    lines = content.split('\n')
    query_lower = query.lower()
    
    for i, line in enumerate(lines):
        if query_lower in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            return '\n'.join(lines[start:end])
    
    return content[:200]  # Первые 200 символов
```

**Подключение к агенту:**
```python
from core.skills.memory_manager import read_memory, update_memory

def get_tools_for_agent(agent_type):
    tools = []
    
    # Базовые tools
    if agent_type == 'german':
        tools.extend([...])
    
    # Добавляем memory tools для всех агентов
    tools.extend([read_memory, update_memory])
    
    return tools
```

#### Решение 2.3: Использование NotebookLM через MCP

**Текущая реализация:**
✅ NotebookLM уже интегрирован через **MCP (Model Context Protocol)**

**MCP - что это:**
- Стандартизированный протокол от Anthropic
- Подключение внешних источников контекста к LLM
- Автоматическая синхронизация с базой знаний

**Текущие возможности:**
- Автоматические выжимки документов
- Поиск связей между заметками
- Генерация insights

**Дополнительно (локальный анализ через Ollama):**

Для задач, требующих приватности, можно использовать локальную модель:

```python
# core/notebook_lm/local_analyzer.py
import requests
from typing import Dict

class LocalAnalyzer:
    """Локальный анализ через Ollama (дополнение к MCP)"""
    
    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url
        self.model = "llama3.1:8b"
    
    def quick_summary(self, doc_path: str) -> str:
        """Быстрая выжимка для приватных данных"""
        
        with open(doc_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        prompt = f"""
Создай краткую выжимку (2-3 предложения):

{content[:2000]}  # Первые 2000 символов

Выжимка:"""
        
        response = requests.post(
            f"{self.ollama_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False}
        )
        
        if response.status_code == 200:
            return response.json()['response']
        
        return "Ошибка генерации выжимки"
```

**Рекомендация:**
- Использовать **MCP NotebookLM** для основных задач анализа
- Использовать **Ollama локально** только для приватных/конфиденциальных данных
- Не дублировать функциональность NotebookLM

---

## 🗺️ План внедрения улучшений

### Фаза 1: Диагностика (1-2 дня)

- [ ] Запустить `db_health_check.py` на текущей базе
- [ ] Добавить `MessageTracker` для отслеживания
- [ ] Собрать логи за 24 часа работы
- [ ] Определить точные места потери данных

### Фаза 2: Исправление истории (2-3 дня)

- [ ] Обновить `save_message()` с валидацией
- [ ] Добавить колонку `metadata` в БД
- [ ] Улучшить логирование
- [ ] Протестировать сохранение 100 сообщений

### Фаза 3: Улучшение памяти (3-5 дней)

- [ ] Реализовать `build_system_prompt()` с динамической загрузкой
- [ ] Создать `memory_manager.py` с tools `read_memory` и `update_memory`
- [ ] Подключить memory tools ко всем агентам
- [ ] Протестировать чтение из `active_memory.md`

### Фаза 4: Расширение MCP NotebookLM (3-5 дней)

- [ ] Изучить текущую MCP интеграцию
- [ ] Добавить Ollama для приватных данных
- [ ] Настроить автоматические выжимки
- [ ] Тестирование MCP workflow

### Фаза 5: Тестирование и оптимизация (2-3 дня)

- [ ] End-to-end тесты всей цепочки
- [ ] Нагрузочное тестирование (1000 сообщений)
- [ ] Оптимизация запросов к БД
- [ ] Документирование изменений

---

## 📊 Метрики успеха

### Для истории сообщений:
- **Целевая метрика**: 100% сообщений сохраняются корректно
- **Измерение**: 0 пустых записей в БД после 100 сообщений
- **Health Score**: > 90 баллов

### Для долговременной памяти:
- **Целевая метрика**: Модель использует память в 80% случаев
- **Измерение**: Явные ссылки на `active_memory.md` в ответах
- **Латентность**: < 100ms на загрузку контекста

### Для MCP NotebookLM:
- **Целевая метрика**: Автоматические insights по запросу
- **Интеграция**: Бесшовная работа с Obsidian через MCP
- **Приватность**: Локальная Ollama для конфиденциальных данных

---

## 🔧 Быстрые победы (Quick Wins)

Эти изменения можно внедрить в течение нескольких часов:

### 1. Добавить явное логирование
```python
import logging
logging.basicConfig(
    filename='data/agents.log',
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# В каждой критической точке
logging.info(f"Saving message: user={user_id}, agent={agent_type}")
```

### 2. Проверка на пустые сообщения
```python
def save_message(...):
    if not content or content.strip() == "":
        logging.warning("Attempted to save empty message")
        return False
    # ... остальная логика
```

### 3. Загрузка active_memory в System Prompt
```python
def get_system_prompt(agent_type):
    base = SYSTEM_PROMPTS[agent_type]
    
    # Добавить active memory
    memory_path = f'history/{agent_type}/active_memory.md'
    if os.path.exists(memory_path):
        with open(memory_path, 'r') as f:
            memory = f.read()[-500:]  # Последние 500 символов
        base += f"\n\n## Контекст сессии:\n{memory}"
    
    return base
```

---

## 📝 Дополнительные рекомендации

### 1. Миграция на Obsidian для планов

**Создать структуру:**
```
obsidian_vault/
├── Projects/
│   └── Agents/
│       ├── Overview.md          # Главный обзор
│       ├── Architecture.md      # Архитектура
│       ├── Improvements.md      # Этот файл
│       ├── Roadmap.md          # Дорожная карта
│       └── Daily Notes/        # Ежедневные записи
```

**Преимущества:**
- Bidirectional links между документами
- Граф связей из коробки
- Поиск по всем заметкам
- Интеграция с агентами

### 2. Интеграция FastAPI на VDS

Проверить текущую реализацию:
```python
# app.py или main.py
# Должно быть:
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}

# А не Streamlit
```

### 3. NotebookLM через MCP ✅

**Уже интегрировано:**
- NotebookLM подключен через Model Context Protocol (MCP)
- Автоматические выжимки и анализ связей
- Интеграция с Obsidian Vault

**Дополнительные инструменты:**
- **Obsidian Graph View** - встроенная визуализация связей
- **Dataview plugin** - SQL-подобные запросы к заметкам
- **Ollama локально** - для приватных данных

---

## 🎯 Приоритизация

### Критично (делать сейчас):
1. ✅ Диагностика БД (`db_health_check.py`)
2. ✅ Исправление `save_message()`
3. ✅ Динамический System Prompt с памятью

### Важно (следующие 1-2 недели):
4. Memory tools (`read_memory`, `update_memory`)
5. Message tracker для отладки
6. Миграция планов в Obsidian

### Желательно (backlog):
7. Расширение MCP NotebookLM возможностей
8. Локальная Ollama для приватных insights
9. Визуализация knowledge graph в UI

---

*Документ создан: 2026-04-25*  
*Следующий review: После внедрения Фазы 1*
