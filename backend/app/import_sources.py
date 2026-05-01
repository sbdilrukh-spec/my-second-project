"""
Импорт источников из CSV и Excel файлов.
"""

import csv
import io
from typing import List, Dict, Any

# Маппинг допустимых названий столбцов к каноническим
COLUMN_MAP = {
    # Название / номер
    "название": "name", "name": "name", "источник": "name", "source": "name",
    "№": "name", "номер": "name", "number": "name", "n": "name",
    # Код вещества
    "код вещества": "substance_code", "код": "substance_code",
    "substance_code": "substance_code", "code": "substance_code",
    # Название вещества
    "название вещества": "substance_name", "вещество": "substance_name",
    "substance": "substance_name", "substance_name": "substance_name",
    # Высота
    "высота": "height", "h": "height", "h, м": "height", "height": "height",
    "высота трубы": "height", "высота, м": "height",
    "высота (h), м": "height", "высота (h)": "height",
    # Диаметр
    "диаметр": "diameter", "d": "diameter", "d, м": "diameter", "diameter": "diameter",
    "диаметр устья": "diameter",
    "диаметр (d), м": "diameter", "диаметр (d)": "diameter",
    # Скорость
    "скорость": "velocity", "w0": "velocity", "w0, м/с": "velocity", "velocity": "velocity",
    "скорость выхода": "velocity",
    "скорость (w0), м/с": "velocity", "скорость (w0)": "velocity",
    # Температура
    "температура": "temperature", "tг": "temperature", "tг, °c": "temperature",
    "temperature": "temperature", "температура газов": "temperature",
    "температура (tг), °c": "temperature", "температура (tг)": "temperature",
    # Выброс г/с
    "выброс г/с": "emission_gs", "m": "emission_gs", "m, г/с": "emission_gs",
    "emission_gs": "emission_gs", "г/с": "emission_gs", "выброс": "emission_gs",
    "выброс (m), г/с": "emission_gs", "выброс (m)": "emission_gs",
    # Выброс т/год
    "выброс т/год": "emission_ty", "m год": "emission_ty", "m, т/год": "emission_ty",
    "emission_ty": "emission_ty", "т/год": "emission_ty",
    "выброс, т/год": "emission_ty",
    # Координаты
    "широта": "lat", "lat": "lat", "latitude": "lat",
    "долгота": "lon", "lon": "lon", "longitude": "lon", "lng": "lon",
}

REQUIRED_FIELDS = {"name", "height", "diameter", "velocity", "temperature", "emission_gs"}


def _normalize_header(header: str) -> str:
    """Приводит заголовок к каноническому имени."""
    h = header.strip().lower().replace("°", "°")
    return COLUMN_MAP.get(h, h)


def parse_csv(content: str) -> List[Dict[str, Any]]:
    """Парсит CSV-текст и возвращает список источников."""
    # Определяем разделитель
    delimiter = ";"
    if content.count(",") > content.count(";"):
        delimiter = ","

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)

    if len(rows) < 2:
        return []

    headers = [_normalize_header(h) for h in rows[0]]
    sources = []

    for row_idx, row in enumerate(rows[1:], start=2):
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))

        source = {}
        errors = []

        for i, header in enumerate(headers):
            val = row[i].strip() if i < len(row) else ""

            if header in ("name",):
                source[header] = val or f"Источник {row_idx - 1}"
            elif header in ("substance_code", "substance_name"):
                source[header] = val or None
            elif header in ("height", "diameter", "velocity", "temperature",
                           "emission_gs", "emission_ty", "lat", "lon"):
                try:
                    source[header] = float(val.replace(",", ".")) if val else None
                except ValueError:
                    source[header] = None
                    errors.append(f"Строка {row_idx}, '{headers[i]}': нечисловое значение '{val}'")

        # Проверка обязательных полей
        for field in REQUIRED_FIELDS:
            if field not in source or source[field] is None:
                if field == "name":
                    source["name"] = f"Источник {row_idx - 1}"
                else:
                    errors.append(f"Строка {row_idx}: отсутствует обязательное поле '{field}'")

        source["_row"] = row_idx
        source["_errors"] = errors
        sources.append(source)

    return sources


