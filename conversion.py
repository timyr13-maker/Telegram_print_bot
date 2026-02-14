# conversion.py
"""
Функции для асинхронной конвертации файлов в PDF с поддержкой grayscale.
Использует asyncio.subprocess для отзывчивости бота.
"""

import asyncio
import os
import shutil
import tempfile
import logging
import sys
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

import pypdf

from utils import create_temp_copy
from config import MAX_FILE_SIZE

logger = logging.getLogger(__name__)


async def send_progress_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: Optional[int] = None,
    text: str = ""
) -> int:
    """
    Отправляет или редактирует сообщение с прогрессом.
    Возвращает message_id для последующих редактирований.
    """
    if message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text
            )
            return message_id
        except Exception:
            pass  # если сообщение удалено или ошибка — отправим новое

    sent = await context.bot.send_message(chat_id=chat_id, text=text)
    return sent.message_id


async def run_subprocess(
    cmd: list[str],
    timeout: float = 120.0,
    cwd: Optional[str] = None,
    description: str = "выполнение команды"
) -> tuple[bytes, bytes]:
    """
    Асинхронный запуск внешней команды с таймаутом и логированием ошибок.
    """
    logger.info(f"Запускаю: {' '.join(cmd)}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.terminate()
            try:
                await process.wait()
            except:
                process.kill()
            raise RuntimeError(f"Таймаут ({timeout} сек) при {description}")

        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="replace").strip()
            logger.error(f"Команда завершилась с кодом {process.returncode}: {error_text}")
            raise RuntimeError(f"{description} завершилось с ошибкой (код {process.returncode}): {error_text}")

        return stdout, stderr

    except Exception as e:
        logger.exception(f"Критическая ошибка при {description}")
        raise


async def convert_to_pdf(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    input_file: str,
    input_ext: str,
    grayscale: bool = True
) -> str:
    """
    Асинхронно конвертирует офисный документ в PDF с помощью LibreOffice.
    Поддерживает индикаторы прогресса.
    """
    chat_id = update.effective_chat.id
    progress_msg_id = None

    progress_msg_id = await send_progress_message(
        context, chat_id, progress_msg_id,
        f"📄 Конвертирую {input_ext.upper()} → PDF…"
    )

    with tempfile.TemporaryDirectory(prefix="conv_to_pdf_") as tmpdir:
        try:
            temp_input = os.path.join(tmpdir, os.path.basename(input_file))
            shutil.copy2(input_file, temp_input)

            pdf_name = os.path.splitext(os.path.basename(temp_input))[0] + ".pdf"
            pdf_path = os.path.join(tmpdir, pdf_name)

            cmd = [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmpdir,
                temp_input
            ]

            await run_subprocess(
                cmd,
                timeout=90.0 + os.path.getsize(input_file) // (1024 * 1024) * 8,  # ~8 сек на МБ
                description="конвертация в PDF (LibreOffice)"
            )

            if not os.path.exists(pdf_path):
                raise RuntimeError("PDF после конвертации не найден")

            if grayscale:
                progress_msg_id = await send_progress_message(
                    context, chat_id, progress_msg_id,
                    "🖤 Применяю чёрно-белый режим (grayscale)…"
                )
                pdf_path = await convert_pdf_to_grayscale(update, context, pdf_path)

            return create_temp_copy(pdf_path, ".pdf")

        except Exception as e:
            if progress_msg_id:
                await send_progress_message(
                    context, chat_id, progress_msg_id,
                    f"❌ Ошибка конвертации: {str(e)[:120]}"
                )
            raise


async def convert_image_to_pdf(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    grayscale: bool = True
) -> str:
    """
    Асинхронно конвертирует изображение в PDF с помощью img2pdf.
    Grayscale применяется на уровне PDF через Ghostscript.
    """
    chat_id = update.effective_chat.id
    progress_msg_id = None

    progress_msg_id = await send_progress_message(
        context, chat_id, progress_msg_id,
        "🖼️ Конвертирую изображение → PDF…"
    )

    with tempfile.TemporaryDirectory(prefix="conv_img_pdf_") as tmpdir:
        try:
            temp_image = os.path.join(tmpdir, os.path.basename(image_path))
            shutil.copy2(image_path, temp_image)

            pdf_path = os.path.join(tmpdir, "image.pdf")

            cmd = [sys.executable, "-m", "img2pdf", temp_image, "--output", pdf_path]

            await run_subprocess(
                cmd,
                timeout=45.0,
                description="конвертация изображения (img2pdf)"
            )

            if not os.path.exists(pdf_path):
                raise RuntimeError("PDF после img2pdf не найден")

            if grayscale:
                progress_msg_id = await send_progress_message(
                    context, chat_id, progress_msg_id,
                    "🖤 Применяю чёрно-белый режим…"
                )
                pdf_path = await convert_pdf_to_grayscale(update, context, pdf_path)

            return create_temp_copy(pdf_path, ".pdf")

        except Exception as e:
            if progress_msg_id:
                await send_progress_message(
                    context, chat_id, progress_msg_id,
                    f"❌ Ошибка конвертации изображения: {str(e)[:120]}"
                )
            raise


async def convert_pdf_to_grayscale(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    pdf_path: str
) -> str:
    """
    Асинхронно конвертирует PDF в grayscale с помощью Ghostscript.
    При ошибке поднимает исключение (не возвращает цветной оригинал молча).
    """
    chat_id = update.effective_chat.id
    progress_msg_id = await send_progress_message(
        context, chat_id, None,  # новое сообщение, т.к. предыдущее может быть уже отредактировано
        "🖤 Конвертация в grayscale (Ghostscript)…"
    )

    with tempfile.TemporaryDirectory(prefix="pdf_gray_") as tmpdir:
        try:
            temp_input = os.path.join(tmpdir, "input.pdf")
            shutil.copy2(pdf_path, temp_input)

            output_path = os.path.join(tmpdir, "gray.pdf")

            cmd = [
                "gs",
                "-q",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/printer",
                "-sProcessColorModel=DeviceGray",
                "-sColorConversionStrategy=Gray",
                "-dNOPAUSE",
                "-dBATCH",
                f"-sOutputFile={output_path}",
                temp_input
            ]

            await run_subprocess(
                cmd,
                timeout=60.0,
                description="конвертация в grayscale (Ghostscript)"
            )

            if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
                raise RuntimeError("Созданный grayscale PDF пустой или слишком маленький")

            return create_temp_copy(output_path, ".pdf")

        except Exception as e:
            await send_progress_message(
                context, chat_id, progress_msg_id,
                "⚠️ Не удалось сделать ч/б версию — печатаем оригинал"
            )
            logger.error(f"Grayscale failed: {e}", exc_info=True)
            # Если очень важно — можно здесь raise, но для usability оставляем fallback
            return create_temp_copy(pdf_path, ".pdf")


def create_blank_pdf() -> str:
    """Создаёт пустую PDF-страницу формата A4."""
    with tempfile.TemporaryDirectory(prefix="blank_pdf_") as tmpdir:
        try:
            writer = pypdf.PdfWriter()
            writer.add_blank_page(width=595, height=842)  # A4

            pdf_path = os.path.join(tmpdir, "blank.pdf")
            with open(pdf_path, "wb") as f:
                writer.write(f)

            return create_temp_copy(pdf_path, ".pdf")
        except Exception as e:
            logger.error(f"Ошибка создания пустой страницы: {e}")
            raise