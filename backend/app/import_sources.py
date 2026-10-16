"""
Импорт источников из CSV и Excel файлов.
"""

import csv
import io
import re
from typing import List, Dict, Any, Iterable, Optional

# Маппинг допустимых названий столбцов к каноническим
COLUMN_MAP = {
    # Название
    "название": "name", "name": "name", "источник": "name", "source": "name",
    "наименование": "name", "наименование источника": "name",
    # Номер источника — тот, что пользователь сам присвоил (0001, 6001, ...)
    "№": "number", "номер": "number", "number": "number", "n": "number",
    "№ источника": "number", "номер источника": "number", "н ист.": "number",
    "н ист": "number", "№ ист.": "number", "№ ист": "number",
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
    # Координаты (десятичные градусы или градусы-минуты-секунды)
    "широта": "lat", "lat": "lat", "latitude": "lat", "широта (n)": "lat",
    "широта, с.ш.": "lat", "с.ш.": "lat",
    "долгота": "lon", "lon": "lon", "longitude": "lon", "lng": "lon",
    "долгота (e)": "lon", "долгота, в.д.": "lon", "в.д.": "lon",
}

REQUIRED_FIELDS = ("height", "diameter", "velocity", "temperature", "emission_gs")

NUMERIC_FIELDS = (
    "height", "diameter", "velocity", "temperature",
    "emission_gs", "emission_ty",
)
COORD_FIELDS = ("lat", "lon")
# Параметры трубы: в «карточном» шаблоне они объединены (merge) по строкам
# одного источника, поэтому пустые ячейки протягиваются из строки выше —
# но только в пределах того же источника.
INHERITABLE_FIELDS = ("height", "diameter", "velocity", "temperature", "lat", "lon")


def _normalize_header(header: str) -> str:
    """Приводит заголовок к каноническому имени."""
    h = " ".join(str(header).strip().lower().split())
    return COLUMN_MAP.get(h, h)


