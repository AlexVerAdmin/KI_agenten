import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

HISTORY_FILE = "/home/alex/Work/anti/knowledge/tutor/history.md"

def append_to_history(role: str, text: str):
    """Сохраняем историю переписки в базу знаний (Obsidian)"""
    # Гарантируем, что папка существует
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"**{role}**: {text}\n\n")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "Hallo! Ich bin dein Deutschlehrer. Lass uns anfangen! (Привет! Я твой учитель немецкого. Давай начнем!)"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=msg)
    append_to_history("System", f"Новая сессия начата пользователем {update.effective_user.first_name}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    append_to_history("Alex (Student)", user_text)
    
    # -------------------------------------------------------------
    # TODO: Здесь будет подключение Google Gemini API или локальной Gemma
    # -------------------------------------------------------------
    tutor_reply = f"[Заглушка ИИ] Du hast gesagt: {user_text}. (Мы еще не подключили API)"
    
    append_to_history("Tutor (AI)", tutor_reply)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=tutor_reply)

if __name__ == '__main__':
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
         print("ОШИБКА: Переменная окружения TELEGRAM_BOT_TOKEN не найдена. Пожалуйста, установите её.")
         exit(1)
         
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))
    
    print("ИИ-Репетитор запущен и слушает Telegram...")
    application.run_polling()
