"""
Точка входа: запускает Telegram бот + FastAPI Web UI параллельно.
Telegram polling работает в отдельном потоке через asyncio.
"""

import asyncio
import logging
import os
import threading
from pathlib import Path

import uvicorn

# Загружаем .env из корня проекта
_env_file = Path(__file__).parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from Agents.src.db.conversations import init_db
from Agents.src.gateway.web import app as web_app

# Импортируем агентов чтобы зарегистрировались в router
import Agents.src.agents.tutor  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def run_web():
    """Запускает FastAPI в отдельном потоке."""
    port = int(os.environ.get("WEB_PORT", 8080))
    uvicorn.run(web_app, host="0.0.0.0", port=port, log_level="info")


async def run_telegram():
    """Запускает Telegram polling."""
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
    from Agents.src.gateway.bot import start, bind_tutor, handle_message

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bind_tutor", bind_tutor))
    app.add_handler(
        MessageHandler((filters.TEXT | filters.VOICE) & (~filters.COMMAND), handle_message)
    )
    await app.initialize()
    await app.start()
    logger.info("Telegram bot started, polling...")
    await app.updater.start_polling()
    # Держим живым пока не получим сигнал
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    init_db()

    # Web в отдельном потоке
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("Web UI started on :8080")

    # Telegram в asyncio
    try:
        asyncio.run(run_telegram())
    except KeyboardInterrupt:
        logger.info("Shutdown")

    # Если Telegram не запущен — держим процесс живым пока работает Web
    if web_thread.is_alive():
        try:
            web_thread.join()
        except KeyboardInterrupt:
            logger.info("Shutdown")


if __name__ == "__main__":
    main()
