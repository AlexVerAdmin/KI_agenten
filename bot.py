import asyncio
import logging
import sys
import os
import tempfile
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from openai import OpenAI
import edge_tts
import uuid
from utils.audio_utils import generate_voice

from config import config

# Configure logging
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Initialize Dispatcher
dp = Dispatcher()

# Configure pydub/ffmpeg path BEFORE importing AudioSegment
# On VDS/Linux ffmpeg is usually in the PATH, on Windows it's in a specific folder
ffmpeg_bin = r"C:\Users\Lenovo\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
if os.path.exists(ffmpeg_bin):
    os.environ["PATH"] += os.pathsep + ffmpeg_bin
    logging.info(f"Adding FFmpeg to PATH: {ffmpeg_bin}")
else:
    # If not found at specific path, it might be in the system PATH (Standard for Linux/Docker)
    logging.info("FFmpeg bin NOT found at specific Windows path, relying on system PATH.")

from pydub import AudioSegment
# Explicitly set paths for pydub ONLY if local path exists
if os.path.exists(ffmpeg_bin):
    AudioSegment.converter = os.path.join(ffmpeg_bin, "ffmpeg.exe")
    AudioSegment.ffmpeg = os.path.join(ffmpeg_bin, "ffmpeg.exe")
    AudioSegment.ffprobe = os.path.join(ffmpeg_bin, "ffprobe.exe")
else:
    # Linux standard paths
    if os.name != 'nt':
        AudioSegment.converter = "ffmpeg"
        AudioSegment.ffmpeg = "ffmpeg"
        AudioSegment.ffprobe = "ffprobe"

