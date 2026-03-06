# Personal Agents 🚀 — Distributed Multi-Agent AI System

**Personal Agents** — это высокопроизводительная гибридная ИИ-платформа, объединяющая облачные вычисления (VDS) и мощности домашней лаборатории (Private Home Lab) в единую экосистему. Проект реализует концепцию **Multi-Agent RAG (Retrieval-Augmented Generation)** для управления персональными знаниями (Obsidian, документы) и автоматизации экспертных задач.

---

## 🛠 Технологический стек (Tech Stack)

*   **Orchestration:** [LangGraph](https://www.langchain.com/langgraph) (Stateful Multi-Agent workflows), LangChain.
*   **LLM Ecosystem:** 
    *   **Cloud:** Google Gemini 3.1 Pro (Preview), 2.5 Pro/Flash, 2.0 Flash (via Google Generative AI SDK).
    *   **High-Speed Inference:** Llama 3.3 70B & 3.1 70B (via [Groq API](https://groq.com/)).
    *   **On-Premise:** Llama 3.1 8B, Mistral Nemo (via [Ollama](https://ollama.com/)).
*   **Backend & API:** Python 3.10+, FastAPI (Worker API), Uvicorn.
*   **Database & Vector Search:** 
    *   **RDBMS:** SQLite3 (Chat Persistence & Agent Settings).
    *   **Vector DB:** ChromaDB (Knowledge indexing).
*   **Infrastructure:** Docker & Docker Compose (Hybrid Cloud Strategy), NFS (Network File System) для синхронизации данных.
*   **UI/UX:** Streamlit (Admin Dashboard), Telegram Standard Bot API (Mobile access).
*   **AI Ops:** Python-dotenv, Pydantic Settings (Environment Management).

---

## 🏗 Ключевые архитектурные решения

### 1. Гибридная Cloud-Edge Архитектура (Hybrid Deployment)
Система разделена на два контура для оптимизации ресурсов и приватности:
*   **VDS (Cloud Node):** Запускает легковесный Streamlit UI и оркестратор LangGraph. Это обеспечивает доступность 24/7 и минимальный расход оперативной памяти (оптимизировано до <500MB RAM).
*   **Home Lab (Worker Node):** Выполняет ресурсоемкие задачи — векторный поиск по 10ГБ+ документов и запуск локальных LLM на GPU. Связь осуществляется через защищенный API-воркер и WireGuard туннель.

### 2. Динамическая маршрутизация моделей (Dynamic Model Selection)
Реализована система сохранения состояния (Persistence): пользователи могут на лету переключать LLM для каждого агента в интерфейсе. Настройки сохраняются в SQLite и применяются мгновенно без перезагрузки системы.

### 3. Распределенный RAG через NFS
Агенты имеют прямой доступ к "Второму мозгу" (Obsidian Vault и рабочие документы) через NFS-монтирование. Это исключает задержки на копирование файлов и гарантирует, что ИИ всегда оперирует актуальными данными.

---

## 🔥 Экспертные Агенты

*   **🎓 Herr Max Klein (Учитель немецкого):** Специализируется на лингвистическом анализе, использует Gemini 3.1 Pro для глубокого понимания контекста.
*   **🚀 VDS & Local Admin (DevOps):** Имеют доступ к системным инструментам, мониторингу Docker-контейнеров и анализу состояния GPU через кастомные LangChain Tools.
*   **💼 HR-Expert:** Интегрирован с базой данных вакансий и резюме для подготовки к интервью и анализа карьерного трека.
*   **🧠 General Assistant:** Оптимизирован под скорость с использованием Groq Llama 3.3 70B.

---

## 💎 Почему это важно для бизнеса (Value Proposition)

1.  **Cost Efficiency:** Снижение затрат на облачные GPU за счет выноса тяжелых вычислений на собственное железо.
2.  **Data Sovereignty:** Конфиденциальные документы Obsidian никогда не покидают частный контур при использовании локальных моделей.
3.  **Scalability:** Архитектура на базе LangGraph позволяет легко добавлять новые узлы (Worker Nodes) или новых специализированных агентов.
4.  **Zero Latency RAG:** Индексация данных происходит локально, обеспечивая мгновенный поиск по тысячам файлов.

---

## 🚀 Как запустить (Quick Start)

### Cloud Setup (VDS)
```bash
docker compose up -d --build
```

### Local Worker (Home Lab)
```bash
docker compose -f docker-compose.local.yml up -d --build
```

---

## 🛠 Установка и Настройка

### Предварительные условия
- Python 3.10+
- (Опционально) FFmpeg (для работы с аудио в Telegram)

### Шаги запуска
1. **Клонирование и зависимости**:
   ```bash
   git clone https://github.com/your-username/AntigravityAgents.git
   cd AntigravityAgents
   pip install -r requirements.txt
   ```

2. **Настройка окружения**:
   Создайте `.env` на базе шаблона и заполните ключи:
   ```bash
   cp .env.example .env
   ```

3. **Запустите проект**:
   - Веб-интерфейс: `run_ui.bat`
   - Telegram-бот: `run_bot.bat`

Подробное описание архитектуры и файлов проекта можно найти в [project_structure.md](project_structure.md).
