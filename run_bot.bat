@echo off
:: DIRECT RUN: This bypasses ExecutionPolicy because it doesn't call .ps1 scripts
echo [1/1] Starting Antigravity Telegram Bot...
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    pause
    exit /b
)

:: Activate venv and run bot
call .\venv\Scripts\activate.bat
python bot.py

pause

pause
