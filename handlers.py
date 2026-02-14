# Файл: handlers.py
# Обработчики сообщений и команд для Telegram-бота

import os
import logging
import tempfile
import shutil
import re
import time
import pypdf

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_ID, MAX_FILE_SIZE, SUPPORTED_FORMATS, DEFAULT_SHEETS_PER_SIGNATURE, PRINTER_NAME
from utils import (
    is_user_allowed, is_admin, get_file_extension, is_office_document,
    is_image_file, is_text_file, load_allowed_users, save_allowed_users
)
from conversion import convert_to_pdf, convert_image_to_pdf, convert_pdf_to_grayscale, create_blank_pdf
from printing import calculate_signature_config, create_booklet_for_short_edge, print_file_postscript
from scanning import scan_single_page, scan_multiple_pages, convert_images_to_pdf

logger = logging.getLogger(__name__)


def _build_print_mode_keyboard(is_pdf_or_office: bool) -> list:
    """Возвращает клавиатуру выбора режима печати."""
    if is_pdf_or_office:
        return [
            [InlineKeyboardButton("📄 Обычная", callback_data="print_normal"),
             InlineKeyboardButton("📄 Двусторонняя", callback_data="print_duplex")],
            [InlineKeyboardButton("📖 Брошюрой", callback_data="print_booklet")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
        ]
    return [
        [InlineKeyboardButton("📄 Обычная", callback_data="print_normal_only")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]


def _build_scan_keyboard() -> list:
    """Возвращает клавиатуру для сканирования."""
    return [
        [InlineKeyboardButton("📄 Один лист", callback_data="scan_single")],
        [InlineKeyboardButton("📚 Несколько", callback_data="scan_multiple")],
        [InlineKeyboardButton("❌ Отмена", callback_data="scan_cancel")]
    ]


def _build_page_range_keyboard(page_count: int) -> list:
    """Возвращает клавиатуру выбора диапазона страниц."""
    keyboard = []
    if page_count > 1:
        keyboard += [
            [InlineKeyboardButton("Все страницы", callback_data="print_all")],
            [InlineKeyboardButton("Свои страницы", callback_data="print_custom")]
        ]
    else:
        keyboard += [[InlineKeyboardButton("Печатать", callback_data="print_all")]]
    keyboard += [[InlineKeyboardButton("Назад", callback_data="back_to_menu")]]
    return keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed_users = context.bot_data.get('allowed_users', set())

    if not is_user_allowed(user_id, allowed_users):
        await update.message.reply_text("❌ Доступ запрещен. Обратитесь к администратору.")
        return

    keyboard = [[InlineKeyboardButton("📸 Сканировать", callback_data="start_scan")]]
    welcome_text = (
        f"🤖 Бот для печати и сканирования\n\n"
        f"📎 Отправьте файл для печати\n"
        f"🖼️ Или фото из галереи\n"
        f"📸 Или используйте сканер (кнопка ниже)\n\n"
        f"⚠️ Форматы: {', '.join(sorted(SUPPORTED_FORMATS))}\n"
        f"📏 Макс. размер: {MAX_FILE_SIZE // (1024*1024)} МБ\n\n"
        f"📋 Особенности:\n"
        f"Команды:\n/help_booklet - инструкция по брошюре"
    )
    if is_admin(user_id):
        welcome_text += "\n\n⚙️ Админ: /add_user, /remove_user, /list_users"

    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def help_booklet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed_users = context.bot_data.get('allowed_users', set())

    if not is_user_allowed(user_id, allowed_users):
        await update.message.reply_text("❌ Доступ запрещен")
        return

    instructions = (
        "📘 ПЕЧАТЬ БРОШЮРЫ\n"
        "Доступно для: PDF, DOC, DOCX, XLS, XLSX\n\n"
        "✅ Авто-расчет:\n"
        "• <29 стр. → 1 сигнатура\n"
        "• ≥29 стр. → несколько\n"
    )
    await update.message.reply_text(instructions)


async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только для админа")
        return

    if not context.args:
        await update.message.reply_text("Использование: /add_user <user_id>")
        return

    try:
        new_user_id = int(context.args[0])
        allowed_users = context.bot_data['allowed_users']

        if new_user_id in allowed_users:
            await update.message.reply_text(f"⚠️ Пользователь {new_user_id} уже добавлен")
            return

        allowed_users.add(new_user_id)
        save_allowed_users(allowed_users)
        context.bot_data['allowed_users'] = allowed_users

        await update.message.reply_text(f"✅ Добавлен {new_user_id}")
        logger.info(f"Админ {user_id} добавил {new_user_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный ID (число)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только для админа")
        return

    if not context.args:
        await update.message.reply_text("Использование: /remove_user <user_id>")
        return

    try:
        remove_id = int(context.args[0])
        if remove_id == ADMIN_ID:
            await update.message.reply_text("❌ Нельзя удалить админа")
            return

        allowed_users = context.bot_data['allowed_users']
        if remove_id not in allowed_users:
            await update.message.reply_text(f"⚠️ {remove_id} не найден")
            return

        allowed_users.remove(remove_id)
        save_allowed_users(allowed_users)
        context.bot_data['allowed_users'] = allowed_users

        await update.message.reply_text(f"✅ Удален {remove_id}")
        logger.info(f"Админ {user_id} удалил {remove_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный ID (число)")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Только для админа")
        return

    allowed_users = context.bot_data.get('allowed_users', set())
    if not allowed_users:
        await update.message.reply_text("📋 Список пуст")
        return

    users_list = "📋 Пользователи:\n\n"
    for uid in sorted(allowed_users):
        role = "👑 (админ)" if uid == ADMIN_ID else "👤"
        users_list += f"{role} {uid}\n"
    users_list += f"\nВсего: {len(allowed_users)}"

    await update.message.reply_text(users_list)


async def handle_document_or_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed_users = context.bot_data.get('allowed_users', set())

    if not is_user_allowed(user_id, allowed_users):
        await update.message.reply_text("❌ Доступ запрещен")
        return

    message = update.message
    document = message.document
    photo = message.photo[-1] if message.photo else None
    file_obj = document or photo

    if not file_obj:
        await message.reply_text("❌ Файл не найден")
        return

    file_name = document.file_name if document else f"photo_{photo.file_id}.jpg"
    file_ext = get_file_extension(file_name).lower()

    if file_obj.file_size > MAX_FILE_SIZE or file_ext not in SUPPORTED_FORMATS:
        await message.reply_text("❌ Файл слишком большой или формат не поддерживается")
        return

    await message.reply_text("📥 Скачиваю и обрабатываю файл...")

    temp_file_path = None
    pdf_path = None

    try:
        file = await file_obj.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            await file.download_to_drive(tmp.name)
            temp_file_path = tmp.name

        if file_ext == '.pdf':
            pdf_path = await convert_pdf_to_grayscale(update, context, temp_file_path)
        elif is_office_document(file_ext):
            pdf_path = await convert_to_pdf(update, context, temp_file_path, file_ext, grayscale=True)
        elif is_image_file(file_ext):
            pdf_path = await convert_image_to_pdf(update, context, temp_file_path, grayscale=True)
        else:
            await message.reply_text("❌ Формат не поддерживается для конвертации")
            return

        with open(pdf_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)

        context.user_data.update({
            'pdf_path': pdf_path,
            'file_name': file_name,
            'page_count': page_count,
            'is_pdf': file_ext == '.pdf',
            'is_office': is_office_document(file_ext),
            'is_image': is_image_file(file_ext),
            'awaiting_custom_range': False,
            'print_mode': 'normal'
        })

        if page_count == 1:
            await message.reply_text("🖨️ Авто-печать 1 страницы (grayscale)...")
            success = print_file_postscript(pdf_path, printer_name=PRINTER_NAME)
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            context.user_data.clear()
            await message.reply_text("✅ Отправлено на печать" if success else "❌ Ошибка печати")
            return

        is_pdf_or_office = context.user_data['is_pdf'] or context.user_data['is_office']
        keyboard = _build_print_mode_keyboard(is_pdf_or_office)

        await message.reply_text(
            f"✅ Файл готов: {file_name}\nСтраниц: {page_count}\nВыберите режим печати:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Ошибка обработки файла от {user_id}: {e}", exc_info=True)
        await message.reply_text(f"❌ Ошибка обработки: {str(e)[:120]}\nПопробуйте другой файл.")
    
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except:
                pass


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "start_scan":
        keyboard = _build_scan_keyboard()
        await query.edit_message_text(
            "📸 Выберите тип сканирования (600dpi):\n"
            "• Один лист — на планшет\n"
            "• Несколько — через автоподатчик\n"
            "⚠️ 600dpi может занять время!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data.startswith("scan_"):
        await handle_scan_callback(update, context)
        return

    if 'pdf_path' not in context.user_data:
        await query.edit_message_text("❌ Сессия истекла или файл не найден")
        return

    pdf_path = context.user_data['pdf_path']
    page_count = context.user_data.get('page_count', 0)
    file_name = context.user_data.get('file_name', 'file')

    if data == "cancel":
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
        context.user_data.clear()
        await query.edit_message_text("❌ Операция отменена")
        return

    if data == "print_normal_only":
        await query.edit_message_text("🖨️ Печатаю односторонне...")
        success = print_file_postscript(pdf_path, printer_name=PRINTER_NAME)
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)
        context.user_data.clear()
        await query.edit_message_text("✅ Отправлено" if success else "❌ Ошибка печати")
        return

    if data in ["print_normal", "print_duplex"]:
        context.user_data['print_mode'] = 'normal' if data == "print_normal" else 'duplex'

        if page_count <= 1:
            await execute_print_with_range(context, query.edit_message_text)
            return

        keyboard = _build_page_range_keyboard(page_count)

        mode_text = "Обычная" if data == "print_normal" else "Двусторонняя"
        await query.edit_message_text(
            f"📄 {mode_text} печать\nФайл: {file_name}\nСтраниц: {page_count}\nВыберите диапазон:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "print_booklet":
        context.user_data['print_mode'] = 'booklet'
        if page_count < 2:
            keyboard = _build_print_mode_keyboard(True)
            await query.edit_message_text(
                f"❌ Для брошюры минимум 2 страницы\nФайл: {file_name}\nСтраниц: {page_count}\nРежим:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        num_signatures, sheets_per_sig, total_sheets, sheets_with_blanks = calculate_signature_config(
            page_count, DEFAULT_SHEETS_PER_SIGNATURE
        )
        info_text = (
            f"📖 Печать брошюрой\n"
            f"Файл: {file_name}\n"
            f"Страниц: {page_count}\n"
            f"Листов: {total_sheets}\n"
            f"Сигнатур: {num_signatures} по {sheets_per_sig}\n"
            f"Итого листов (с пустыми): {sheets_with_blanks}\n"
            f"🖨️ Готовлю и печатаю..."
        )
        await query.edit_message_text(info_text)

        try:
            booklet_files = create_booklet_for_short_edge(pdf_path, sheets_per_sig, page_count)
            if not booklet_files:
                raise Exception("Не удалось создать файлы брошюры")

            success = all(
                print_file_postscript(f, booklet=True, duplex=True, printer_name=PRINTER_NAME)
                for f in booklet_files
            )

            for f in booklet_files + [pdf_path]:
                if os.path.exists(f):
                    os.unlink(f)

            context.user_data.clear()
            await query.edit_message_text(
                f"✅ Брошюра отправлена на печать\n"
                f"Сигнатур: {num_signatures}\nЛистов: {sheets_with_blanks}"
                if success else "❌ Ошибка при печати брошюры"
            )
        except Exception as e:
            logger.error(f"Ошибка брошюры: {e}", exc_info=True)
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            context.user_data.clear()
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:120]}")
            return

    elif data == "print_all":
        await execute_print_with_range(context, query.edit_message_text)

    elif data == "print_custom":
        context.user_data['awaiting_custom_range'] = True
        await query.edit_message_text("📝 Введите диапазон страниц (пример: 1-3,5,7-9)\nИли /cancel")

    elif data == "back_to_menu":
        context.user_data['awaiting_custom_range'] = False

        is_pdf_or_office = context.user_data.get('is_pdf', False) or context.user_data.get('is_office', False)
        keyboard = _build_print_mode_keyboard(is_pdf_or_office)

        await query.edit_message_text(
            f"✅ Файл: {file_name}\nСтраниц: {page_count}\nВыберите режим:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def execute_print_with_range(context: ContextTypes.DEFAULT_TYPE, reply_func, page_range: str = None):
    """
    Выполняет печать с указанным диапазоном страниц.
    reply_func — вызываемая функция для отправки сообщения (query.edit_message_text или message.reply_text).
    """
    if 'pdf_path' not in context.user_data:
        await reply_func("❌ Файл не найден")
        return

    data = context.user_data
    pdf_path = data['pdf_path']
    print_mode = data.get('print_mode', 'normal')
    duplex = print_mode == 'duplex'

    msg = "🖨️ Печатаю двусторонне..." if duplex else "🖨️ Печатаю односторонне..."
    await reply_func(msg)

    success = print_file_postscript(
        pdf_path,
        duplex=duplex,
        page_range=page_range,
        printer_name=PRINTER_NAME
    )

    range_text = f" (страницы: {page_range})" if page_range else " (все страницы)"
    if os.path.exists(pdf_path):
        os.unlink(pdf_path)

    context.user_data.clear()
    await reply_func(f"✅ Отправлено{range_text}" if success else "❌ Ошибка печати")


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'awaiting_custom_range' not in context.user_data or not context.user_data['awaiting_custom_range']:
        return

    text = update.message.text.strip()
    if text.lower() == '/cancel':
        context.user_data['awaiting_custom_range'] = False
        page_count = context.user_data.get('page_count', 0)

        keyboard = _build_page_range_keyboard(page_count)

        await update.message.reply_text("❌ Ввод отменён\nВыберите страницы:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if not re.match(r'^(\d+(-\d+)?)(,\d+(-\d+)?)*$', text):
        await update.message.reply_text("❌ Неверный формат. Пример: 1-3,5,7-9\nИли /cancel")
        return

    await update.message.reply_text(f"🖨️ Печатаю указанные страницы: {text}")
    await execute_print_with_range(context, update.message.reply_text, text)


async def handle_scan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    allowed_users = context.bot_data.get('allowed_users', set())

    if not is_user_allowed(user_id, allowed_users):
        await query.edit_message_text("❌ Доступ запрещен")
        return

    data = query.data
    if data == "scan_cancel":
        keyboard = [[InlineKeyboardButton("📸 Сканировать", callback_data="start_scan")]]

        await query.edit_message_text("❌ Сканирование отменено", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await query.edit_message_text("🔄 Подготовка сканера...")

    try:
        scanned_files = []
        if data == "scan_single":
            await query.edit_message_text("📸 Сканирую один лист (планшет, 600dpi)...")
            scanned_files = [await scan_single_page()]
        elif data == "scan_multiple":
            await query.edit_message_text("📚 Сканирую с автоподатчика (600dpi)...")
            scanned_files = await scan_multiple_pages()

        if scanned_files:
            await query.edit_message_text(f"🔄 Объединяю {len(scanned_files)} стр. в PDF...")
            pdf_path = await convert_images_to_pdf(scanned_files)

            await query.edit_message_text(f"✅ Готово! Отправляю PDF ({len(scanned_files)} стр.)")

            with open(pdf_path, 'rb') as pdf_file:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=pdf_file,
                    filename=f"scan_{time.strftime('%Y%m%d_%H%M%S')}.pdf",
                    caption=f"Сканирование ({len(scanned_files)} стр., 600dpi Lineart)"
                )

            for f in scanned_files + [pdf_path]:
                if os.path.exists(f):
                    os.unlink(f)

            keyboard = _build_scan_keyboard()
            await query.edit_message_text(
                "📸 Готов к новому сканированию",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text("❌ Не удалось отсканировать ни одной страницы")

    except Exception as e:
        error_msg = str(e)
        if "timeout" in error_msg.lower():
            error_msg = "Таймаут сканирования. Проверьте сканер."
        elif "device busy" in error_msg.lower():
            error_msg = "Сканер занят. Подождите немного."
        elif "no documents" in error_msg.lower():
            error_msg = "Нет документов в автоподатчике."

        keyboard = _build_scan_keyboard()
        await query.edit_message_text(
            f"❌ Ошибка сканирования: {error_msg}\n\nПопробуйте снова:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Исключение в обработчике: {context.error}", exc_info=context.error)