def _to_float(val) -> Optional[float]:
    """Число из ячейки: поддерживает запятую и неразрывные пробелы."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = str(val).strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    return float(cleaned)


_DMS_SPLIT = re.compile(r"[^\d.]+")


def parse_coordinate(val) -> Optional[float]:
    """
    Координата в десятичных градусах из любой распространённой записи:
      40.0839 · 40,0839 · 40°05'02" · 40°05'02,5"N · 40 05 02 · 40°05.03' · 40:05:02
    Южное/западное полушарие (S, W, Ю, З или минус) — отрицательное значение.
    Бросает ValueError, если разобрать не удалось.
    """
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().upper().replace("\xa0", " ")
    if not s:
        return None
    negative = s.startswith("-") or any(ch in s for ch in ("S", "W", "Ю", "З"))
    # Десятичная запятая внутри числа → точка (40,0839 / 02,5")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    parts = [p for p in _DMS_SPLIT.split(s) if p]
    if not parts or len(parts) > 3:
        raise ValueError(val)
    nums = [float(p) for p in parts]
    minutes = nums[1] if len(nums) > 1 else 0.0
    seconds = nums[2] if len(nums) > 2 else 0.0
    if minutes >= 60 or seconds >= 60:
        raise ValueError(val)
    result = nums[0] + minutes / 60.0 + seconds / 3600.0
    return -result if negative else result


def _cell_text(val) -> Optional[str]:
    """Текст ячейки; целые числа из Excel без «.0» (301.0 → "301")."""
    if val is None or val == "":
        return None
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    text = str(val).strip()
    return text or None


def _process_rows(headers: List[str], rows: Iterable) -> List[Dict[str, Any]]:
    """
    Общая обработка строк CSV/Excel.

    Одна строка = одно вещество одного источника. Источник опознаётся по
    «№» и/или «Названию»; строка без них относится к источнику выше
    (объединённые ячейки Excel), и её пустые параметры трубы наследуются.
    Строка ДРУГОГО источника ничего не наследует — иначе источник без
    координат молча получил бы координаты соседа.
    """
    sources = []
    last: Dict[str, Any] = {}   # параметры трубы текущего источника
    last_key = None             # (номер, название) текущего источника

    for row_idx, row in enumerate(rows, start=2):
        row = list(row) + [None] * (len(headers) - len(row))
        source: Dict[str, Any] = {}
        errors = []
        any_numeric = False

        for i, header in enumerate(headers):
            val = row[i]
            if isinstance(val, str):
                val = val.strip()
            if header in ("name", "number", "substance_code", "substance_name"):
                source[header] = _cell_text(val)
            elif header in NUMERIC_FIELDS:
                try:
                    source[header] = _to_float(val)
                    if source[header] is not None:
                        any_numeric = True
                except (ValueError, TypeError):
                    source[header] = None
                    errors.append(f"Строка {row_idx}, «{header}»: нечисловое значение «{val}»")
            elif header in COORD_FIELDS:
                try:
                    source[header] = parse_coordinate(val)
                except (ValueError, TypeError):
                    source[header] = None
                    errors.append(
                        f"Строка {row_idx}: не удалось разобрать координату «{val}» "
                        f"(пример: 40°05'02\" или 40.0839)"
                    )

        has_emission = (source.get("emission_gs") is not None
                        or source.get("emission_ty") is not None)
        # Пустая/служебная строка (хвост, «Итого», комментарий)
        if not any_numeric and not has_emission:
            continue

        own_key = (source.get("number"), source.get("name"))
        same_source = own_key == (None, None) or own_key == last_key
        if own_key == (None, None) and last_key:
            source["number"], source["name"] = last_key
        if same_source:
            for f in INHERITABLE_FIELDS:
                if source.get(f) is None and last.get(f) is not None:
                    source[f] = last[f]
        else:
            last = {}
        last_key = (source.get("number"), source.get("name"))
        for f in INHERITABLE_FIELDS:
            if source.get(f) is not None:
                last[f] = source[f]

        if not source.get("name"):
            source["name"] = (f"Источник {source['number']}" if source.get("number")
                              else f"Источник {row_idx - 1}")

        for field in REQUIRED_FIELDS:
            if source.get(field) is None:
                errors.append(f"Строка {row_idx}: отсутствует обязательное поле '{field}'")

        source["_row"] = row_idx
        source["_errors"] = errors
        sources.append(source)

    return sources


def parse_csv(content: str) -> List[Dict[str, Any]]:
    """Парсит CSV-текст и возвращает список строк-выбросов."""
    delimiter = ";"
    if content.count(",") > content.count(";"):
        delimiter = ","
    rows = list(csv.reader(io.StringIO(content), delimiter=delimiter))
    if len(rows) < 2:
        return []
    headers = [_normalize_header(h) for h in rows[0]]
    return _process_rows(headers, rows[1:])


def parse_excel(file_bytes: bytes) -> Dict[str, Any]:
    """
    Парсит Excel (.xlsx). Понимает два вида:
      • «2-бўлим» — таблица «Ифлослантирувчи моддаларни чиқарилмаларининг
        манбалари» из ПЗВОС (колонки A–T по позициям, шапка в несколько строк);
      • плоскую таблицу с однострочной шапкой (старый шаблон).
    Возвращает {"rows": [...], "origin": {"lat", "lon"} | None}.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if len(rows) < 2:
        return {"rows": [], "origin": None}

    section2 = _find_section2_layout(rows)
    if section2 is not None:
        return _parse_section2(rows, section2)

    headers = [_normalize_header(str(h or "")) for h in rows[0]]
    return {"rows": _process_rows(headers, rows[1:]), "origin": None}


