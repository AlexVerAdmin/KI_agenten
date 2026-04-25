#!/bin/bash
echo "=== Установка Playwright и Chromium ==="
echo "Пожалуйста, введите пароль sudo для установки системных зависимостей:"
sudo apt-get update && sudo apt-get install -y libgbm1 libasound2 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libpango-1.0-0 libcairo2
./.venv/bin/pip install playwright
./.venv/bin/playwright install chromium
echo "=== Установка завершена ==="
