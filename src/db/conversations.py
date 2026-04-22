"""
Единое хранилище разговоров для всех агентов и всех интерфейсов.
Telegram и Web читают/пишут в одну БД — история общая.

Схема:
  messages(id, agent, source, role, content, audio_path, timestamp)
    agent:  "tutor" | "career" | "finance" | "secretary" | ...
    source: "telegram" | "web"
    role:   "user" | "assistant"
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(os.environ.get("SQLITE_DB_PATH", "/app/data/conversations.sqlite"))


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                agent      TEXT    NOT NULL,
                source     TEXT    NOT NULL DEFAULT 'telegram',
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                audio_path TEXT,
                timestamp  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_agent_time
                ON messages(agent, timestamp);
        """)


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_message(
    agent: str,
    role: str,
    content: str,
    source: str = "telegram",
    audio_path: str = None,
) -> int:
    """Сохраняет сообщение и возвращает его id."""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO messages (agent, source, role, content, audio_path, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (agent, source, role, content, audio_path, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def get_history(agent: str, limit: int = 20) -> list[dict]:
    """Возвращает последние N пар сообщений для агента."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT role, content, source, timestamp FROM messages"
            " WHERE agent = ? ORDER BY id DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_history_text(agent: str, limit: int = 20) -> str:
    """История в виде строки для system prompt."""
    msgs = get_history(agent, limit)
    if not msgs:
        return ""
    lines = []
    for m in msgs:
        label = "Alex" if m["role"] == "user" else "Agent"
        lines.append(f"{label}: {m['content']}")
    return "\n".join(lines)


def get_recent_messages(agent: str, limit: int = 50) -> list[dict]:
    """Для Web UI: возвращает сообщения с audio_path."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, role, content, audio_path, source, timestamp FROM messages"
            " WHERE agent = ? ORDER BY id DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
