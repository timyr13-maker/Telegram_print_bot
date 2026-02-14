#!/bin/bash
set -e

# Переменные
SERVICE_NAME="tpb-bot"
USER_NAME=$(whoami)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="$PROJECT_DIR/venv/bin/python3"
SCRIPT_PATH="$PROJECT_DIR/bot.py"
SERVICE_FILE="/tmp/$SERVICE_NAME.service"

echo "🔧 Настройка systemd сервиса для пользователя $USER_NAME..."

# Проверка venv
if [ ! -f "$PYTHON_EXEC" ]; then
    echo "❌ Виртуальное окружение не найдено! Запустите ./install.sh"
    exit 1
fi

# Генерация .service файла
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Telegram Print Bot (TPB)
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_EXEC $SCRIPT_PATH
Restart=always
RestartSec=10
EnvironmentFile=$PROJECT_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

echo "📄 Создан временный файл сервиса: $SERVICE_FILE"
echo "🛠 Установка сервиса (потребуется sudo)..."

sudo mv "$SERVICE_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
# sudo systemctl start "$SERVICE_NAME"

echo -e "\n✅ Сервис установлен!"
echo "Команды управления:"
echo "  Запуск:      sudo systemctl start $SERVICE_NAME"
echo "  Остановка:   sudo systemctl stop $SERVICE_NAME"
echo "  Статус:      sudo systemctl status $SERVICE_NAME"
echo "  Логи:        journalctl -u $SERVICE_NAME -f"
echo -e "\n⚠️ Не забудьте запустить сервис командой: sudo systemctl start $SERVICE_NAME"
