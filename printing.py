# Файл: printing.py
# Этот файл содержит функции для печати и создания брошюр.

import os
import subprocess
import math
import logging
import re
import pypdf  # Импорт pypdf.
import tempfile  # Импорт tempfile.
import time  # Импорт time.

from utils import create_temp_copy  # Импорт из utils.

logger = logging.getLogger(__name__)  # Логгер.

def calculate_signature_config(page_count: int, default_sheets: int = 5) -> tuple:  # Функция рассчитывает конфигурацию для брошюры, возвращает кортеж (tuple - неизменяемый список).
    """Рассчитывает конфигурацию сигнатур для брошюры."""  # Docstring.
    total_sheets = math.ceil(page_count / 4)  # Вычисляем общее количество листов: ceil округляет вверх (импорт math).
    if page_count < 29:  # Если страниц меньше 29.
        sheets_per_signature = min(total_sheets, default_sheets)  # min - минимальное значение.
        num_signatures = 1  # Одна сигнатура.
        total_sheets_with_blanks = sheets_per_signature  # С blanks.
    else:  # Иначе.
        sheets_per_signature = default_sheets
        num_signatures = math.ceil(total_sheets / sheets_per_signature)
        total_sheets_with_blanks = sheets_per_signature * num_signatures
    return num_signatures, sheets_per_signature, total_sheets, total_sheets_with_blanks  # Возвращаем кортеж.

