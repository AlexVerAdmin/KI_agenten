#!/usr/bin/env python3
"""
obsidian_watcher.py — синхронизация избранных папок Obsidian → NotebookLM

Следит за изменениями .md файлов и поддерживает блокнот NotebookLM актуальным.
Локальный индекс хранит соответствие путь → source_id (для удаления).

Запуск:
  python -m src.utils.obsidian_watcher          # режим слежения
  python -m src.utils.obsidian_watcher --sync   # первичная синхронизация
  python -m src.utils.obsidian_watcher --status # состояние индекса
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from watchfiles import awatch, Change

# ─── Конфигурация ────────────────────────────────────────────────────────────

NOTEBOOK_ID  = os.environ.get("NOTEBOOKLM_NOTEBOOK_ID", "5b649e8b-ebde-46b8-986a-61b91de96c6f")
VAULT_PATH   = Path(os.environ.get("OBSIDIAN_VAULT", Path.home() / "Obsidian"))
VENV_BIN     = Path(__file__).parents[2] / "venv/bin"

# Только эти папки попадают в NotebookLM — остальное приватное
WATCH_FOLDERS = [
    "01_Projects",
    "02_System_Admin",
]

INDEX_PATH = Path.home() / ".config/obsidian_watcher/index.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("watcher")


# ─── Индекс (path → source_id) ───────────────────────────────────────────────

def load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {}


def save_index(index: dict) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def rel(path: Path) -> str:
    """Относительный путь от корня vault-а."""
    return str(path.relative_to(VAULT_PATH))


def should_watch(path: Path) -> bool:
    """Только .md файлы из разрешённых папок."""
    if path.suffix != ".md":
        return False
    try:
        parts = path.relative_to(VAULT_PATH).parts
        return len(parts) > 0 and parts[0] in WATCH_FOLDERS
    except ValueError:
        return False


# ─── MCP-операции ────────────────────────────────────────────────────────────

async def source_add(session: ClientSession, path: Path) -> str | None:
    """Добавляет файл как источник. Возвращает source_id или None."""
    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            log.warning("Пропуск пустого файла: %s", rel(path))
            return None

        result = await session.call_tool("source_add", arguments={
            "notebook_id": NOTEBOOK_ID,
            "source_type": "text",
            "text": content,
            "title": path.name,
            "wait": True,
        })
        data = json.loads(result.content[0].text) if result.content else {}
        source_id = data.get("id") or data.get("source_id")
        if source_id:
            log.info("✅ Добавлен: %s → %s", rel(path), source_id)
        else:
            log.warning("⚠️  source_add не вернул id для %s: %s", rel(path), data)
        return source_id
    except Exception as e:
        log.error("❌ source_add ошибка для %s: %s", rel(path), e)
        return None


async def source_delete(session: ClientSession, source_id: str, label: str = "") -> bool:
    """Удаляет источник по id. Возвращает True при успехе."""
    try:
        await session.call_tool("source_delete", arguments={
            "source_id": source_id,
            "confirm": True,
        })
        log.info("🗑️  Удалён: %s (%s)", label, source_id)
        return True
    except Exception as e:
        log.error("❌ source_delete ошибка для %s: %s", source_id, e)
        return False


async def reconcile(session: ClientSession, index: dict) -> dict:
    """
    Сверяет локальный индекс с реальным состоянием блокнота.
    Удаляет из индекса source_id которых нет в блокноте.
    """
    try:
        result = await session.call_tool("notebook_get", arguments={"notebook_id": NOTEBOOK_ID})
        data = json.loads(result.content[0].text)
        remote_ids = {s["id"] for s in data.get("sources", [])}
        stale = [k for k, v in index.items() if v not in remote_ids]
        for key in stale:
            log.warning("🔄 Индекс устарел, убираю: %s", key)
            del index[key]
        return index
    except Exception as e:
        log.error("❌ reconcile ошибка: %s", e)
        return index


# ─── Синхронизация ───────────────────────────────────────────────────────────

async def initial_sync(session: ClientSession) -> dict:
    """
    Первичная синхронизация: добавляет все .md из WATCH_FOLDERS которых нет в индексе.
    Если файл уже в индексе — пропускает.
    """
    index = load_index()
    index = await reconcile(session, index)

    files = []
    for folder in WATCH_FOLDERS:
        folder_path = VAULT_PATH / folder
        if folder_path.exists():
            files.extend(p for p in folder_path.rglob("*.md") if p.is_file())

    new_files = [f for f in files if rel(f) not in index]
    log.info("Первичная синхронизация: %d файлов, %d новых", len(files), len(new_files))

    for path in new_files:
        source_id = await source_add(session, path)
        if source_id:
            index[rel(path)] = source_id
            save_index(index)

    return index


# ─── Обработка событий ───────────────────────────────────────────────────────

async def handle_event(session: ClientSession, index: dict, change: Change, path: Path) -> None:
    key = rel(path)

    if change == Change.deleted:
        if key in index:
            await source_delete(session, index[key], label=key)
            del index[key]
            save_index(index)
        return

    if change in (Change.added, Change.modified):
        # Если уже есть — удаляем старую версию перед добавлением новой
        if key in index:
            await source_delete(session, index[key], label=f"(старая версия) {key}")
            del index[key]

        source_id = await source_add(session, path)
        if source_id:
            index[key] = source_id
            save_index(index)


# ─── Главный цикл ────────────────────────────────────────────────────────────

async def run_watch() -> None:
    server_params = StdioServerParameters(
        command=str(VENV_BIN / "notebooklm-mcp"),
        args=[],
        env=os.environ.copy(),
    )

    log.info("🔌 Подключение к NotebookLM MCP...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            log.info("✅ Подключено. Блокнот: %s", NOTEBOOK_ID)

            index = await initial_sync(session)

            watch_paths = [VAULT_PATH / f for f in WATCH_FOLDERS if (VAULT_PATH / f).exists()]
            log.info("👁️  Слежение за: %s", [str(p) for p in watch_paths])

            async for changes in awatch(*watch_paths):
                for change, path_str in changes:
                    path = Path(path_str)
                    if should_watch(path):
                        await handle_event(session, index, change, path)


async def run_status() -> None:
    index = load_index()
    if not index:
        print("Индекс пуст — запустите --sync")
        return
    print(f"Индекс: {len(index)} файлов")
    for path, source_id in sorted(index.items()):
        print(f"  {path:60s}  {source_id}")


# ─── Точка входа ─────────────────────────────────────────────────────────────

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--watch"

    if mode == "--status":
        asyncio.run(run_status())

    elif mode == "--sync":
        async def sync_only():
            server_params = StdioServerParameters(
                command=str(VENV_BIN / "notebooklm-mcp"),
                args=[],
                env=os.environ.copy(),
            )
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    index = await initial_sync(session)
                    log.info("✅ Синхронизация завершена: %d файлов в индексе", len(index))
        asyncio.run(sync_only())

    else:
        try:
            asyncio.run(run_watch())
        except KeyboardInterrupt:
            log.info("Остановлено")


if __name__ == "__main__":
    main()
