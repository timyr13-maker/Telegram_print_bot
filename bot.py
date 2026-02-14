# Файл: bot.py
# Главный файл для запуска бота.

import logging  # Импорт logging.
from telegram import Update

from telegram.ext import (  # Импорт из telegram.ext.
    Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
)

from config import TOKEN  # Импорт TOKEN.
from utils import cleanup_temp_files, load_allowed_users  # Импорт из utils.
from handlers import (  # Импорт всех обработчиков из handlers.
    start, help_booklet, add_user, remove_user, list_users,
    handle_document_or_photo, button_callback, handle_text_input, error_handler
)

# Настройка логирования (токен не логируется)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Логирует почти каждое входящее обновление.
    Выполняется первым (group=-1).
    """
    user = update.effective_user
    if not user:
        logger.info("Получено обновление без пользователя")
        return

    username = user.username or 'anon'
    user_id = user.id

    if update.message:
        msg_type = 'message'
        text = update.message.text or update.message.caption or '[без текста]'
        if update.message.document:
            text = f"[документ: {update.message.document.file_name or 'без имени'}]"
        elif update.message.photo:
            text = "[фото]"
        elif update.message.voice:
            text = "[голосовое]"
    elif update.callback_query:
        msg_type = 'callback_query'
        text = f"data: {update.callback_query.data}"
    else:
        msg_type = 'другое обновление'
        text = str(update.to_dict())[:200]

    logger.info(f"Обновление от {user_id} (@{username}): {msg_type} — {text}")

def main():
    cleanup_temp_files()
    logger.info("🤖 Запуск бота (600dpi PNM)")
    allowed_users = load_allowed_users()

    application = Application.builder().token(TOKEN).build()

    # Сохраняем allowed_users в bot_data, чтобы обработчики имели к ним доступ
    application.bot_data['allowed_users'] = allowed_users

    # Логгер обновлений — самый первый, group=-1
    application.add_handler(
        MessageHandler(filters.ALL, log_update),
        group=-1
    )
    application.add_handler(
        CallbackQueryHandler(log_update),
        group=-1
    )
    # Handlers
    application.add_handler(CommandHandler("start", start))  # Добавляем обработчик команды /start.
    application.add_handler(CommandHandler("help_booklet", help_booklet))  # /help_booklet.
    application.add_handler(CommandHandler("add_user", add_user))  # /add_user.
    application.add_handler(CommandHandler("remove_user", remove_user))  # /remove_user.
    application.add_handler(CommandHandler("list_users", list_users))  # /list_users.
    application.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_document_or_photo))  # Обработчик документов и фото (| - или в фильтрах).
    application.add_handler(CallbackQueryHandler(button_callback))  # Обработчик callback.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))  # Обработчик текста (& - и, ~ - не).
    application.add_error_handler(error_handler)  # Обработчик ошибок.
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)  # Запускаем polling - опрос обновлений.

if __name__ == '__main__':  # Если файл запущен напрямую (не импортирован).
    main()  # Вызываем main.