def create_booklet_for_short_edge(input_pdf: str, sheets_per_signature: int, total_pages_in_doc: int) -> list[str]:
    """Создаёт PDF-брошюру для two-sided-short-edge."""
    with tempfile.TemporaryDirectory(prefix="booklet_") as tmpdir:
        output_files = []
        try:
            reader = pypdf.PdfReader(input_pdf)
            num_pages = len(reader.pages)
            pages_per_sig = sheets_per_signature * 4

            # Генерируем конфигурации для всех сигнатур
            current_page = 0
            signature_configs = []
            while current_page < num_pages:
                end_page = min(current_page + pages_per_sig, num_pages)
                actual_pages = end_page - current_page
                empty_pages = pages_per_sig - actual_pages
                signature_configs.append({
                    'start': current_page,
                    'end': end_page,
                    'total_pages_needed': pages_per_sig,
                    'actual_pages': actual_pages,
                    'sheets': sheets_per_signature,
                    'empty_pages': empty_pages
                })
                current_page = end_page
            
            for sig_idx, config in enumerate(signature_configs):  # Цикл for с enumerate (индекс + значение).
                writer = pypdf.PdfWriter()  # Новый PdfWriter.
                pages = [reader.pages[i] for i in range(config['start'], config['end'])]  # Список страниц (list comprehension - генератор списка).
                for _ in range(config['empty_pages']):  # Цикл for для добавления пустых страниц (_ - игнорируемая переменная).
                    blank_page = pypdf.PageObject.create_blank_page(width=595, height=842)  # Создаем пустую страницу.
                    pages.append(blank_page)  # Добавляем.
                
                total_pages = config['total_pages_needed']  # Общее страниц.
                booklet_pages = []  # Список для брошюры.
                for i in range(total_pages // 2):  # Цикл for, // - целочисленное деление.
                    if i % 2 == 0:  # Если четный (% - остаток от деления).
                        right = i
                        left = total_pages - i - 1
                    else:
                        right = total_pages - i - 1
                        left = i
                    booklet_pages.append((pages[left], pages[right]))  # Добавляем пару страниц.
                
                for page_left, page_right in booklet_pages:  # Цикл по парам.
                    width = float(page_left.mediabox.width) if page_left else 595  # Получаем ширину, float - в float, if-else в одну строку.
                    height = float(page_left.mediabox.height) if page_left else 842  # Аналогично высота.
                    new_page = writer.add_blank_page(width=width * 2 + 40, height=height + 30)  # Добавляем новую страницу.
                    if page_left:  # Если левая страница существует.
                        new_page.merge_translated_page(page_left, tx=10, ty=15)  # Сливаем с переводом (merge_translated_page).
                    if page_right:
                        new_page.merge_translated_page(page_right, tx=width + 30, ty=15)  # Аналогично для правой.
                
                temp_path = os.path.join(tmpdir, f'booklet_{sig_idx}.pdf')  # Путь к временному PDF.
                with open(temp_path, "wb") as f:  # Открываем на запись.
                    writer.write(f)  # Пишем.
                output_files.append(create_temp_copy(temp_path, '.pdf'))  # Добавляем копию в список.
            return output_files  # Возвращаем список.
        except Exception as e:
            logger.error(f"Ошибка создания брошюры: {e}")
            return []  # Возвращаем пустой список при ошибке.

def print_file_postscript(file_path: str, booklet: bool = False, duplex: bool = False, page_range: str = None, printer_name: str = 'Xerox_WorkCentre_3220') -> bool:  # Функция печати.
    """Отправляет файл на печать через lp (CUPS)."""  # Docstring.
    try:
        start_time = time.time()  # Запоминаем текущее время для расчета длительности.
        cmd = ['lp', '-d', printer_name, '-o', 'PageSize=A4']  # Базовая команда lp.
        if booklet:  # Если брошюра.
            cmd.extend(['-o', 'sides=two-sided-short-edge', '-o', 'Duplex=DuplexTumble'])  # Добавляем опции.
            logger.info("Режим: Брошюра (two-sided-short-edge с Tumble)")
        elif duplex:  # Если дуплекс.
            cmd.extend(['-o', 'sides=two-sided-long-edge', '-o', 'Duplex=DuplexNoTumble'])
            logger.info("Режим: Двусторонняя (two-sided-long-edge без Tumble)")
        else:  # Односторонняя.
            cmd.extend(['-o', 'sides=one-sided', '-o', 'Duplex=None'])
            logger.info("Режим: Односторонняя (one-sided)")
        
        quality = '300dpi' if booklet else '600dpi'  # Тернарный оператор: качество в зависимости от booklet.
        cmd.extend(['-o', f'Quality={quality}'])  # Добавляем качество.
        logger.info(f"Качество: {quality}")
        
        cmd.extend([  # Добавляем общие опции.
            '-o', 'JCLEconomode=Off',
            '-o', 'InputSlot=Auto',
            '-o', 'MediaType=Plain',
            '-o', 'ColorModel=Gray',
            '-o', 'fit-to-page',
            '-o', 'document-format=application/pdf'
        ])
        
        if page_range:
            # Валидация page_range: допускаем только цифры, дефисы и запятые
            if not re.match(r'^[\d,\-]+$', page_range):
                logger.error(f"Невалидный page_range: {page_range}")
                return False
            cmd.extend(['-o', f'page-ranges={page_range}'])
        
        cmd.append(file_path)  # Добавляем путь к файлу в конец.
        logger.info(f"Команда печати: {' '.join(cmd)}")  # Логируем команду (' '.join - объединяет список в строку через пробел).
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # Запускаем.
        duration = time.time() - start_time  # Вычисляем длительность.
        
        if result.returncode == 0:  # Если успех.
            logger.info(f"Печать отправлена за {duration:.1f} сек")  # Логируем с форматированием (.1f - один знак после точки).
            return True
        else:
            logger.error(f"Ошибка печати: {result.stderr}")
            # Попытка упрощенной печати
            logger.info("Пробую упрощенную печать...")
            simple_cmd = ['lp', '-d', printer_name, '-o', 'PageSize=A4', '-o', 'fit-to-page', file_path]  # Упрощенная команда.
            simple_result = subprocess.run(simple_cmd, capture_output=True, text=True, timeout=60)
            return simple_result.returncode == 0  # Возвращаем True если успех.
    except subprocess.TimeoutExpired:
        logger.error("Таймаут печати")
        return False
    except Exception as e:
        logger.error(f"Критическая ошибка печати: {e}")
        return False