# Файл: config.py
# Этот файл содержит все конфигурационные переменные бота.
# Мы используем .env для хранения секретов, чтобы они не попадали в код или логи.

import os  # Импорт модуля os для работы с операционной системой, путями и переменными окружения.
from dotenv import load_dotenv  # Импорт функции load_dotenv из библиотеки python-dotenv для загрузки переменных из .env файла.

load_dotenv()  # Вызов функции load_dotenv(), которая загружает переменные из файла .env в системные переменные окружения. Это позволяет безопасно хранить токены и ID.

# Основная конфигурация (из .env)
# Здесь мы присваиваем переменным значения из окружения или дефолтные.
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN не задан! Создайте файл .env с BOT_TOKEN=ваш_токен")

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
if ADMIN_ID == 0:
    raise ValueError("❌ ADMIN_ID не задан! Укажите ADMIN_ID в .env файле")

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ
SUPPORTED_FORMATS = frozenset({
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.txt', '.rtf', '.jpg', '.jpeg', '.png',
    '.gif', '.bmp', '.tiff', '.tif'
})

# Настройки печати
# Здесь настройки для печати, загружаемые из .env или с дефолтами.
DEFAULT_SHEETS_PER_SIGNATURE = int(os.getenv('DEFAULT_SHEETS', '5'))  # Получаем дефолтное количество листов на сигнатуру, преобразовываем в int.
DEFAULT_COPIES = int(os.getenv('DEFAULT_COPIES', '1'))  # Получаем дефолтное количество копий, преобразовываем в int.
PRINTER_NAME = os.getenv('PRINTER_NAME', 'Xerox_WorkCentre_3220')  # Получаем имя принтера из .env, с дефолтом.

# Настройки сканирования
# Здесь опции для сканирования.
SCANNER_DEVICE = os.getenv('SCANNER_DEVICE', 'xerox_mfp:libusb:001:004')  # Получаем устройство сканера из .env, с дефолтом. Это может быть переопределено автоопределением.
SCAN_OPTIONS = {  # Создаем словарь (dict) с опциями сканирования. Словарь - это коллекция ключ-значение.
    'format': 'pnm',  # Ключ 'format' со значением 'pnm' - формат вывода сканирования.
    'resolution': '600',  # Ключ 'resolution' со значением '600' - разрешение в DPI.
    'mode': 'Lineart'  # Ключ 'mode' со значением 'Lineart' - режим сканирования (черно-белый).
}

# Файлы
# Здесь пути к файлам.
ALLOWED_USERS_FILE = "allowed_users.json"  # Присваиваем строковое значение - имя файла для хранения разрешенных пользователей.