# ---------------------------------------------------------------------------
# Формат «2-бўлим» (ПЗВОС): Ифлослантирувчи моддаларни чиқарилмаларининг манбалари
# ---------------------------------------------------------------------------
# Колонки по позициям (как в отчётах): A цех · B источник выделения ·
# C источник выброса · D часы/год · E № на карте-схеме · F H · G D · H V ·
# I w0 · J T · K X1 · L Y1 · M X2 · N Y2 · O ширина · P вещество · Q г/с ·
# R мг/м³ · S т/год · T удельный выброс. Справа — дополнительные колонки
# шаблона: U код вещества · V широта · W долгота (необязательные).
S2_COLS = {
    "shop": 0, "release": 1, "outlet": 2, "hours": 3, "number": 4,
    "height": 5, "diameter": 6, "volume": 7, "velocity": 8, "temperature": 9,
    "x1": 10, "y1": 11, "x2": 12, "y2": 13, "width": 14,
    "substance_name": 15, "emission_gs": 16, "emission_ty": 18,
    "substance_code": 20, "lat": 21, "lon": 22,
}

# Узбекские/сокращённые названия веществ из отчётов → коды справочника
# (коды «Радуги», которые есть во встроенном справочнике).
SUBSTANCE_ALIASES = {
    "углерод оксиди": "38", "углерод (ii) оксиди": "38", "ис гази": "38",
    "азот оксидлари": "34", "азот оксиди": "34", "азот диоксиди": "154",
    "олтингугурт оксиди": "106", "олтингугурт оксидлари": "106",
    "олтингугурт диоксиди": "201", "олтингугурт (iv) оксиди": "201",
    "хлор": "143", "водород хлорид": "120", "хлорли водород": "120",
    "водород сульфид": "204", "водород сульфиди": "204",
    "углеводородлар": "118", "чегараланган углеводородлар": "118",
    "бензин буғлари": "112", "бензин буғи": "112",
    "қурум": "57", "курум": "57", "сажа": "57",
    "марганец оксиди": "123", "марганец ва унинг бирикмалари": "123",
    "темир оксиди": "86", "темир (iii) оксиди": "86",
    "ноорганик чанг": "114", "анорганик чанг": "114",
    "цемент чанги": "55", "клинкер чанги": "115к", "оҳак чанги": "902и",
    "охак чанги": "902и", "оҳактош чанги": "902", "гипс чанги": "777",
    "ёғоч чанги": "113", "абразив чанг": "102", "абразив чанги": "102",
    "металл чанги": "101", "кўмир чанги": "128", "комир чанги": "128",
    "ун чанги": "129", "дон чанги": "100", "пахта чанги": "712",
    "кул чанги": "125", "руда чанги": "116", "формальдегид": "150",
    "метан": "205", "аммиак": "04", "метанол": "351", "свинец": "315",
    "қўрғошин": "315", "фторли водород": "119",
}


def _norm_name(name: str) -> str:
    return " ".join(str(name).lower().replace("ё", "е").split()) if name else ""


_ALIASES_NORM = {_norm_name(k): v for k, v in SUBSTANCE_ALIASES.items()}


def _cell_str(v) -> str:
    return " ".join(str(v).split()).lower() if v is not None else ""


def _find_section2_layout(rows) -> Optional[Dict[str, int]]:
    """
    Ищет шапку «2-бўлим»: строку с подписями Х1/У1 (кириллица или латиница)
    и под ней строку-нумерацию колонок 1, 2, 3, ... Возвращает индекс первой
    строки данных и, если есть, координаты начала карты-схемы.
    """
    xy_row = None
    for i, row in enumerate(rows[:20]):
        cells = {_cell_str(c) for c in row}
        if ({"х1", "x1"} & cells) and ({"у1", "y1"} & cells):
            xy_row = i
            break
    if xy_row is None:
        return None
    data_start = xy_row + 1
    # Строка нумерации колонок «1 2 3 … 20» — данные начинаются после неё
    for i in range(xy_row + 1, min(xy_row + 4, len(rows))):
        row = rows[i]
        if len(row) > 2 and _cell_str(row[0]) == "1" and _cell_str(row[1]) == "2":
            data_start = i + 1
            break
    return {"data_start": data_start}


