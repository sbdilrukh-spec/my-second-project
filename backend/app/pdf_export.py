"""
Генерация PDF-отчёта по расчёту рассеивания (ОНД-86).
Использует reportlab + matplotlib.
"""

import io
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Регистрация шрифта с поддержкой кириллицы
# ---------------------------------------------------------------------------

def _register_font() -> str:
    candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("DocFont", path))
                return "DocFont"
            except Exception:
                continue
    return "Helvetica"


FONT = _register_font()


# ---------------------------------------------------------------------------
# Вспомогательные стили
# ---------------------------------------------------------------------------

def _styles():
    s = getSampleStyleSheet()
    title = ParagraphStyle(
        "DocTitle",
        fontName=FONT,
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    h1 = ParagraphStyle(
        "DocH1",
        fontName=FONT,
        fontSize=12,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "DocBody",
        fontName=FONT,
        fontSize=9,
        leading=13,
    )
    return title, h1, body


TABLE_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, -1), FONT),
    ("FONTSIZE", (0, 0), (-1, 0), 9),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
])


# ---------------------------------------------------------------------------
# График поля концентраций (matplotlib)
# ---------------------------------------------------------------------------

def _make_concentration_plot(points_data: list, grid_step: float = 200,
                              title: str = "Карта рассеивания ЗВ в приземном слое") -> io.BytesIO:
    """
    Сеточная карта рассеивания в стиле ОНД-86:
    каждая ячейка содержит числовое значение концентрации.
    """
    lats = np.array([p["lat"] for p in points_data])
    lons = np.array([p["lon"] for p in points_data])
    conc = np.array([p["c"] for p in points_data])

    center_lat = float(np.mean(lats))
    center_lon = float(np.mean(lons))
    lat_rad = center_lat * np.pi / 180

    # Переводим в метры от центра
    dx_e = (lons - center_lon) * 111000.0 * np.cos(lat_rad)
    dy_n = (lats - center_lat) * 111000.0

    # Округляем к сетке
    dx_r = np.round(dx_e / grid_step).astype(int) * int(grid_step)
    dy_r = np.round(dy_n / grid_step).astype(int) * int(grid_step)

    unique_x = sorted(set(dx_r))
    unique_y = sorted(set(dy_r))
    n_x, n_y = len(unique_x), len(unique_y)

    x_idx = {v: i for i, v in enumerate(unique_x)}
    y_idx = {v: i for i, v in enumerate(unique_y)}
    grid_arr = np.zeros((n_y, n_x))
    for dx, dy, c in zip(dx_r, dy_r, conc):
        xi, yi = x_idx.get(int(dx)), y_idx.get(int(dy))
        if xi is not None and yi is not None:
            grid_arr[yi, xi] = c

    max_c = float(conc.max()) if conc.max() > 0 else 1.0

    # Адаптивный размер графика
    cell_inch = max(0.35, min(0.7, 12.0 / max(n_x, n_y)))
    fig_w = max(8, n_x * cell_inch + 1.5)
    fig_h = max(6, n_y * cell_inch + 1.5)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    font_size = max(4, min(8, int(cell_inch * 12)))

    for yi, y_val in enumerate(unique_y):
        for xi, x_val in enumerate(unique_x):
            c_val = grid_arr[yi, xi]
            ratio = c_val / max_c if max_c > 0 else 0
            is_max = abs(c_val - max_c) < max_c * 0.001 and c_val > 0

            # Цвет фона
            if is_max:
                fc = "#FF9999"
            elif ratio > 0.7:
                fc = "#FFCC66"
            elif ratio > 0.3:
                fc = "#FFFF99"
            elif ratio > 0.05:
                fc = "#FFFFDD"
            else:
                fc = "#FFFFFF"

            rect = plt.Rectangle(
                (x_val - grid_step / 2, y_val - grid_step / 2),
                grid_step, grid_step,
                facecolor=fc, edgecolor="#555555", linewidth=0.4,
            )
            ax.add_patch(rect)

            if c_val > 0:
                ax.text(
                    x_val, y_val, f"{c_val:.4f}",
                    ha="center", va="center", fontsize=font_size,
                    fontweight="bold" if is_max else "normal",
                    color="#CC0000" if is_max else "#000000",
                )

    ax.set_xlim(unique_x[0] - grid_step / 2, unique_x[-1] + grid_step / 2)
    ax.set_ylim(unique_y[0] - grid_step / 2, unique_y[-1] + grid_step / 2)
    ax.set_aspect("equal")
    ax.set_xlabel("X, м (от источника)", fontsize=9)
    ax.set_ylabel("Y, м (от источника)", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold")

    # Жёлтые метки осей
    ax.set_xticks(unique_x)
    ax.set_yticks(unique_y)
    ax.tick_params(labelsize=font_size)
    for lbl in ax.get_xticklabels():
        lbl.set_bbox(dict(facecolor="#FFE000", edgecolor="#333", linewidth=0.5, pad=2))
    for lbl in ax.get_yticklabels():
        lbl.set_bbox(dict(facecolor="#FFE000", edgecolor="#333", linewidth=0.5, pad=2))

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Основная функция генерации PDF
# ---------------------------------------------------------------------------

def generate_pdf(request_data: dict, result_data: dict) -> bytes:
    """
    Генерирует PDF-отчёт.

    request_data — словарь с исходными данными (sources, meteo, grid, pdk).
    result_data  — словарь с результатами расчёта.
    Возвращает bytes (содержимое PDF).
    """
    title_style, h1_style, body_style = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []
    W = A4[0] - 4 * cm   # ширина контента

    # --- Заголовок ---
    story.append(Paragraph(
        "РАСЧЁТ РАССЕИВАНИЯ ЗАГРЯЗНЯЮЩИХ ВЕЩЕСТВ<br/>В АТМОСФЕРНОМ ВОЗДУХЕ",
        title_style,
    ))
    story.append(Paragraph(
        "Методика ОНД-86 (Приказ МПР №273)",
        ParagraphStyle("sub", fontName=FONT, fontSize=10, alignment=TA_CENTER, spaceAfter=4),
    ))
    story.append(Paragraph(
        f"Дата расчёта: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        ParagraphStyle("date", fontName=FONT, fontSize=9, alignment=TA_CENTER, spaceAfter=16),
    ))

    # --- 1. Источники выбросов ---
    story.append(Paragraph("1. Параметры источников выбросов", h1_style))
    src_headers = ["Название", "H, м", "D, м", "w₀, м/с", "Tг, °C", "M, г/с", "M, т/год"]
    src_rows = [src_headers]
    for s in request_data.get("sources", []):
        M_gs = s.get("emission_gs") or 0.0
        M_ty = s.get("emission_ty") or 0.0
        if not M_gs and M_ty:
            M_gs = round(M_ty * 1_000_000 / (365.25 * 24 * 3600), 4)
        if not M_ty and M_gs:
            M_ty = round(M_gs * 365.25 * 24 * 3600 / 1_000_000, 4)
        src_rows.append([
            s.get("name", "—"),
            str(s.get("height", "—")),
            str(s.get("diameter", "—")),
            str(s.get("velocity", "—")),
            str(s.get("temperature", "—")),
            str(round(M_gs, 4)),
            str(round(M_ty, 4)),
        ])
    col_w = [W * f for f in [0.24, 0.10, 0.10, 0.12, 0.12, 0.16, 0.16]]
    t = Table(src_rows, colWidths=col_w)
    t.setStyle(TABLE_STYLE)
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))

    # --- 2. Метеоусловия ---
    story.append(Paragraph("2. Метеорологические условия", h1_style))
    meteo = request_data.get("meteo", {})
    meteo_rows = [
        ["Параметр", "Значение"],
        ["Город / регион", meteo.get("city", "—")],
        ["Скорость ветра", f"{meteo.get('wind_speed', '—')} м/с"],
        ["Направление ветра (откуда)", f"{meteo.get('wind_direction', '—')}°"],
        ["Класс устойчивости атмосферы", meteo.get("stability_class", "—")],
        ["Температура воздуха", f"{meteo.get('temperature', '—')} °C"],
    ]
    tm = Table(meteo_rows, colWidths=[W * 0.6, W * 0.4])
    tm.setStyle(TABLE_STYLE)
    story.append(tm)
    story.append(Spacer(1, 0.4 * cm))

    # --- 3. Результаты по каждому источнику ---
    story.append(Paragraph("3. Результаты расчёта по источникам", h1_style))
    res_headers = ["Источник", "Cm, мг/м³", "Xm, м"]
    res_rows = [res_headers]
    for sr in result_data.get("source_results", []):
        res_rows.append([
            sr.get("name", "—"),
            str(round(sr.get("cm_mg", 0), 4)),
            str(round(sr.get("xm", 0), 1)),
        ])
    tr = Table(res_rows, colWidths=[W * 0.50, W * 0.25, W * 0.25])
    tr.setStyle(TABLE_STYLE)
    story.append(tr)
    story.append(Spacer(1, 0.4 * cm))

    # --- 4. Итог ---
    story.append(Paragraph("4. Суммарные результаты", h1_style))
    pdk_val = result_data.get("pdk", 0.5)
    max_c = result_data.get("max_c", 0.0)
    exceeds = result_data.get("exceeds_pdk", False)

    summary_rows = [
        ["Показатель", "Значение"],
        ["ПДК загрязняющего вещества", f"{pdk_val} мг/м³"],
        ["Максимальная расчётная концентрация", f"{round(max_c, 5)} мг/м³"],
        ["Доля ПДК (Cmax / ПДК)", f"{round(max_c / pdk_val, 3) if pdk_val else '—'}"],
        ["Расчётная область (радиус)", f"{request_data.get('grid', {}).get('radius', '—')} м"],
        ["Шаг сетки", f"{request_data.get('grid', {}).get('step', '—')} м"],
    ]
    ts = Table(summary_rows, colWidths=[W * 0.6, W * 0.4])
    ts.setStyle(TABLE_STYLE)
    story.append(ts)
    story.append(Spacer(1, 0.5 * cm))

    # --- Заключение ---
    conclusion_color = "#DC2626" if exceeds else "#16A34A"
    conclusion_text = (
        f"⚠ ПРЕВЫШЕНИЕ ПДК: расчётная концентрация {round(max_c, 5)} мг/м³ "
        f"превышает ПДК ({pdk_val} мг/м³) в {round(max_c / pdk_val, 2) if pdk_val else '?'} раза."
        if exceeds else
        f"✓ ПДК не превышена: максимальная расчётная концентрация "
        f"{round(max_c, 5)} мг/м³ не превышает ПДК ({pdk_val} мг/м³)."
    )
    story.append(Paragraph(
        conclusion_text,
        ParagraphStyle(
            "conclusion",
            fontName=FONT,
            fontSize=10,
            textColor=colors.HexColor(conclusion_color),
            borderPad=6,
            spaceAfter=12,
        ),
    ))

    # --- 5. График ---
    story.append(Paragraph("5. Поле приземных концентраций", h1_style))
    points = result_data.get("points", [])
    if points:
        grid_step = request_data.get("grid", {}).get("step", 200)
        plot_buf = _make_concentration_plot(points, grid_step=grid_step)
        img = RLImage(plot_buf, width=W, height=W * 0.75)
        story.append(img)

    doc.build(story)
    return buf.getvalue()
