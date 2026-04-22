"""
Telegram Gateway.
Принимает сообщения → определяет агента по теме → вызывает router.process().
Ответ: голосовое сообщение (если есть audio_path) + подпись, иначе текст.
"""

import os
import sys
import json
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Docker path
sys.path.insert(0, '/app')

# Импорт агентов — они регистрируются в router при импорте
import src.agents.tutor  # noqa: F401

from src.gateway.router import process, AGENT_LABELS
from src.db.conversations import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOPICS_FILE = '/app/data/topics.json'


def load_topics() -> dict:
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_topics(topics: dict):
    os.makedirs(os.path.dirname(TOPICS_FILE), exist_ok=True)
    with open(TOPICS_FILE, 'w') as f:
        json.dump(topics, f, indent=4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Шлюз готов!\n"
        "Команды:\n"
        "/bind_tutor — привязать ветку к учителю немецкого\n"
    )


async def bind_tutor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id
    if not thread_id:
        await update.message.reply_text("Используйте команду внутри темы/форума.")
        return
    topics = load_topics()
    topics[str(thread_id)] = 'tutor'
    save_topics(topics)
    label = AGENT_LABELS.get('tutor', 'tutor')
    await update.message.reply_text(f'✅ Ветка привязана к {label}')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    thread_id = str(update.message.message_thread_id)
    topics = load_topics()
    if thread_id not in topics:
        return

    agent = topics[thread_id]
    voice_path = None
    user_text = None

    # Скачать голосовой файл
    if update.message.voice:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_path = f'/tmp/{update.message.voice.file_id}.ogg'
        await voice_file.download_to_drive(voice_path)
    elif update.message.text:
        user_text = update.message.text
    else:
        return

    try:
        result = await process(
            agent=agent,
            user_input=user_text or "",
            source="telegram",
            voice_path=voice_path,
        )
    except Exception as e:
        logger.error(f"Router error: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Ошибка: {e}")
        return
    finally:
        if voice_path and os.path.exists(voice_path):
            os.remove(voice_path)

    # Отправить ответ
    audio_path = result.get("audio_path")
    text = result.get("text", "")

    if audio_path and os.path.exists(audio_path):
        with open(audio_path, 'rb') as audio:
            await context.bot.send_voice(
                chat_id=update.effective_chat.id,
                message_thread_id=update.message.message_thread_id,
                voice=audio,
                caption=text[:1024] if text else None,
            )
    else:
        await update.message.reply_text(text)


TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
application = ApplicationBuilder().token(TOKEN).build() if TOKEN else None


def run():
    if not application:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    init_db()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('bind_tutor', bind_tutor))
    application.add_handler(
        MessageHandler((filters.TEXT | filters.VOICE) & (~filters.COMMAND), handle_message)
    )
    application.run_polling()


if __name__ == '__main__':
    run()
