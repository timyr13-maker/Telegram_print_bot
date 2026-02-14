# Файл: scanning.py
# Функции для сканирования с автоопределением сканера.
# Все subprocess-вызовы — асинхронные, чтобы не блокировать event loop бота.

import os
import subprocess
import asyncio
import tempfile
import logging
import re
import sys

from config import SCANNER_DEVICE, SCAN_OPTIONS
from utils import create_temp_copy

logger = logging.getLogger(__name__)


async def _run_scan_command(
    cmd: list[str],
    timeout: float = 120.0,
    description: str = "сканирование"
) -> tuple[bytes, bytes]:
    """
    Асинхронный запуск команды сканирования с таймаутом.
    Возвращает (stdout, stderr).
    """
    logger.info(f"Запускаю: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.terminate()
        try:
            await process.wait()
        except Exception:
            process.kill()
        raise RuntimeError(f"Таймаут ({timeout} сек) при {description}")

    return stdout, stderr, process.returncode


async def auto_detect_scanner() -> str:
    """Автоопределяет устройство сканера с помощью scanimage -L."""
    try:
        stdout, stderr, returncode = await _run_scan_command(
            ['scanimage', '-L'],
            timeout=30.0,
            description="автоопределение сканера"
        )
        if returncode != 0:
            logger.warning(f"Ошибка автоопределения сканера: {stderr.decode(errors='replace')}")
            return SCANNER_DEVICE

        output = stdout.decode(errors='replace')
        match = re.search(r"device\s+`([^']+)'", output)
        if match:
            detected_device = match.group(1)
            logger.info(f"Автоопределен сканер: {detected_device}")
            return detected_device
        else:
            logger.warning("Сканер не найден, использую дефолт")
            return SCANNER_DEVICE
    except Exception as e:
        logger.error(f"Ошибка автоопределения: {e}")
        return SCANNER_DEVICE


async def scan_single_page() -> str:
    """Сканирует один лист с планшета (PNM, 600dpi). Асинхронно."""
    scanner = await auto_detect_scanner()
    with tempfile.TemporaryDirectory(prefix="scan_single_") as tmpdir:
        try:
            logger.info("Начинаю сканирование одного листа (PNM, 600dpi)")
            scan_path = os.path.join(tmpdir, 'scan.pnm')
            cmd = [
                'scanimage', '-d', scanner,
                '--format', SCAN_OPTIONS['format'],
                '--resolution', SCAN_OPTIONS['resolution'],
                '--mode', SCAN_OPTIONS['mode'],
                '--source', 'Flatbed',
                '--progress',
                '-o', scan_path
            ]
            _stdout, stderr, returncode = await _run_scan_command(
                cmd, timeout=120.0, description="сканирование одного листа"
            )
            if returncode != 0:
                error_text = stderr.decode(errors='replace').strip()
                raise RuntimeError(f"Ошибка сканирования: {error_text or 'Неизвестная ошибка'}")

            if not os.path.exists(scan_path) or os.path.getsize(scan_path) == 0:
                raise RuntimeError("Сканированный файл пуст или не создан")

            logger.info(f"Сканирование успешно: {scan_path}")
            return create_temp_copy(scan_path, '.pnm')

        except RuntimeError as e:
            if "Таймаут" in str(e):
                raise RuntimeError("Таймаут сканирования (для 600dpi нужно больше времени)")
            logger.error(f"Ошибка сканирования: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка сканирования: {e}")
            raise


async def scan_multiple_pages() -> list[str]:
    """Сканирует несколько листов с автоподатчика (PNM, 600dpi). Асинхронно."""
    scanner = await auto_detect_scanner()
    with tempfile.TemporaryDirectory(prefix="scan_multi_") as tmpdir:
        scanned_files = []
        try:
            logger.info("Начинаю сканирование нескольких страниц (PNM, 600dpi)")
            base_scan_path = os.path.join(tmpdir, 'scan_%d.pnm')
            cmd = [
                'scanimage', '-d', scanner,
                '--format', SCAN_OPTIONS['format'],
                '--resolution', SCAN_OPTIONS['resolution'],
                '--mode', SCAN_OPTIONS['mode'],
                '--source', 'ADF',
                '--batch', base_scan_path,
                '--batch-start', '1',
                '--batch-increment', '1',
                '--batch-count', '50'
            ]
            _stdout, stderr, returncode = await _run_scan_command(
                cmd, timeout=600.0, description="многолистовое сканирование"
            )

            # Собираем отсканированные файлы
            page_num = 1
            while True:
                page_path = os.path.join(tmpdir, f'scan_{page_num}.pnm')
                if os.path.exists(page_path) and os.path.getsize(page_path) > 0:
                    scanned_files.append(create_temp_copy(page_path, '.pnm'))
                    logger.info(f"Страница {page_num} отсканирована")
                    page_num += 1
                else:
                    break

            # Фоллбэк: один файл без нумерации
            if not scanned_files:
                alt_page_path = os.path.join(tmpdir, 'scan.pnm')
                if os.path.exists(alt_page_path) and os.path.getsize(alt_page_path) > 0:
                    scanned_files.append(create_temp_copy(alt_page_path, '.pnm'))
                    logger.info("1 страница отсканирована (одиночный файл)")

            if returncode != 0 and not scanned_files:
                error_text = stderr.decode(errors='replace').strip()
                raise RuntimeError(f"Ошибка сканирования: {error_text or 'Неизвестная ошибка'}")

            if not scanned_files:
                raise RuntimeError("Не удалось отсканировать ни одной страницы")

            logger.info(f"Всего отсканировано {len(scanned_files)} страниц")
            return scanned_files

        except RuntimeError as e:
            if "Таймаут" in str(e) and scanned_files:
                logger.info(f"Возвращаю {len(scanned_files)} страниц (таймаут)")
                return scanned_files
            if "Таймаут" in str(e) and not scanned_files:
                raise RuntimeError("Таймаут сканирования. Проверьте сканер.")
            logger.error(f"Ошибка многолистового сканирования: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка многолистового сканирования: {e}")
            raise


async def convert_images_to_pdf(image_paths: list[str]) -> str:
    """Конвертирует список PNM-изображений в PDF с помощью img2pdf. Асинхронно."""
    with tempfile.TemporaryDirectory(prefix="conv_imgs_to_pdf_") as tmpdir:
        try:
            logger.info(f"Конвертирую {len(image_paths)} PNM в PDF")
            pdf_path = os.path.join(tmpdir, 'scanned.pdf')
            cmd = [sys.executable, '-m', 'img2pdf', '--output', pdf_path] + image_paths

            _stdout, stderr, returncode = await _run_scan_command(
                cmd, timeout=60.0, description="конвертация изображений в PDF"
            )

            if returncode != 0:
                error_text = stderr.decode(errors='replace').strip()
                raise RuntimeError(f"Ошибка img2pdf: {error_text or 'Неизвестная ошибка'}")

            if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
                raise RuntimeError("Созданный PDF пуст")

            return create_temp_copy(pdf_path, '.pdf')
        except Exception as e:
            logger.error(f"Ошибка конвертации изображений в PDF: {e}")
            raise