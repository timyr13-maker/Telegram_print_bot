#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "⚠️ Виртуальное окружение не найдено. Сначала запустите ./install.sh"
    exit 1
fi

source "$VENV_DIR/bin/activate"

# Проверка наличия .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "❌ Файл .env не найден! Создайте его перед запуском."
    exit 1
fi

echo "🚀 Запускаем бота..."
python3 bot.py
