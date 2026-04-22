"""
Модуль долговременной памяти агентов.
Хранит историю сессий в SQLite + векторный индекс в ChromaDB для RAG-поиска.

Таблицы SQLite:
- sessions: session_id, created_at, summary
- messages: id, session_id, role, content, timestamp, agent_name
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "memory.db"


def init_db():
    """Создает базу данных и таблицы при первом запуске."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            created_at  TEXT NOT NULL,
            summary     TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            agent_name  TEXT NOT NULL,
            role        TEXT NOT NULL,  -- 'user' | 'assistant' | 'tool'
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(session_id)
        );
    """)

    conn.commit()
    conn.close()


def new_session() -> str:
    """Создает новую сессию и возвращает её ID."""
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO sessions (session_id, created_at) VALUES (?, ?)",
        (session_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return session_id


def save_message(session_id: str, agent_name: str, role: str, content: str):
    """Сохраняет одно сообщение в историю."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO messages (session_id, agent_name, role, content, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        (session_id, agent_name, role, content, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def save_session_summary(session_id: str, summary: str):
    """Обновляет краткое резюме завершённой сессии."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE sessions SET summary = ? WHERE session_id = ?",
        (summary, session_id)
    )
    conn.commit()
    conn.close()


def get_recent_history(n_sessions: int = 3) -> str:
    """
    Возвращает краткую историю последних N сессий для загрузки в контекст агента.
    Используется в system_message, чтобы агент «помнил» прошлые разговоры.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT session_id, created_at, summary FROM sessions "
        "WHERE summary IS NOT NULL "
        "ORDER BY created_at DESC LIMIT ?",
        (n_sessions,)
    ).fetchall()
    conn.close()

    if not rows:
        return "История сессий пуста."

    lines = ["## Предыдущие сессии:"]
    for session_id, created_at, summary in rows:
        lines.append(f"- [{created_at[:10]}] {summary}")
    return "\n".join(lines)


def get_session_messages(session_id: str) -> list[dict]:
    """Возвращает все сообщения конкретной сессии."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, agent_name, content, timestamp FROM messages "
        "WHERE session_id = ? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [
        {"role": r, "agent": a, "content": c, "timestamp": t}
        for r, a, c, t in rows
    ]


# Инициализация при импорте
init_db()