async def transcribe_voice(bot: Bot, file_id: str) -> str:
    """
    Downloads voice from Telegram, converts to mp3, and transcribes via Groq Whisper.
    """
    # Groq's Whisper API is compatible with the OpenAI client
    client = OpenAI(api_key=config.groq_api_key, base_url="https://api.groq.com/openai/v1")
    
    # Create temporary file paths
    temp_dir = tempfile.gettempdir()
    voice_oga_path = os.path.join(temp_dir, f"voice_{file_id}.oga")
    voice_mp3_path = os.path.join(temp_dir, f"voice_{file_id}.mp3")
    
    try:
        # Download from Telegram
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, voice_oga_path)
        
        # Convert OGG to MP3 using pydub
        # We wrap it in a try-finally to ensure handles are released
        audio = None
        try:
            audio = AudioSegment.from_file(voice_oga_path)
            audio.export(voice_mp3_path, format="mp3")
        finally:
            if audio:
                del audio
        
        # Transcribe using Groq's Whisper
        # Neutral prompt to allow Whisper to detect either Russian or German naturally.
        with open(voice_mp3_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file
                # Раньше тут был prompt, который заставлял Whisper придумывать начало. Теперь он пустой.
            )
        
        return transcription.text
    finally:
        # Extra care for Windows file handles
        import time
        time.sleep(0.5) # Wait for OS to release files
        for p in [voice_oga_path, voice_mp3_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception as e:
                    logging.warning(f"Could not remove temp file {p}: {e}")

from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_agent_keyboard(current_agent='general'):
    builder = InlineKeyboardBuilder()
    agents = [
        ("general", "🧠 Оркестратор"),
        ("german", "🇩🇪 Учитель (Max Klein)"),
        ("career", "💼 HR-Эксперт"),
        ("finance", "💰 Финансы")
    ]
    for key, name in agents:
        label = f"✅ {name}" if key == current_agent else name
        builder.row(InlineKeyboardButton(text=label, callback_data=f"set_agent:{key}"))
    return builder.as_markup()

@dp.message(Command("agent"))
async def command_agent_handler(message: Message) -> None:
    """Manual agent selection via /agent command"""
    from core.orchestrator import get_user_agent
    current = get_user_agent(str(message.from_user.id))
    await message.answer(f"Текущий агент: {html.bold(current)}\nВыберите активного агента:", reply_markup=get_agent_keyboard(current))

@dp.callback_query(lambda c: c.data.startswith('set_agent:'))
async def process_callback_agent(callback_query: CallbackQuery):
    from core.orchestrator import set_user_agent, AGENT_REGISTRY
    agent_key = callback_query.data.split(":")[1]
    user_id = str(callback_query.from_user.id)
    
    # Мгновенно уведомляем Telegram, чтобы убрать "мигание" (часики)
    await callback_query.answer() 
    
    set_user_agent(user_id, agent_key)
    agent_name = AGENT_REGISTRY[agent_key]['name']
    
    # Обновляем сообщение: ставим галочку на выбранного агента
    await callback_query.message.edit_text(
        f"✅ Активен: {html.bold(agent_name)}\n\nТеперь все сообщения (голос/текст) идут ему.",
        reply_markup=get_agent_keyboard(agent_key)
    )

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    This handler receives messages with `/start` command
    """
    allowed_ids = [vid.strip() for vid in config.allowed_telegram_user_ids.split(",") if vid.strip()]
    if str(message.from_user.id) not in allowed_ids:
        if not allowed_ids:
            await message.answer(f"🔒 Бот работает в приватном режиме.\n\nВаш ID: <code>{message.from_user.id}</code>\nПожалуйста, добавьте эти цифры в файл .env в конец строки ALLOWED_TELEGRAM_USER_IDS и перезапустите бота.")
        else:
            logging.warning(f"Unauthorized access attempt from user ID: {message.from_user.id} ({message.from_user.full_name})")
            await message.answer(f"🔒 Извините, у вас нет доступа к этому боту.")
        return

    # Send a friendly greeting to the user
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}!\n\n"
        f"Я твой персональный AI-ассистент (Оркестратор).\n"
        f"Я готов общаться текстом и голосом!\n\n"
        f"Используйте команду /agent, чтобы выбрать, кому вы сейчас пишете.",
        reply_markup=get_agent_keyboard()
    )

@dp.message(lambda message: message.voice)
async def voice_handler(message: Message) -> None:
    """
    Handler for Telegram voice messages.
    """
    allowed_ids = [vid.strip() for vid in config.allowed_telegram_user_ids.split(",") if vid.strip()]
    if str(message.from_user.id) not in allowed_ids:
        return

    try:
        # Show 'typing' action while processing
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # 1. Transcribe voice to text
        transcribed_text = await transcribe_voice(message.bot, message.voice.file_id)
        
        # Show the user what we heard (for transparency)
        await message.reply(f"🎤 {html.italic(transcribed_text)}")
        
        # 2. Process the transcribed text through the orchestrator
        from core.orchestrator import process_message
        user_id = str(message.from_user.id)
        
        # Re-trigger 'typing' for the AI response generation
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        
        # Process -- let Orchestrator decide the agent (теперь передаем и thread_id)
        response_data = await asyncio.to_thread(process_message, transcribed_text, user_id, thread_id=message.message_thread_id)
        response_text = response_data["text"]
        active_node = response_data.get("active_node")
        
        # Add visual indicator for the active agent
        from core.orchestrator import AGENT_REGISTRY
        agent_name = AGENT_REGISTRY.get(active_node, {}).get("name", "Оркестратор")
        display_text = f"👤 {html.bold(agent_name)}:\n\n{response_text}"
        
        # 3. Generate voice response
        is_german = active_node == "german"
        voice = "de-DE-ConradNeural" if is_german else "ru-RU-DmitryNeural"
        
        voice_path = await generate_voice(response_text, voice)
        
        try:
            from aiogram.types import FSInputFile
            # Используем message.reply, чтобы Телеграм сам направил ответ в нужную тему.
            await message.reply_voice(
                voice=FSInputFile(voice_path), 
                caption=display_text if len(display_text) < 1000 else None
            )
            if len(display_text) >= 1000:
                await message.reply(display_text)
        finally:
            if os.path.exists(voice_path):
                os.remove(voice_path)
        
    except Exception as e:
        logging.error(f"Error handling voice: {e}")
        await message.answer(f"Ошибка при обработке голоса: {e}\n\nПодсказка: Для работы со звуком нужен ffmpeg.")

@dp.message()
async def message_handler(message: Message) -> None:
    """
    Handler receives all text messages and passes them to the LangGraph orchestrator.
    """
    # 1. Защита от системных сообщений (добавление бота, смена названия и т.д.)
    if not message.text and not message.voice:
        return

    # 2. Игнорируем голос (его обрабатывает voice_handler)
    if message.voice:
        return

    allowed_ids = [vid.strip() for vid in config.allowed_telegram_user_ids.split(",") if vid.strip()]
    if str(message.from_user.id) not in allowed_ids:
        return

    try:
        from core.orchestrator import process_message
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        user_id = str(message.from_user.id)
        
        # --- NEW: Темы (Topics) в группах ---
        # Если это группа с темами, выведем ID темы для настройки
        thread_id = message.message_thread_id
        if thread_id:
            logging.info(f"Message from Group Topic ID: {thread_id}")

        # Process -- let Orchestrator decide the agent (теперь передаем и thread_id)
        response_data = await asyncio.to_thread(process_message, message.text, user_id, thread_id=thread_id)
        response_text = response_data["text"]
        
        # Determine if we should respond with voice
        active_node = response_data.get("active_node")
        is_german = active_node == "german"
        
        # Visual indicator
        from core.orchestrator import AGENT_REGISTRY
        agent_name = AGENT_REGISTRY.get(active_node, {}).get("name", "Оркестратор")
        display_text = f"👤 {html.bold(agent_name)}:\n\n{response_text}"
        
        if is_german:
            voice_path = await generate_voice(response_text, "de-DE-ConradNeural")
            try:
                from aiogram.types import FSInputFile
                # В aiogram при вызове message.answer_voice или message.answer 
                # message_thread_id передается автоматически, если это ответ (Reply).
                # Я убираю явную передачу, чтобы не было конфликта.
                await message.reply_voice(
                    voice=FSInputFile(voice_path), 
                    caption=display_text if len(display_text) < 1000 else None
                )
                if len(display_text) >= 1000:
                    await message.reply(display_text)
            finally:
                if os.path.exists(voice_path):
                    os.remove(voice_path)
        else:
            await message.reply(display_text)
            
    except Exception as e:
        logging.error(f"Error handling message: {e}")
        await message.answer(f"Ошибка: {e}")
            
    except Exception as e:
        logging.error(f"Error handling message: {e}")
        await message.answer(f"Ошибка: {e}")


async def main() -> None:
    # Initialize Bot instance with default parse mode
    bot = Bot(
        token=config.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    logging.info("Starting bot...")
    # Start polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
