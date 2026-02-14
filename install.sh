#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔍 Проверка системных требований...${NC}"

check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}❌ $1 не найден. Пожалуйста, установите его.${NC}"
        missing_dependencies=1
    else
        echo -e "${GREEN}✅ $1 найден.${NC}"
    fi
}

missing_dependencies=0
check_command python3
check_command scanimage
check_command lp
check_command soffice
check_command gs

if [ $missing_dependencies -ne 0 ]; then
    echo -e "${YELLOW}⚠️  Некоторые системные утилиты отсутствуют. Бот может работать не полностью.${NC}"
    echo "Для установки на Debian/Ubuntu выполните:"
    echo "sudo apt update && sudo apt install -y python3-venv sane-utils cups libreoffice-writer-nogui ghostscript"
fi

echo -e "\n${GREEN}📦 Настройка Python окружения...${NC}"

if [ ! -d "$VENV_DIR" ]; then
    echo "Создаю виртуальное окружение..."
    python3 -m venv "$VENV_DIR"
else
    echo "Виртуальное окружение уже существует."
fi

# Активация venv для скрипта
source "$VENV_DIR/bin/activate"

echo "Обновление pip..."
pip install --upgrade pip

if [ -f "$REQUIREMENTS" ]; then
    echo "Установка зависимостей из requirements.txt..."
    pip install -r "$REQUIREMENTS"
else
    echo -e "${RED}❌ Файл requirements.txt не найден!${NC}"
    exit 1
fi

echo -e "\n${GREEN}⚙️  Проверка конфигурации...${NC}"

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}⚠️  Файл .env не найден.${NC}"
    echo "Создаю шаблон .env.example..."
    cat <<EOF > "$PROJECT_DIR/.env.example"
BOT_TOKEN=ваш_токен_здесь
ADMIN_ID=ваш_id
PRINTER_NAME=Xerox_WorkCentre_3220
SCANNER_DEVICE=xerox_mfp:libusb:001:004
DEFAULT_SHEETS=5
DEFAULT_COPIES=1
EOF
    echo -e "${YELLOW}👉 Создайте .env на основе .env.example и укажите BOT_TOKEN!${NC}"
else
    echo -e "${GREEN}✅ Файл .env найден.${NC}"
fi

echo -e "\n${GREEN}🎉 Установка завершена!${NC}"
echo "Для запуска бота используйте: ./start_bot.sh"
