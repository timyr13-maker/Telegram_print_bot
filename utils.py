# Файл: utils.py
# Этот файл содержит вспомогательные функции для работы с пользователями, 
# файлами и проверками.

import os  # Импорт os для работы с файлами и путями.
import json  # Импорт json для чтения/записи JSON файлов.
import logging  # Импорт logging для логирования сообщений.
import tempfile  # Импорт tempfile для создания временных файлов и директорий.
import shutil  # Импорт shutil для копирования файлов.
import re  # Импорт re для регулярных выражений (поиска по шаблонам).
import time  # Импорт time для работы со временем (например, проверка возраста файлов).

from config import ADMIN_ID, ALLOWED_USERS_FILE  # Импорт конкретных переменных из config.py.

logger = logging.getLogger(__name__)  # Создаем объект логгера с именем текущего модуля (__name__ - специальная переменная, равная имени файла без .py).

def load_allowed_users() -> set:  # Определяем функцию load_allowed_users, которая возвращает set (множество уникальных элементов).
    """Загружает список разрешенных пользователей из файла."""  # Docstring - описание функции.
    if os.path.exists(ALLOWED_USERS_FILE):  # Проверяем, существует ли файл с помощью os.path.exists (возвращает True/False).
        try:  # Начинаем блок try для перехвата ошибок.
            with open(ALLOWED_USERS_FILE, 'r') as f:  # Открываем файл на чтение ('r'), with автоматически закрывает файл после блока.
                data = json.load(f)  # Загружаем содержимое файла как JSON в словарь data.
                return set(data.get('allowed_users', []))  # Возвращаем множество из списка по ключу 'allowed_users', get возвращает дефолт [] если ключа нет.
        except Exception as e:  # Ловим любую ошибку (Exception - базовый класс ошибок), сохраняем в e.
            logger.error(f"Ошибка загрузки пользователей: {e}")  # Логируем ошибку с помощью logger.error, f-строка для вставки переменной.
    return {ADMIN_ID}  # Если файл не существует или ошибка, возвращаем множество с одним ADMIN_ID.

def save_allowed_users(allowed_users: set):  # Определяем функцию save_allowed_users с параметром allowed_users (тип set).
    """Сохраняет список разрешенных пользователей в файл."""  # Docstring.
    try:  # Блок try.
        with open(ALLOWED_USERS_FILE, 'w') as f:  # Открываем файл на запись ('w').
            json.dump({'allowed_users': list(allowed_users)}, f)  # Сохраняем словарь с ключом 'allowed_users' и списком из set в JSON.
    except Exception as e:  # Ловим ошибку.
        logger.error(f"Ошибка сохранения пользователей: {e}")  # Логируем.

def is_user_allowed(user_id: int, allowed_users: set) -> bool:  # Функция проверяет доступ, возвращает bool (True/False).
    """Проверяет, есть ли у пользователя доступ."""  # Docstring.
    return user_id in allowed_users  # Возвращаем True если user_id в множестве, иначе False. in - оператор проверки наличия.

def is_admin(user_id: int) -> bool:  # Функция проверяет, является ли пользователь админом.
    """Проверяет, является ли пользователь администратором."""  # Docstring.
    return user_id == ADMIN_ID  # Возвращаем True если user_id равен ADMIN_ID (== - сравнение).

def get_file_extension(filename: str) -> str:  # Функция возвращает расширение файла.
    """Возвращает расширение файла в нижнем регистре."""  # Docstring.
    return os.path.splitext(filename)[1].lower()  # os.path.splitext разбивает на (имя, расширение), [1] - расширение, lower() - в нижний регистр.

def is_office_document(file_ext: str) -> bool:  # Функция проверяет, является ли расширение офисным документом.
    """Проверяет, является ли файл документом Office."""  # Docstring.
    office_extensions = frozenset({'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods'})
    return file_ext in office_extensions

def is_image_file(file_ext: str) -> bool:  # Аналогичная функция для изображений.
    """Проверяет, является ли файл изображением."""  # Docstring.
    image_extensions = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif'})
    return file_ext in image_extensions

def is_text_file(file_ext: str) -> bool:  # Аналогичная функция для текстовых файлов.
    """Проверяет, является ли файл текстовым."""  # Docstring.
    text_extensions = frozenset({'.txt', '.rtf'})
    return file_ext in text_extensions

def create_temp_copy(file_path: str, suffix: str = None) -> str:  # Функция создает временную копию файла.
    """Создает временную копию файла."""  # Docstring.
    if suffix is None:  # Проверяем, если suffix не задан (None - отсутствие значения).
        suffix = os.path.splitext(file_path)[1]  # Получаем расширение из file_path.
    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, prefix='temp_', delete=False)  # Создаем временный файл с суффиксом и префиксом, delete=False - не удалять автоматически.
    temp_file.close()  # Закрываем файл (tempfile.NamedTemporaryFile открывает его).
    shutil.copy2(file_path, temp_file.name)  # Копируем содержимое file_path в новый временный файл.
    return temp_file.name  # Возвращаем путь к временному файлу.

def cleanup_temp_files():  # Функция очищает старые временные файлы.
    """Очищает старые временные файлы (старше 1 часа)."""  # Docstring.
    temp_dir = tempfile.gettempdir()
    pattern = re.compile(r'^(temp_|converted_|image_|gray_|blank_|booklet_|scan_|scanned_)')
    now = time.time()
    try:
        with os.scandir(temp_dir) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False) and pattern.match(entry.name):
                    try:
                        if now - entry.stat().st_mtime > 3600:
                            os.unlink(entry.path)
                            logger.info(f"Очищен старый временный файл: {entry.name}")
                    except Exception as e:
                        logger.error(f"Не удалось удалить {entry.name}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {e}")