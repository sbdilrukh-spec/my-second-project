"""
Карты рассеивания в Excel: на каждое вещество — лист с сеткой ОНД
(X по столбцам, Y по строкам, метры от левого-нижнего угла), в ячейках
концентрация в долях ПДК, заливка по той же шкале, что PNG «Сетка ОНД».
Заливка — обычная (не условное форматирование), чтобы цвета не терялись
при переносе таблицы в CorelDRAW.
"""

import io
import re

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .ond86 import source_number
from .raduga_docx import _GridXY, _Obj, _f, _sub_meta

# Шкала как в pdf_export._render_grid_map: доля от максимума поля
LEVELS = [
    (0.7, "FFCC66", "70–100 % от Cmax"),
    (0.3, "FFFF99", "30–70 % от Cmax"),
    (0.05, "FFFFDD", "5–30 % от Cmax"),
]
MAX_FILL = "FF9999"

THIN = Side(style="thin", color="A0A0A0")
SRC_SIDE = Side(style="medium", color="1D4ED8")
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
SRC_BORDER = Border(left=SRC_SIDE, right=SRC_SIDE, top=SRC_SIDE, bottom=SRC_SIDE)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
AXIS_FILL = PatternFill(start_color="FDE047", end_color="FDE047", fill_type="solid")


def _fill(hex_color):
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _num_format(v: float) -> str:
    # Как подписи на карте: 12.3 / 1.23 / 0.0123
    if v >= 10:
        return "0.0"
    if v >= 1:
        return "0.00"
    return "0.0000"


def _sheet_title(code, name, used):
    base = re.sub(r"[\[\]\*\?/\\:]", " ", f"{code} {name}").strip()[:28] or "Вещество"
    title, k = base, 2
    while title in used:
        title = f"{base[:25]} ({k})"
        k += 1
    used.add(title)
    return title


def _mode_text(mode):
    return "действующее предприятие, сф' по ОНД-86 п.7" if mode == "existing" else "новый объект, c + сф"


