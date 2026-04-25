#!/usr/bin/env bash
# Screen Translator — глобальная установка (Ubuntu 24.04+)
set -e

APP_DIR="$HOME/.local/share/screen-translator"
VENV_DIR="$APP_DIR/venv"
BIN_DIR="$HOME/.local/bin"
APPS_DIR="$HOME/.local/share/applications"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$BIN_DIR/translator"
DESKTOP="$APPS_DIR/screen-translator.desktop"

echo "=== Screen Translator — Установка ==="

echo ""
echo "1/4  Системные зависимости (tesseract + tkinter + venv)..."
sudo apt-get update -q
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    tesseract-ocr-rus \
    tesseract-ocr-ukr \
    python3-tk \
    python3-venv \
    python3-dev \
    build-essential \
    gir1.2-ayatana-appindicator3-0.1

echo ""
echo "2/4  Копируем файлы в $APP_DIR ..."
mkdir -p "$APP_DIR"
cp "$SRC_DIR/main.py" "$APP_DIR/main.py"
cp "$SRC_DIR/requirements.txt" "$APP_DIR/requirements.txt"

echo ""
echo "3/4  Python-пакеты в $VENV_DIR ..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

echo ""
echo "4/4  Ярлык в меню приложений и команда 'translator'..."
mkdir -p "$BIN_DIR" "$APPS_DIR"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python" "$APP_DIR/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Screen Translator
Comment=Перевод текста со скриншота (DeepL)
Exec=$LAUNCHER
Icon=accessories-dictionary
Terminal=false
Categories=Utility;Translation;
Keywords=translate;translator;deepl;ocr;
StartupNotify=true
EOF

# Добавляем ~/.local/bin в PATH если его там нет
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
    echo "  Добавлен ~/.local/bin в PATH — выполните: source ~/.bashrc"
fi

echo ""
echo "=== Готово! ==="
echo ""
echo "Запуск из меню:    Поиск → 'Screen Translator'"
echo "Запуск из терминала: translator"
echo "Горячая клавиша:   Ctrl+Shift+T (меняется в Настройках)"
echo ""
echo "API ключ DeepL:    https://www.deepl.com/account/summary"
echo "Бесплатный план:   500 000 символов/месяц, ключ оканчивается на :fx"