def _find_origin(rows) -> Optional[Dict[str, float]]:
    """
    Начало координат карты-схемы (X=0, Y=0) — строка шаблона, где после
    подписи «Начало координат» стоят широта и долгота (десятичные или Г-М-С).
    """
    for row in rows[:20]:
        for j, c in enumerate(row):
            if "начало координат" in _cell_str(c) or "координаталар боши" in _cell_str(c):
                vals = []
                for v in row[j + 1:]:
                    if v is None or str(v).strip() == "":
                        continue
                    try:
                        vals.append(parse_coordinate(v))
                    except (ValueError, TypeError):
                        continue
                    if len(vals) == 2:
                        break
                if len(vals) == 2 and vals[0] is not None and vals[1] is not None:
                    return {"lat": vals[0], "lon": vals[1]}
    return None


def _num_or_none(v) -> Optional[float]:
    """Число из ячейки; прочерк «-» и пустота → None."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip() in ("", "-", "—", "–"):
        return None
    return _to_float(v)


def _parse_section2(rows, layout) -> Dict[str, Any]:
    origin = _find_origin(rows)
    out = []
    cur: Dict[str, Any] = {}   # параметры текущего источника

    def cell(row, key):
        i = S2_COLS[key]
        return row[i] if i < len(row) else None

    for row_idx, row in enumerate(rows[layout["data_start"]:], start=layout["data_start"] + 1):
        row = list(row)
        first = _cell_str(cell(row, "shop"))
        if first.startswith("жами") or first.startswith("итого") or first.startswith("всего"):
            continue
        sub_name = cell(row, "substance_name")
        sub_name = str(sub_name).strip() if sub_name is not None else ""
        errors = []

        def num(key):
            try:
                return _num_or_none(cell(row, key))
            except (ValueError, TypeError):
                errors.append(f"Строка {row_idx}: нечисловое значение «{cell(row, key)}»")
                return None

        gs, ty = num("emission_gs"), num("emission_ty")
        number = _cell_text(cell(row, "number"))
        if number:
            # Новый источник: собираем параметры трубы
            name = (_cell_text(cell(row, "release")) or _cell_text(cell(row, "outlet"))
                    or f"Источник {number}")
            try:
                lat = parse_coordinate(cell(row, "lat"))
                lon = parse_coordinate(cell(row, "lon"))
            except (ValueError, TypeError):
                lat = lon = None
                errors.append(f"Строка {row_idx}: не удалось разобрать широту/долготу")
            cur = {
                "number": number, "name": name,
                "height": num("height"), "diameter": num("diameter"),
                "velocity": num("velocity"), "temperature": num("temperature"),
                "volume": num("volume"),
                "x1": num("x1"), "y1": num("y1"), "x2": num("x2"), "y2": num("y2"),
                "width": num("width"), "lat": lat, "lon": lon,
            }
        if not cur or (not sub_name and gs is None and ty is None):
            continue

        src = dict(cur)
        # Скорость не указана, но есть объём V — w0 = 4V / (π·D²)
        if not src.get("velocity") and src.get("volume") and src.get("diameter"):
            src["velocity"] = 4.0 * src["volume"] / (3.141592653589793 * src["diameter"] ** 2)
        code = _cell_text(cell(row, "substance_code"))
        if not code and sub_name:
            code = _ALIASES_NORM.get(_norm_name(sub_name))
        src.update({
            "substance_code": code, "substance_name": sub_name or None,
            "emission_gs": gs, "emission_ty": ty,
        })
        _apply_geometry(src, origin)
        for field in ("height", "diameter", "velocity", "temperature"):
            if src.get(field) is None:
                errors.append(f"Строка {row_idx}: не заполнено поле «{field}» у источника {src['number']}")
        if gs is None and ty is None:
            errors.append(f"Строка {row_idx}: нет выброса (г/с или т/год)")
        src["_row"] = row_idx
        src["_errors"] = errors
        out.append(src)

    return {"rows": out, "origin": origin}


def _apply_geometry(src: Dict[str, Any], origin: Optional[Dict[str, float]]) -> None:
    """
    Координаты карты-схемы → положение источника.
    Точечный: (X1, Y1). Площадной/линейный (заданы X2, Y2): центр — середина
    отрезка X1Y1–X2Y2, длина — его длина, ширина — колонка «Кенглик», угол —
    направление отрезка от оси X (на восток) против часовой стрелки, как
    у площадного источника в программе.
    Если задана широта/долгота источника — она главнее X/Y. Если X/Y есть,
    а начала координат нет — отдаём метры (x_m, y_m), фронт поставит их
    от центра города.
    """
    import math
    x1, y1, x2, y2 = src.pop("x1"), src.pop("y1"), src.pop("x2"), src.pop("y2")
    width = src.pop("width")
    src.pop("volume", None)
    if x1 is None or y1 is None:
        return
    cx, cy = x1, y1
    if x2 is not None and y2 is not None and (x2, y2) != (x1, y1):
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        src["type"] = "area"
        src["area_length"] = round(math.hypot(x2 - x1, y2 - y1), 2)
        src["area_width"] = width if width and width > 0 else 1.0
        src["area_angle"] = round(math.degrees(math.atan2(y2 - y1, x2 - x1)), 2)
    src["x_m"], src["y_m"] = cx, cy
    if src.get("lat") is None and origin:
        src["lat"] = origin["lat"] + cy / 111_000.0
        src["lon"] = origin["lon"] + cx / (111_000.0 * math.cos(math.radians(origin["lat"])))


def generate_template_xlsx() -> bytes:
    """
    Шаблон импорта в виде таблицы «2-бўлим» ПЗВОС: те же колонки A–T,
    что в отчёте (можно вставлять готовую таблицу), плюс справа код
    вещества и широта/долгота источника. Над шапкой — строка «Начало
    координат», чтобы X/Y карты-схемы ставились на карту по местам.
    """
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "2-бўлим"

    thin = Side(style="thin", color="94A3B8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    head_font = Font(bold=True, size=9)
    head_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    extra_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid")

    ws["A1"] = "2-Бўлим"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = "Ифлослантирувчи моддаларни чиқарилмаларининг манбалари"
    ws["A2"].font = Font(bold=True, size=11)

    # Строка начала координат карты-схемы (X=0, Y=0)
    ws["A3"] = "Начало координат карты-схемы (X=0, Y=0):"
    ws["A3"].font = Font(bold=True, size=10, color="B91C1C")
    ws["E3"] = "широта"
    ws["F3"] = "40°05'02\""
    ws["G3"] = "долгота"
    ws["H3"] = "65°22'45\""
    for ref in ("F3", "H3"):
        ws[ref].fill = extra_fill
        ws[ref].border = border
        ws[ref].font = Font(bold=True, size=10)
    ws.merge_cells("A3:D3")

    # Шапка (строки 5–7) и нумерация колонок (строка 8)
    top = {
        "A": "Ишлаб чиқариш цехи ва бўлинмасининг номи",
        "B": "Ажралма манбасининг номи",
        "C": "Чиқарилма манбасининг номи",
        "D": "Чиқарилма манбасининг ишлаш вақти соат/йил",
        "E": "Харитадаги манбаларнинг рақамланиши",
        "F": "Чиқарилма манбаларининг баландлиги, м.",
        "G": "Қувур диаметри, м.",
        "H": "Газ-ҳаво аралашмасининг кўрсаткичлари",
        "K": "Харита-схемасидаги чиқарилма манбасининг координаталари, м.",
        "P": "Ифлослантирувчи моддаларнинг номи",
        "Q": "Ифлослантирувчи моддаларнинг чиқарилмалари",
        "T": "Бирлик маҳсулотга тўғри келадиган солиштирма чиқарилма",
        "U": "Код вещества (необяз.)",
        "V": "Широта источника (необяз.)",
        "W": "Долгота источника (необяз.)",
    }
    for col, text in top.items():
        ws[f"{col}5"] = text
    mid = {"H": "Ҳажми, м3/с", "I": "Тезлик, м/с", "J": "Температура, °С",
           "K": "Нуқтали, чизиқлининг бир томони", "M": "Иккинчи томон охирги нуқтаси",
           "O": "Кенглик, м"}
    for col, text in mid.items():
        ws[f"{col}6"] = text
    low = {"K": "Х1", "L": "У1", "M": "Х2", "N": "У2", "Q": "г/с", "R": "мг/м3", "S": "т/г"}
    for col, text in low.items():
        ws[f"{col}7"] = text
    for merge in ("A5:A7", "B5:B7", "C5:C7", "D5:D7", "E5:E7", "F5:F7", "G5:G7",
                  "H5:J5", "H6:H7", "I6:I7", "J6:J7", "K5:O5", "K6:L6", "M6:N6",
                  "O6:O7", "P5:P7", "Q5:S6", "T5:T7", "U5:U7", "V5:V7", "W5:W7"):
        ws.merge_cells(merge)
    n_cols = 23
    for c in range(1, n_cols + 1):
        ws.cell(row=8, column=c, value=c if c <= 20 else None)
        for r in range(5, 9):
            cell = ws.cell(row=r, column=c)
            cell.font = head_font
            cell.alignment = center
            cell.border = border
            cell.fill = extra_fill if c > 20 else head_fill

    # Пример: труба с тремя веществами, неорганизованный источник с площадкой
    demo = [
        ["Ишлаб чиқариш цехи", "Қозонхона", "Ташкиллаштирилган", 2496, "0001", 12, 0.5,
         None, 5.2, 120, 150, 210, "-", "-", "-", "Углерод оксиди", 0.0236, None, 0.2119, "-",
         None, None, None],
        [None, None, None, None, None, None, None, None, None, None, None, None, None, None,
         None, "Азот оксидлари", 0.0104, None, 0.0933, "-", None, None, None],
        [None, None, None, None, None, None, None, None, None, None, None, None, None, None,
         None, "Олтингугурт оксиди", 0.0015, None, 0.0132, "-", None, None, None],
        [None, "Омбор", "Ташкиллаштирилмаган", 1872, "6001", 2, 0.5, None, 0.5, 28.5,
         300, 100, 360, 100, 20, "Ноорганик чанг", 0.044, None, 0.29, "-", "114", None, None],
    ]
    for i, values in enumerate(demo):
        r = 9 + i
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.border = border
            cell.alignment = center
            cell.font = Font(size=10)
            if c > 20:
                cell.fill = extra_fill
    end = 9 + len(demo)
    ws.cell(row=end, column=1, value="Жами:").font = Font(bold=True, size=10)

    note = ws.cell(row=end + 2, column=1, value=(
        "Как заполнять: одна строка — одно вещество. Новый источник начинается со строки, "
        "где заполнен № (колонка 5); строки ниже без № — другие вещества того же источника. "
        "Координаты X1/У1 — метры от начала карты-схемы (строка 3 вверху, широта/долгота "
        "в градусах-минутах-секундах или десятичные). Для площадного/линейного источника "
        "заполните Х2/У2 (другой конец) и ширину. Вместо X/Y можно указать широту и долготу "
        "самого источника (колонки V, W). Код вещества (колонка U) нужен, если название "
        "не находится в справочнике."
    ))
    note.font = Font(italic=True, size=9, color="475569")
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=end + 2, start_column=1, end_row=end + 2, end_column=n_cols)
    ws.row_dimensions[end + 2].height = 54

    widths = [18, 18, 16, 10, 9, 9, 8, 8, 8, 10, 8, 8, 8, 8, 8, 22, 10, 8, 10, 10, 10, 12, 12]
    for c, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = w
    ws.row_dimensions[5].height = 60
    ws.row_dimensions[6].height = 36
    ws.freeze_panes = "A9"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