def generate_excel_maps(request_data: dict, result_data: dict) -> bytes:
    sources = request_data.get("sources") or []
    step = _f((request_data.get("grid") or {}).get("step"), 0)
    obj = (request_data.get("enterprise") or {}).get("name") or "—"
    subs = [s for s in (result_data.get("by_substance") or []) if s.get("points")]
    if not subs:
        raise ValueError("Нет результатов расчёта — сначала нажмите «Рассчитать»")

    gxy = _GridXY(subs[0]["points"], step)
    numbers = [source_number(_Obj(s), i) for i, s in enumerate(sources)]
    # Узел сетки каждого источника — для выделения рамкой
    src_nodes = {}
    for s, num in zip(sources, numbers):
        if s.get("lat") is None or s.get("lon") is None:
            continue
        src_nodes.setdefault(gxy.node(s["lat"], s["lon"]), []).append(str(num))

    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = "Сводка"
    used = {"Сводка"}

    summary_rows = []
    for sub in subs:
        code, name = _sub_meta(sub)
        pdk = _f(sub.get("pdk"), 0.5) or 0.5
        cells = {}
        for p in sub["points"]:
            cells[gxy.node(p["lat"], p["lon"])] = _f(p.get("c")) / pdk
        xs = sorted({k[0] for k in cells})
        ys = sorted({k[1] for k in cells}, reverse=True)
        qmax = max(cells.values()) if cells else 0.0
        max_node = max(cells, key=cells.get) if cells else (0, 0)

        ws = wb.create_sheet(_sheet_title(code, name, used))
        ws["A1"] = f"Карта рассеивания: {name} (код {code})"
        ws["A1"].font = Font(bold=True, size=12)
        info = f"Объект: {obj}.  ПДК м.р. {pdk:g} мг/м³.  Cmax = {qmax:.4g} ПДК в точке X={max_node[0]}, Y={max_node[1]} м."
        bg = sub.get("background")
        if bg:
            info += f"  С учётом фона {bg:g} мг/м³ ({_mode_text(sub.get('background_mode'))})."
        ws["A2"] = info
        ws["A2"].font = Font(size=10)

        # Легенда в строке 3
        col = 1
        ws.cell(row=3, column=col, value="Легенда:").font = Font(bold=True, size=9)
        col += 1
        for frac, color, label in [(None, MAX_FILL, "максимум")] + LEVELS:
            c = ws.cell(row=3, column=col)
            c.fill = _fill(color)
            c.border = CELL_BORDER
            txt = label if frac is None else f"{label} (> {qmax * frac:.3g} ПДК)"
            ws.cell(row=3, column=col + 1, value=txt).font = Font(size=9)
            col += 4
        c = ws.cell(row=3, column=col)
        c.border = SRC_BORDER
        ws.cell(row=3, column=col + 1, value="ячейка с источником").font = Font(size=9)

        # Сетка: строка 5 — X, столбец A — Y
        top = 5
        corner = ws.cell(row=top, column=1, value="Y \\ X, м")
        corner.font = Font(bold=True, size=8)
        corner.alignment = CENTER
        for j, x in enumerate(xs, 2):
            c = ws.cell(row=top, column=j, value=x)
            c.fill, c.font, c.alignment, c.border = AXIS_FILL, Font(bold=True, size=8), CENTER, CELL_BORDER
        for i, y in enumerate(ys, top + 1):
            c = ws.cell(row=i, column=1, value=y)
            c.fill, c.font, c.alignment, c.border = AXIS_FILL, Font(bold=True, size=8), CENTER, CELL_BORDER
            for j, x in enumerate(xs, 2):
                v = cells.get((x, y), 0.0)
                c = ws.cell(row=i, column=j, value=round(v, 6))
                c.number_format = _num_format(v)
                c.alignment = CENTER
                ratio = v / qmax if qmax > 0 else 0.0
                is_max = (x, y) == max_node and v > 0
                c.font = Font(size=8, bold=is_max)
                if is_max:
                    c.fill = _fill(MAX_FILL)
                else:
                    for frac, color, _ in LEVELS:
                        if ratio > frac:
                            c.fill = _fill(color)
                            break
                c.border = SRC_BORDER if (x, y) in src_nodes else CELL_BORDER

        # Квадратные ячейки: ширина 9 символов ≈ 68 px ≈ высота 51 pt
        ws.column_dimensions["A"].width = 9
        for j in range(2, len(xs) + 2):
            ws.column_dimensions[get_column_letter(j)].width = 9
        for i in range(top + 1, top + 1 + len(ys)):
            ws.row_dimensions[i].height = 51
        ws.freeze_panes = ws.cell(row=top + 1, column=2)
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1
        ws.sheet_properties.pageSetUpPr.fitToPage = True

        summary_rows.append((code, name, pdk, qmax, max_node, bg, sub.get("exceeds_pdk")))

    # --- Сводка ---
    summary["A1"] = f"Карты рассеивания — {obj}"
    summary["A1"].font = Font(bold=True, size=12)
    summary["A2"] = ("Значения в ячейках листов — концентрация в долях ПДК; X, Y — метры "
                     "от левого-нижнего угла сетки (как в таблицах «Радуги»).")
    summary["A2"].font = Font(size=9, italic=True)
    head = ["Код", "Вещество", "ПДК м.р., мг/м³", "Cmax, доли ПДК", "X max, м", "Y max, м",
            "Фон, мг/м³", "Превышение ПДК"]
    for j, h in enumerate(head, 1):
        c = summary.cell(row=4, column=j, value=h)
        c.font, c.alignment, c.border, c.fill = Font(bold=True, size=9), CENTER, CELL_BORDER, AXIS_FILL
    for i, (code, name, pdk, qmax, node, bg, exceeds) in enumerate(summary_rows, 5):
        vals = [code, name, pdk, round(qmax, 4), node[0], node[1], bg or "—", "да" if exceeds else "нет"]
        for j, v in enumerate(vals, 1):
            c = summary.cell(row=i, column=j, value=v)
            c.border = CELL_BORDER
            c.font = Font(size=9, color="B91C1C" if exceeds and j == 8 else "000000")
    r = 6 + len(summary_rows)
    summary.cell(row=r, column=1, value="Источники (рамка на листах — узел сетки источника)").font = Font(bold=True, size=10)
    for j, h in enumerate(["№", "Название", "X, м", "Y, м"], 1):
        c = summary.cell(row=r + 1, column=j, value=h)
        c.font, c.alignment, c.border, c.fill = Font(bold=True, size=9), CENTER, CELL_BORDER, AXIS_FILL
    for k, (s, num) in enumerate(zip(sources, numbers), r + 2):
        if s.get("lat") is None or s.get("lon") is None:
            continue
        x, y = gxy.xy(s["lat"], s["lon"])
        for j, v in enumerate([str(num), s.get("name") or "", int(round(x)), int(round(y))], 1):
            c = summary.cell(row=k, column=j, value=v)
            c.border = CELL_BORDER
            c.font = Font(size=9)
    for col, w in zip("ABCDEFGH", (10, 40, 14, 14, 10, 10, 12, 14)):
        summary.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
