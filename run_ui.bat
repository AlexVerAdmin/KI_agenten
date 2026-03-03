@echo off
:: DIRECT RUN: This bypasses ExecutionPolicy because it doesn't call .ps1 scripts
echo [1/1] Starting Antigravity Web UI...
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run install.bat or create venv first.
    pause
    exit /b
)

:: Activate venv and run streamlit
call .\venv\Scripts\activate.bat
python -m streamlit run app.py

pause