def parse_excel(file_bytes: bytes) -> List[Dict[str, Any]]:
    """Парсит Excel (.xlsx) файл и возвращает список источников."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []

    headers = [_normalize_header(str(h or "")) for h in rows[0]]
    sources = []

    for row_idx, row in enumerate(rows[1:], start=2):
        source = {}
        errors = []

        for i, header in enumerate(headers):
            val = row[i] if i < len(row) else None

            if header in ("name",):
                source[header] = str(val) if val else f"Источник {row_idx - 1}"
            elif header in ("substance_code", "substance_name"):
                source[header] = str(val) if val else None
            elif header in ("height", "diameter", "velocity", "temperature",
                           "emission_gs", "emission_ty", "lat", "lon"):
                try:
                    source[header] = float(val) if val is not None else None
                except (ValueError, TypeError):
                    source[header] = None
                    errors.append(f"Строка {row_idx}, '{headers[i]}': нечисловое значение")

        for field in REQUIRED_FIELDS:
            if field not in source or source[field] is None:
                if field == "name":
                    source["name"] = f"Источник {row_idx - 1}"
                else:
                    errors.append(f"Строка {row_idx}: отсутствует обязательное поле '{field}'")

        source["_row"] = row_idx
        source["_errors"] = errors
        sources.append(source)

    wb.close()
    return sources


def generate_template_csv() -> str:
    """Генерирует CSV-шаблон для импорта (с BOM для Excel).

    Каждая строка — одно вещество от одного источника.
    Если у одной трубы несколько веществ — повторите строку с тем же
    "Названием" и параметрами трубы, поменяв только колонки вещества и выбросов.
    """
    header = "Название;Код вещества;Высота (H), м;Диаметр (D), м;Скорость (w0), м/с;Температура (Tг), °C;Выброс (M), г/с;Выброс, т/год;Широта;Долгота"
    examples = "\n".join([
        "Труба ТЭЦ-1;0301;45;1.2;12.0;180;8.5;268.06;41.2995;69.2401",
        "Труба ТЭЦ-1;0337;45;1.2;12.0;180;12.0;378.43;41.2995;69.2401",
        "Труба ТЭЦ-1;0330;45;1.2;12.0;180;3.5;110.4;41.2995;69.2401",
    ])
    return f"{header}\n{examples}\n"


def generate_template_xlsx() -> bytes:
    """Генерирует Excel-шаблон для импорта."""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Источники"

    headers = [
        "№", "Код вещества", "Высота (H), м", "Диаметр (D), м",
        "Скорость (w0), м/с", "Температура (Tг), °C",
        "Выброс (M), г/с", "Выброс, т/год",
    ]

    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.border = thin_border

    # Демонстрируем многовеществный формат: одна труба, три вещества
    examples = [
        ["Труба ТЭЦ-1", "0301", 45, 1.2, 12.0, 180, 8.5, 268.06],
        ["Труба ТЭЦ-1", "0337", 45, 1.2, 12.0, 180, 12.0, 378.43],
        ["Труба ТЭЦ-1", "0330", 45, 1.2, 12.0, 180, 3.5, 110.4],
    ]
    for row_offset, row_data in enumerate(examples):
        for col, val in enumerate(row_data, 1):
            cell = ws.cell(row=2 + row_offset, column=col, value=val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")

    # Подсказка под таблицей
    note = ws.cell(row=2 + len(examples) + 1, column=1,
                    value="Многовеществный формат: повторите строку с одним и тем же 'Названием' источника, меняя только код вещества и выбросы.")
    note.font = Font(italic=True, size=10, color="555555")
    ws.merge_cells(start_row=note.row, start_column=1, end_row=note.row, end_column=len(headers))

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
