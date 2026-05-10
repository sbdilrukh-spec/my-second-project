"""
Генерация PDF-отчёта по расчёту рассеивания (ОНД-86).
Использует reportlab + matplotlib.
"""

import base64
import io
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A3, A4, landscape, portrait
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

def _make_concentration_plot(points_data: list, grid_step: float = 500,
                              title: str = "Карта рассеивания ЗВ в приземном слое",
                              grid_params: dict = None,
                              sources: list = None,
                              boundary: list = None) -> io.BytesIO:
    """
    Сеточная карта рассеивания в стиле ОНД-86:
    каждая ячейка содержит числовое значение концентрации.
    Начало координат (0,0) в нижнем левом углу.
    """
    lats = np.array([p["lat"] for p in points_data])
    lons = np.array([p["lon"] for p in points_data])
    conc = np.array([p["c"] for p in points_data])

    # Начало координат — минимальные lat/lon (нижний левый угол)
    origin_lat = float(np.min(lats))
    origin_lon = float(np.min(lons))
    lat_rad = origin_lat * np.pi / 180

    # Переводим в метры от начала координат (всё >= 0)
    dx_e = (lons - origin_lon) * 111000.0 * np.cos(lat_rad)
    dy_n = (lats - origin_lat) * 111000.0

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

    # Адаптивный размер графика с правильным соотношением сторон
    x_range = unique_x[-1] - unique_x[0] + grid_step if unique_x else grid_step
    y_range = unique_y[-1] - unique_y[0] + grid_step if unique_y else grid_step
    aspect = y_range / x_range if x_range > 0 else 1.0
    fig_w = max(8, min(16, n_x * 0.5 + 2))
    fig_h = max(6, fig_w * aspect)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    font_size = max(4, min(8, int(fig_w / n_x * 10))) if n_x > 0 else 6

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
                    x_val, y_val, f"{c_val:.2f}",
                    ha="center", va="center", fontsize=font_size,
                    fontweight="bold" if is_max else "normal",
                    color="#CC0000" if is_max else "#000000",
                )

    ax.set_xlim(unique_x[0] - grid_step / 2, unique_x[-1] + grid_step / 2)
    ax.set_ylim(unique_y[0] - grid_step / 2, unique_y[-1] + grid_step / 2)
    ax.set_aspect("equal")
    ax.set_xlabel("X, м", fontsize=9)
    ax.set_ylabel("Y, м", fontsize=9)

    # Хелпер: lat/lon -> метры от начала координат сетки
    def _ll_to_xy(lat, lon):
        x = (lon - origin_lon) * 111000.0 * np.cos(lat_rad)
        y = (lat - origin_lat) * 111000.0
        return x, y

    # Контур предприятия / карьера — только линия, без заливки и нумерации
    if boundary and len(boundary) >= 2:
        bx, by = [], []
        for p in boundary:
            try:
                px, py = _ll_to_xy(float(p["lat"]), float(p["lon"]))
                bx.append(px); by.append(py)
            except (KeyError, TypeError, ValueError):
                continue
        if len(bx) >= 2:
            # Замыкаем контур
            if len(bx) >= 3:
                bx.append(bx[0]); by.append(by[0])
            ax.plot(bx, by, color="#EA580C", linewidth=1.6, zorder=4, solid_capstyle="round")

    # Маркеры источников отключены — карта рассеивания без них
    # (при необходимости источники видны в основной карте Leaflet)
    for idx, src in enumerate([]):
        if "_xy" in src:
            sx, sy = src["_xy"]
        else:
            try:
                sx, sy = _ll_to_xy(float(src["lat"]), float(src["lon"]))
            except (KeyError, TypeError, ValueError):
                continue
        # Кружок с цифрой
        ax.plot(sx, sy, marker="o", color="#7C2D12", markersize=11,
                markeredgecolor="#fff", markeredgewidth=1.2, zorder=6)
        ax.text(sx, sy, str(idx + 1), ha="center", va="center",
                fontsize=font_size + 1, color="#fff", fontweight="bold", zorder=7)

    ax.set_title(title, fontsize=11, fontweight="bold")

    # Жёлтые метки осей (координаты от начала: 0, 500, 1000, ...)
    ax.set_xticks(unique_x)
    ax.set_xticklabels([str(v) for v in unique_x])
    ax.set_yticks(unique_y)
    ax.set_yticklabels([str(v) for v in unique_y])
    ax.tick_params(labelsize=font_size)
    for lbl in ax.get_xticklabels():
        lbl.set_bbox(dict(facecolor="#FFE000", edgecolor="#333", linewidth=0.5, pad=2))
    for lbl in ax.get_yticklabels():
        lbl.set_bbox(dict(facecolor="#FFE000", edgecolor="#333", linewidth=0.5, pad=2))

    # Рамка вокруг всей области
    ax.plot([unique_x[0] - grid_step/2, unique_x[-1] + grid_step/2, unique_x[-1] + grid_step/2, unique_x[0] - grid_step/2, unique_x[0] - grid_step/2],
            [unique_y[0] - grid_step/2, unique_y[0] - grid_step/2, unique_y[-1] + grid_step/2, unique_y[-1] + grid_step/2, unique_y[0] - grid_step/2],
            color="#000", linewidth=1.5, zorder=4)

    fig.subplots_adjust(left=0.12, right=0.95, bottom=0.12, top=0.92)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Полярная картограмма — концентрации по румбам и расстояниям
# ---------------------------------------------------------------------------

# Румбы (16 направлений, как в розе ветров)
_COMPASS_16 = [
    "С", "ССВ", "СВ", "ВСВ",
    "В", "ВЮВ", "ЮВ", "ЮЮВ",
    "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ",
    "З", "ЗСЗ", "СЗ", "ССЗ",
]


def _make_polar_plot(points_data: list, sources: list = None,
                     pdk: float = None,
                     title: str = "Концентрации по румбам и расстояниям"):
    """
    Полярная картограмма: концентрации в координатах (расстояние, румб)
    относительно центра источников. 16 секторов по 22.5°, кольца на
    автоматически подобранных расстояниях (от шага сетки до её границы).
    Цветные клетки + численное значение в каждой.
    """
    if not points_data:
        return None
    lats = np.array([p["lat"] for p in points_data])
    lons = np.array([p["lon"] for p in points_data])
    conc = np.array([p["c"] for p in points_data])

    # Центр — среднее источников, если есть; иначе центр сетки
    if sources:
        try:
            center_lat = float(np.mean([float(s["lat"]) for s in sources]))
            center_lon = float(np.mean([float(s["lon"]) for s in sources]))
        except (KeyError, TypeError, ValueError):
            center_lat = float(np.mean(lats))
            center_lon = float(np.mean(lons))
    else:
        center_lat = float(np.mean(lats))
        center_lon = float(np.mean(lons))

    lat_rad = center_lat * np.pi / 180.0
    # Расстояния (м) и направления (азимут, 0=С, по часовой) от центра до каждой точки
    dx_e = (lons - center_lon) * 111_000.0 * np.cos(lat_rad)
    dy_n = (lats - center_lat) * 111_000.0
    r_pts = np.sqrt(dx_e**2 + dy_n**2)
    az_pts = (np.degrees(np.arctan2(dx_e, dy_n)) + 360.0) % 360.0

    # Подбираем кольца по реальному радиусу области
    r_max = float(np.max(r_pts)) if len(r_pts) else 0
    if r_max < 100:
        return None
    # 6 колец, начиная с разумного шага
    candidates = [50, 100, 200, 250, 500, 1000, 2000]
    # Шаг между кольцами — округлённый r_max / 6
    target = r_max / 6
    step = min(candidates, key=lambda v: abs(v - target))
    rings = [step * (i + 1) for i in range(6) if step * (i + 1) <= r_max + step * 0.5]
    if not rings:
        rings = [int(r_max)]

    # Сектора: 16 по 22.5°
    n_sec = 16
    sec_width = 360.0 / n_sec  # 22.5°

    # Для каждой (кольцо, сектор) — выбираем максимум среди точек,
    # попавших в это окно. Окно: r ± step/2, азимут ± sec_width/2.
    grid_vals = np.zeros((len(rings), n_sec))
    for ri, r0 in enumerate(rings):
        r_lo = r0 - step / 2
        r_hi = r0 + step / 2
        for si in range(n_sec):
            az0 = si * sec_width
            # окно по азимуту с обработкой перехода через 0/360
            az_diff = ((az_pts - az0 + 180) % 360) - 180  # -180..180
            in_sec = (np.abs(az_diff) <= sec_width / 2) & (r_pts >= r_lo) & (r_pts <= r_hi)
            if np.any(in_sec):
                grid_vals[ri, si] = float(np.max(conc[in_sec]))
            # Если в окне пусто — оставляем 0 (визуально светлая ячейка)

    max_c = float(grid_vals.max()) if grid_vals.max() > 0 else 1.0

    # Рисуем
    fig = plt.figure(figsize=(9, 9))
    ax = fig.add_subplot(111, projection="polar")
    # 0° наверху, по часовой стрелке (как роза ветров)
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)

    # Wedges
    for ri, r0 in enumerate(rings):
        r_inner = r0 - step / 2 if ri == 0 else (rings[ri - 1] + rings[ri]) / 2
        r_outer = r0 + step / 2 if ri == len(rings) - 1 else (rings[ri] + rings[ri + 1]) / 2
        for si in range(n_sec):
            theta_center = np.radians(si * sec_width)
            theta_lo = np.radians(si * sec_width - sec_width / 2)
            theta_hi = np.radians(si * sec_width + sec_width / 2)
            v = grid_vals[ri, si]
            ratio = v / max_c if max_c > 0 else 0
            # Цвет — плавная шкала бело→жёлтое→оранжевое→красное
            if v <= 0:
                fc = "#FFFFFF"
            elif ratio > 0.85:
                fc = "#DC2626"
            elif ratio > 0.6:
                fc = "#F97316"
            elif ratio > 0.35:
                fc = "#FACC15"
            elif ratio > 0.15:
                fc = "#FEF3C7"
            else:
                fc = "#FFFFFF"
            # Дополнительная подсветка превышения ПДК
            if pdk and v > pdk:
                edge = "#7F1D1D"
                lw = 1.2
            else:
                edge = "#94A3B8"
                lw = 0.5
            ax.bar(
                theta_center, r_outer - r_inner, width=np.radians(sec_width),
                bottom=r_inner, color=fc, edgecolor=edge, linewidth=lw, zorder=2,
            )
            if v > 0:
                # Подпись концентрации в центре сектора
                ax.text(
                    theta_center, (r_inner + r_outer) / 2,
                    f"{v:.3f}",
                    ha="center", va="center",
                    fontsize=7, fontweight="bold" if ratio > 0.85 else "normal",
                    color="#fff" if ratio > 0.85 else "#1F2937", zorder=3,
                )

    # Оформление
    ax.set_rlabel_position(112.5)  # положение подписей радиуса
    ax.set_rgrids(rings, labels=[f"{r:g} м" for r in rings], fontsize=8, color="#475569")
    ax.set_xticks(np.radians([i * sec_width for i in range(n_sec)]))
    ax.set_xticklabels(_COMPASS_16, fontsize=9, fontweight="bold")
    ax.set_ylim(0, rings[-1] + step / 2)
    ax.grid(color="#CBD5E1", linewidth=0.4)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=18)

    # Маркер источника(ов) — красная точка в центре + цифры
    ax.plot(0, 0, marker="o", color="#7C2D12", markersize=10,
            markeredgecolor="#fff", markeredgewidth=1.2, zorder=5)
    if sources and len(sources) > 1:
        ax.text(0, 0, str(len(sources)),
                ha="center", va="center", fontsize=8, fontweight="bold",
                color="#fff", zorder=6)
    else:
        ax.text(0, 0, "1",
                ha="center", va="center", fontsize=8, fontweight="bold",
                color="#fff", zorder=6)

    # Легенда внизу
    legend_text = (
        f"Цвет ячейки — отношение к максимуму ({max_c:.3f} мг/м³). "
        + (f"Жирная рамка — превышение ПДК ({pdk:.3f} мг/м³)." if pdk else "")
    )
    fig.text(0.5, 0.02, legend_text, ha="center", fontsize=8, color="#475569")

    fig.subplots_adjust(left=0.05, right=0.95, top=0.92, bottom=0.08)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
    buf.seek(0)
    return buf


# Единственный источник правды по соответствию «уровень ПДК → цвет».
# Используется и для contourf-заливки, и для легенды в PDF/PNG.
_PDK_LEVELS = [
    (0.01, "#DBEAFE", "0,01 ПДК"),
    (0.05, "#93C5FD", "0,05 ПДК"),
    (0.1,  "#3B82F6", "0,1 ПДК"),
    (0.2,  "#14B8A6", "0,2 ПДК"),
    (0.3,  "#22C55E", "0,3 ПДК"),
    (0.5,  "#A3E635", "0,5 ПДК"),
    (0.6,  "#FACC15", "0,6 ПДК"),
    (0.8,  "#F97316", "0,8 ПДК"),
    (1.0,  "#DC2626", "1,0 ПДК"),
    (2.0,  "#991B1B", "2,0 ПДК"),
    (5.0,  "#581C87", "5,0+ ПДК"),
]
# Соответствие для текстовой легенды в PDF (label → color).
_PDK_COLOR_MAP = [(label, color) for _, color, label in _PDK_LEVELS]


def _color_legend_html(present_levels=None) -> str:
    """HTML для ReportLab Paragraph: цветной квадрат + подпись уровня.
    Используем простой `<font color>` (а не `backColor`) — он легче
    разбирается ReportLab и не валит сборку PDF на длинных строках.
    Если передан present_levels — выводим только эти уровни.
    """
    parts = []
    for label, color in _PDK_COLOR_MAP:
        if present_levels is not None and label not in present_levels:
            continue
        # ■ — заполненный квадрат, прокрашен цветом уровня. Подпись — обычным.
        parts.append(f'<font color="{color}" size="11">■</font>&nbsp;{label}')
    return "&nbsp;&nbsp;".join(parts)


# ---------------------------------------------------------------------------
# Прозрачная карта рассеивания — для наложения в CorelDraw на свою подложку
# ---------------------------------------------------------------------------

def _make_transparent_dispersion_map(
    points_data: list,
    sources: list = None,
    boundary: list = None,
    pdk: float = 0.5,
    substance_name: str = "",
    show_axes: bool = False,
    show_title: bool = False,
    grid_data: dict = None,
):
    """
    Рендерит карту рассеивания на прозрачном фоне:
      - изолинии в долях ПДК с подписями
      - заливка между уровнями (полупрозрачная)
      - источники как пронумерованные кружки
      - контур площадки как оранжевая линия
      - изолиния 1.0 ПДК — выделена
    Без осей и заголовка по умолчанию — для наложения в CorelDraw.
    Возвращает io.BytesIO с PNG.
    """
    if not points_data:
        return None

    lats = np.array([p["lat"] for p in points_data])
    lons = np.array([p["lon"] for p in points_data])
    conc = np.array([p["c"] for p in points_data])

    # Размеры расчётной сетки в метрах
    if grid_data:
        x_length = float(grid_data.get("x_length", 7000))
        y_length = float(grid_data.get("y_length", 7000))
        grid_step = float(grid_data.get("step", 500))
    else:
        x_length = 7000.0
        y_length = 7000.0
        grid_step = 500.0

    # Левый-нижний угол сетки в географических координатах
    origin_lat = float(np.min(lats))
    origin_lon = float(np.min(lons))
    lat_rad = origin_lat * np.pi / 180.0

    # Точки сетки → метры от origin
    dx_e = (lons - origin_lon) * 111_000.0 * np.cos(lat_rad)
    dy_n = (lats - origin_lat) * 111_000.0

    # Регулярная 2D-сетка для contour/contourf
    n_x = int(round(x_length / grid_step)) + 1
    n_y = int(round(y_length / grid_step)) + 1
    xi = np.linspace(0.0, x_length, n_x)
    yi = np.linspace(0.0, y_length, n_y)
    XI, YI = np.meshgrid(xi, yi)
    ZI = np.zeros((n_y, n_x))
    for x_m, y_m, c_v in zip(dx_e, dy_n, conc):
        ix = int(round(x_m / grid_step))
        iy = int(round(y_m / grid_step))
        if 0 <= ix < n_x and 0 <= iy < n_y:
            ZI[iy, ix] = c_v

    # Концентрация в долях ПДК
    if pdk and pdk > 0:
        Z_pdk = ZI / pdk
    else:
        Z_pdk = ZI
    z_max = float(Z_pdk.max())
    if z_max <= 0:
        return None

    # Уровни изолиний по ТЗ
    iso_levels = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.6, 0.8, 1.0, 2.0, 5.0]
    iso_levels = [lv for lv in iso_levels if lv <= z_max * 1.1 and lv > 0]
    if len(iso_levels) < 2:
        iso_levels = [z_max * 0.3, z_max * 0.6, z_max] if z_max > 0 else [0.5, 1.0]

    # Размер фигуры пропорционален сетке
    aspect = y_length / x_length if x_length > 0 else 1.0
    fig_w = 12
    fig_h = max(4, fig_w * aspect)

    # Фон: белый только для PDF (когда показываем оси), прозрачный для CorelDraw
    fig_face = "white" if show_axes else "none"
    ax_face = "white" if show_axes else "none"
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor=fig_face)
    ax.set_facecolor(ax_face)

    # Радужная палитра — единый источник правды _PDK_LEVELS на уровне модуля.
    # Идёт от холодного (низкие концентрации) к горячему (превышение).
    fill_colors_full = [color for _, color, _ in _PDK_LEVELS]
    # iso_levels уже отфильтрован под фактический диапазон концентраций.
    # Берём столько цветов, сколько реально интервалов в fill_levels.
    fill_levels = [0.0] + list(iso_levels)
    cf = ax.contourf(
        XI, YI, Z_pdk, levels=fill_levels,
        colors=fill_colors_full[:len(fill_levels) - 1],
        alpha=0.55, extend="max",
    )

    # Все линии изолиний — без подписей (тонкие, для густоты картинки)
    cl_all = ax.contour(
        XI, YI, Z_pdk, levels=iso_levels,
        colors="#7F1D1D", linewidths=0.9, alpha=0.95,
    )

    # Подписываем только «ключевые» уровни — реже, читабельнее
    KEY_LEVELS = {0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0}
    label_levels = [lv for lv in iso_levels if any(abs(lv - k) < 1e-6 for k in KEY_LEVELS)]
    # Если ключевых нет в наборе (поле слишком слабое) — подпишем хотя бы максимальную
    if not label_levels:
        label_levels = [iso_levels[-1]]

    try:
        labels = ax.clabel(
            cl_all,
            levels=label_levels,
            inline=True,
            fontsize=12,
            fmt=lambda v: f"{v:g} ПДК",
            inline_spacing=8,
        )
    except TypeError:
        # Старые matplotlib без аргумента levels — фолбэк
        labels = ax.clabel(cl_all, inline=True, fontsize=12, fmt=lambda v: f"{v:g} ПДК")

    # Белая обводка текста, чтобы читалось и на цветной заливке
    try:
        import matplotlib.patheffects as pe
        for lab in labels or []:
            lab.set_path_effects([
                pe.Stroke(linewidth=3, foreground="white"),
                pe.Normal(),
            ])
    except Exception:
        pass

    # Изолиния 1,0 ПДК — выделена толстой красной + крупной подписью
    if any(abs(lv - 1.0) < 1e-6 for lv in iso_levels):
        cl_one = ax.contour(
            XI, YI, Z_pdk, levels=[1.0],
            colors="#DC2626", linewidths=2.6,
        )
        try:
            one_labels = ax.clabel(cl_one, inline=True, fontsize=13, fmt=lambda v: "1,0 ПДК")
            import matplotlib.patheffects as pe2
            for lab in one_labels or []:
                lab.set_fontweight("bold")
                lab.set_path_effects([
                    pe2.Stroke(linewidth=3.5, foreground="white"),
                    pe2.Normal(),
                ])
        except Exception:
            pass

    # Источники в карте рассеивания не отображаем — пользователь
    # просил убрать пронумерованные кружки. Контур площадки остаётся.
    _ = sources  # параметр оставляем в сигнатуре для совместимости

    # Контур площадки — оранжевая линия
    if boundary and len(boundary) >= 2:
        bx, by = [], []
        for p in boundary:
            try:
                bx.append((float(p["lon"]) - origin_lon) * 111_000.0 * np.cos(lat_rad))
                by.append((float(p["lat"]) - origin_lat) * 111_000.0)
            except (KeyError, TypeError, ValueError):
                continue
        if len(bx) >= 3:
            bx.append(bx[0])
            by.append(by[0])
        if len(bx) >= 2:
            ax.plot(bx, by, color="#EA580C", linewidth=2.0,
                    solid_capstyle="round", zorder=8)

    # ── Линейка масштаба — только в PNG для CorelDraw (show_axes=False) ─────
    # В PDF (show_axes=True) масштаб даёт сама координатная сетка с подписями.
    if not show_axes:
        scale_candidates = [50, 100, 200, 250, 500, 1000, 2000, 5000, 10000]
        target_len = x_length * 0.20
        bar_len = scale_candidates[0]
        for c in scale_candidates:
            if c <= target_len:
                bar_len = c
        bar_x0 = x_length * 0.04
        bar_y0 = y_length * 0.05
        bar_h = y_length * 0.008
        ax.add_patch(plt.Rectangle(
            (bar_x0 - bar_len * 0.005, bar_y0 - bar_h * 0.5),
            bar_len * 1.01, bar_h * 2.0,
            facecolor="white", edgecolor="black", linewidth=0.8, zorder=12,
        ))
        ax.add_patch(plt.Rectangle(
            (bar_x0, bar_y0), bar_len, bar_h,
            facecolor="black", edgecolor="black", linewidth=0.5, zorder=13,
        ))
        ax.add_patch(plt.Rectangle(
            (bar_x0 + bar_len / 2, bar_y0), bar_len / 2, bar_h,
            facecolor="white", edgecolor="black", linewidth=0.5, zorder=14,
        ))
        if bar_len >= 1000:
            labels_text = [(0, "0"), (bar_len / 2, f"{int(bar_len/2)} м"), (bar_len, f"{int(bar_len)} м")]
        else:
            labels_text = [(0, "0"), (bar_len / 2, f"{int(bar_len/2)}"), (bar_len, f"{int(bar_len)} м")]
        for x_off, txt in labels_text:
            ax.text(
                bar_x0 + x_off, bar_y0 + bar_h * 2.5, txt,
                ha="center", va="bottom", fontsize=11, fontweight="bold",
                color="black", zorder=15,
            )

        # ── Цветовая легенда — правый-нижний угол. Только для PNG.
        # Показываем только те уровни, что фактически есть на карте (iso_levels).
        if iso_levels:
            present = []
            for lv in iso_levels:
                color = next((c for v, c, _ in _PDK_LEVELS if abs(v - lv) < 1e-6), None)
                if color is None:
                    continue
                present.append((lv, color, f"{lv:g}"))

            if present:
                n = len(present)
                # Размер ячейки — в долях ширины/высоты осей (transAxes).
                cell_w = 0.038 if n <= 11 else 0.034
                cell_h = 0.028
                legend_w = cell_w * n
                legend_x0 = 0.97 - legend_w  # правый край с небольшим отступом
                legend_y0 = 0.06             # отступ от низа
                # Белая подложка под всю легенду (с местом для подписей)
                pad = 0.012
                ax.add_patch(plt.Rectangle(
                    (legend_x0 - pad, legend_y0 - 0.045),
                    legend_w + 2 * pad, cell_h + 0.075,
                    transform=ax.transAxes,
                    facecolor="white", edgecolor="#333",
                    linewidth=0.7, zorder=18,
                ))
                # Заголовок над цветами
                ax.text(
                    legend_x0 + legend_w / 2,
                    legend_y0 + cell_h + 0.012,
                    "Доли ПДК",
                    transform=ax.transAxes,
                    ha="center", va="bottom",
                    fontsize=9, fontweight="bold", color="black", zorder=20,
                )
                # Цветные ячейки + числовые подписи под каждой
                for i, (lv, color, txt) in enumerate(present):
                    cx = legend_x0 + i * cell_w
                    ax.add_patch(plt.Rectangle(
                        (cx, legend_y0),
                        cell_w * 0.95, cell_h,
                        transform=ax.transAxes,
                        facecolor=color, edgecolor="#333",
                        linewidth=0.4, zorder=19,
                    ))
                    ax.text(
                        cx + cell_w * 0.475,
                        legend_y0 - 0.006,
                        txt,
                        transform=ax.transAxes,
                        ha="center", va="top",
                        fontsize=8, color="black", zorder=20,
                    )

    ax.set_xlim(0, x_length)
    ax.set_ylim(0, y_length)
    ax.set_aspect("equal")

    if show_axes:
        # Прямоугольная координатная сетка по периметру:
        # шаг подписей подбираем "круглым" — 250/500/1000 м
        tick_candidates = [100, 200, 250, 500, 1000, 2000]
        # Целимся на 6-10 тиков по большей оси
        target_tick = max(x_length, y_length) / 8
        tick_step = tick_candidates[0]
        for c in tick_candidates:
            if c <= target_tick:
                tick_step = c
        x_ticks = list(np.arange(0, x_length + 1, tick_step))
        y_ticks = list(np.arange(0, y_length + 1, tick_step))
        ax.set_xticks(x_ticks)
        ax.set_yticks(y_ticks)
        ax.set_xticklabels([f"{int(t)}" for t in x_ticks])
        ax.set_yticklabels([f"{int(t)}" for t in y_ticks])
        ax.set_xlabel("X, м", fontsize=12)
        ax.set_ylabel("Y, м", fontsize=12)
        ax.tick_params(labelsize=11, direction="out", length=4, color="#333")
        ax.grid(True, alpha=0.35, linestyle="--", color="#666", linewidth=0.6)
        # Чёрная рамка по периметру
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color("#333")
            spine.set_linewidth(1.0)
    else:
        ax.set_axis_off()

    if show_title and substance_name:
        ax.set_title(
            f"Карта приземных концентраций {substance_name}, доли ПДК",
            fontsize=13, fontweight="bold", pad=10,
        )

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=150,
        bbox_inches="tight" if (show_axes or show_title) else None,
        pad_inches=0.05 if (show_axes or show_title) else 0,
        transparent=not show_axes,  # белый фон только в PDF (show_axes=True)
        facecolor=fig_face,
    )
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

    # Адаптивный формат страницы по соотношению сторон расчётной сетки.
    # По ТЗ: W/H >= 1.15 → альбомный A3, H/W >= 1.15 → книжный A4, иначе → A4 portrait.
    grid_data = request_data.get("grid") or {}
    gx = grid_data.get("x_length") or 7000
    gy = grid_data.get("y_length") or 7000
    if gx > 0 and gy > 0 and gx / gy >= 1.15:
        page_size = landscape(A3)
    else:
        # Книжный A4 — и для квадратной сетки, и для вытянутой по Y
        page_size = portrait(A4)

    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []
    W = page_size[0] - 4 * cm   # ширина контента

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

    # ============================================================
    # ТАБЛИЦА 1 «Исходные данные» — сводка по объекту (Радуга-стиль)
    # ============================================================
    sources_list = request_data.get("sources", []) or []
    by_subs_for_t1 = result_data.get("by_substance") or []
    enterprise_t1 = request_data.get("enterprise") or {}
    obj_name = enterprise_t1.get("name") or "—"
    meteo_t1 = request_data.get("meteo", {}) or {}
    grid_t1 = request_data.get("grid", {}) or {}

    story.append(Paragraph(
        "1. Исходные данные. Метеорологические характеристики и коэффициенты, "
        "определяющие условия рассеивания загрязняющих веществ в атмосфере",
        h1_style,
    ))
    story.append(Paragraph(f"<b>Объект:</b> {obj_name}", body_style))
    story.append(Spacer(1, 0.1 * cm))
    n_subs = len(by_subs_for_t1)
    n_srcs = len(sources_list)
    t1_rows = [
        ["Параметр", "Значение"],
        ["Число источников", str(n_srcs)],
        ["Число рассматриваемых вредных веществ", str(n_subs)],
        ["Число групп суммирования", "0"],
        ["Средняя максимальная температура наружного воздуха, °C",
         f"{meteo_t1.get('temperature', '—')}"],
        ["Коэффициент, зависящий от стратификации атмосферы (A)",
         "200"],   # для Узбекистана/средней Азии типично
        ["Скорость ветра (повторяемость превышения 5%), м/с",
         f"{meteo_t1.get('wind_speed', '—')}"],
        ["Класс устойчивости атмосферы", meteo_t1.get("stability_class", "—")],
        ["Город / регион", meteo_t1.get("city", "—")],
        ["Расчётная область, м", f"{grid_t1.get('x_length', '—')} × {grid_t1.get('y_length', '—')}"],
        ["Шаг сетки, м", f"{grid_t1.get('step', '—')}"],
    ]
    t1 = Table(t1_rows, colWidths=[W * 0.65, W * 0.35])
    t1.setStyle(TABLE_STYLE)
    story.append(t1)
    story.append(Spacer(1, 0.4 * cm))

    # ============================================================
    # ТАБЛИЦА 7 «Параметры источников» (Радуга-стиль)
    # ============================================================
    story.append(Paragraph("7. Параметры источников выбросов", h1_style))
    src_headers = [
        "№ ист.", "H, м", "D, м", "w₀, м/с",
        "V, м³/с", "Tг, °C", "Lat", "Lon", "Назв.",
    ]
    src_rows = [src_headers]
    for idx, s in enumerate(sources_list, 1):
        d = s.get("diameter") or 0.0
        w = s.get("velocity") or 0.0
        # Объём газовоздушной смеси V = π·D²/4 · w₀
        try:
            V = round(3.14159265 * (float(d) ** 2) / 4.0 * float(w), 4)
        except (TypeError, ValueError):
            V = "—"
        src_rows.append([
            f"{idx:02d}",
            str(s.get("height", "—")),
            str(s.get("diameter", "—")),
            str(s.get("velocity", "—")),
            str(V),
            str(s.get("temperature", "—")),
            f"{s.get('lat', 0):.5f}" if s.get("lat") is not None else "—",
            f"{s.get('lon', 0):.5f}" if s.get("lon") is not None else "—",
            (s.get("name") or "")[:18],
        ])
    col_w = [W * f for f in [0.07, 0.07, 0.07, 0.09, 0.10, 0.07, 0.13, 0.13, 0.27]]
    t7 = Table(src_rows, colWidths=col_w)
    t7.setStyle(TABLE_STYLE)
    story.append(t7)
    story.append(Spacer(1, 0.4 * cm))

    # ============================================================
    # ТАБЛИЦА 8 «Характеристика выбросов» — по веществам и источникам (Радуга)
    # ============================================================
    story.append(Paragraph("8. Характеристика выбросов", h1_style))

    # Группируем источники по веществам: substance_code → [(src_idx, src_name, em_gs, em_ty)]
    subs_emissions = {}
    subs_meta_map = {}
    for src_idx, src in enumerate(sources_list, 1):
        emissions = src.get("emissions") or []
        # Если emissions пуст — старый формат с одним веществом
        if not emissions and (src.get("emission_gs") or src.get("substance")):
            emissions = [{
                "substance": src.get("substance"),
                "emission_gs": src.get("emission_gs"),
                "emission_ty": src.get("emission_ty"),
                "pdk": src.get("pdk"),
            }]
        for em in emissions:
            sub = em.get("substance") or {}
            code = sub.get("code") or "—"
            em_gs = em.get("emission_gs") or 0.0
            em_ty = em.get("emission_ty") or 0.0
            # Конвертация если задано только одно из значений
            if (not em_gs) and em_ty:
                em_gs = em_ty * 1_000_000 / (365.25 * 24 * 3600)
            if (not em_ty) and em_gs:
                em_ty = em_gs * 365.25 * 24 * 3600 / 1_000_000
            if not em_gs:
                continue
            entry = subs_emissions.setdefault(code, [])
            entry.append({
                "src_idx": src_idx,
                "src_name": src.get("name") or f"Источник {src_idx}",
                "em_gs": em_gs,
                "em_ty": em_ty,
            })
            if code not in subs_meta_map:
                subs_meta_map[code] = {
                    "code": code,
                    "name": sub.get("name") or "—",
                    "pdk_mr": em.get("pdk") or sub.get("pdk_mr") or 0.5,
                    "hazard_class": sub.get("hazard_class"),
                }

    if not subs_emissions:
        story.append(Paragraph("<i>Выбросы веществ не заданы.</i>", body_style))
    else:
        for code, entries in subs_emissions.items():
            sub_meta = subs_meta_map.get(code, {})
            sub_name = sub_meta.get("name") or "—"
            pdk_val = sub_meta.get("pdk_mr") or 0.5
            hazard = sub_meta.get("hazard_class") or "—"
            total_gs = sum(e["em_gs"] for e in entries)
            total_ty = sum(e["em_ty"] for e in entries)
            # Шапка вещества
            story.append(Paragraph(
                f"<b>Код {code}</b> · <b>{sub_name}</b> · "
                f"ПДК={pdk_val} мг/м³ · Класс опасн.={hazard} · "
                f"Источников={len(entries)} · Σ т/год={round(total_ty, 4)} · "
                f"Σ г/с={round(total_gs, 6)}",
                body_style,
            ))
            # Подтаблица: построчно по источникам
            t8_headers = ["№ ист.", "Название", "г/с", "т/год"]
            t8_rows = [t8_headers]
            for e in entries:
                t8_rows.append([
                    f"{e['src_idx']:02d}",
                    (e["src_name"] or "")[:30],
                    f"{e['em_gs']:.6f}",
                    f"{e['em_ty']:.4f}",
                ])
            t8 = Table(t8_rows, colWidths=[W * 0.10, W * 0.50, W * 0.20, W * 0.20])
            t8.setStyle(TABLE_STYLE)
            story.append(t8)
            story.append(Spacer(1, 0.25 * cm))

    story.append(Spacer(1, 0.3 * cm))

    # ============================================================
    # 4. Суммарные результаты — оставляем для итогового вердикта (как было)
    # ============================================================
    story.append(Paragraph("4. Суммарные результаты", h1_style))
    pdk_val = result_data.get("pdk", 0.5)
    max_c = result_data.get("max_c", 0.0)
    exceeds = result_data.get("exceeds_pdk", False)

    summary_rows = [
        ["Показатель", "Значение"],
        ["ПДК главного вещества (Cmax / ПДК максимально)", f"{pdk_val} мг/м³"],
        ["Максимальная расчётная концентрация", f"{round(max_c, 5)} мг/м³"],
        ["Доля ПДК (Cmax / ПДК)", f"{round(max_c / pdk_val, 3) if pdk_val else '—'}"],
        ["Расчётная область, м", f"{request_data.get('grid', {}).get('x_length', '—')} × {request_data.get('grid', {}).get('y_length', '—')}"],
        ["Шаг сетки, м", f"{request_data.get('grid', {}).get('step', '—')}"],
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

    # --- 5. Сводная таблица по веществам ---
    from reportlab.platypus import PageBreak

    by_subs = result_data.get("by_substance") or []
    # Если по каким-то причинам by_substance пуст — формируем один «синтетический»
    # блок из плоских полей result_data (для обратной совместимости).
    if not by_subs:
        subst = request_data.get("substance") or {}
        if result_data.get("max_c") is not None:
            by_subs = [{
                "code": subst.get("code"),
                "substance": subst,
                "pdk": result_data.get("pdk", 0.5),
                "max_c": result_data.get("max_c", 0),
                "exceeds_pdk": result_data.get("exceeds_pdk", False),
            }]

    if by_subs:
        story.append(Paragraph("5. Сводка по веществам", h1_style))
        sub_headers = ["Код", "Вещество", "Cmax, мг/м³", "ПДК м.р.", "Cmax/ПДК", "Статус"]
        sub_rows = [sub_headers]
        for sub in by_subs:
            # Поддерживаем две формы данных:
            #  (а) precomputed_result от фронта — name/code на верхнем уровне sub
            #  (б) recomputed на бэке — name/code внутри sub["substance"]
            sub_meta = sub.get("substance") or {}
            sub_name = sub_meta.get("name") or sub.get("name") or "—"
            sub_code = sub_meta.get("code") or sub.get("code") or "—"
            sub_pdk = sub.get("pdk") or 0.5
            max_c = sub.get("max_c", 0)
            ratio = (max_c / sub_pdk) if sub_pdk > 0 else 0
            sub_rows.append([
                str(sub_code),
                str(sub_name),
                f"{max_c:.4f}",
                f"{sub_pdk:.3f}",
                f"{ratio:.3f}",
                "⚠ Превышение" if sub.get("exceeds_pdk") else "✓ В норме",
            ])
        sub_tbl = Table(sub_rows, colWidths=[
            W * 0.10, W * 0.34, W * 0.16, W * 0.13, W * 0.13, W * 0.14,
        ])
        sub_tbl.setStyle(TABLE_STYLE)
        story.append(sub_tbl)
        story.append(Spacer(1, 0.4 * cm))

    # ============================================================
    # ТАБЛИЦА 13 «Наибольшие концентрации» (Радуга-стиль)
    # Top-10 точек по убыванию QH с разбивкой по источникам.
    # ============================================================
    from reportlab.platypus import PageBreak

    has_any_top = any(
        sub.get("top_points") for sub in (result_data.get("by_substance") or [])
    )
    if has_any_top:
        story.append(PageBreak())
        story.append(Paragraph(
            "13. Наибольшие концентрации", h1_style,
        ))
        story.append(Paragraph(
            "<i>Условные обозначения: <b>QH</b> — концентрация в точке (доли ПДК); "
            "<b>X, Y</b> — координаты точки в метрах от левого-нижнего угла сетки; "
            "<b>HB</b> — направление ветра (град.), при котором достигнут максимум; "
            "<b>U</b> — скорость ветра (м/с); далее — top-источников по вкладу.</i>",
            body_style,
        ))
        story.append(Spacer(1, 0.2 * cm))

        for sub in (result_data.get("by_substance") or []):
            top_points = sub.get("top_points") or []
            if not top_points:
                continue
            # Имя/код вещества (поддерживаем обе формы: precomputed и recomputed)
            sub_meta_in = sub.get("substance") or {}
            sub_name = (
                sub_meta_in.get("name")
                or sub.get("name")
                or sub_meta_in.get("code")
                or sub.get("code")
                or "—"
            )
            sub_code = sub_meta_in.get("code") or sub.get("code") or "—"
            sub_pdk_v = sub.get("pdk") or 0.5

            story.append(Paragraph(
                f"<b>Вещество:</b> {sub_name} (код {sub_code}) · ПДК = {sub_pdk_v} мг/м³",
                body_style,
            ))
            story.append(Spacer(1, 0.1 * cm))

            # Считаем максимальное число вкладов в одной точке среди top_points,
            # чтобы определить число колонок для источников. Не больше 4 (как в Радуге).
            max_contribs = min(4, max((len(tp.get("contributions") or []) for tp in top_points), default=0))

            t13_headers = ["QH", "X, м", "Y, м", "HB, °", "U, м/с"]
            for i in range(max_contribs):
                t13_headers.extend([f"№ ист.{i+1}", "Вклад"])

            t13_rows = [t13_headers]
            for tp in top_points:
                row = [
                    f"{tp.get('qh', 0):.4f}",
                    str(tp.get("x_m", 0)),
                    str(tp.get("y_m", 0)),
                    str(tp.get("wind_dir_deg") if tp.get("wind_dir_deg") is not None else "—"),
                    f"{tp.get('wind_speed_ms', 0):.1f}",
                ]
                contribs = tp.get("contributions") or []
                for i in range(max_contribs):
                    if i < len(contribs):
                        c = contribs[i]
                        # Номер источника берём из src_index +1
                        si = c.get("src_index", 0) + 1
                        row.append(f"{si:02d}")
                        row.append(f"{c.get('contribution_pdk', 0):.4f}")
                    else:
                        row.append("")
                        row.append("")
                t13_rows.append(row)

            # Ширина колонок: QH+X+Y+HB+U = 5 базовых, дальше пары "источник+вклад"
            base_w = [W * 0.10, W * 0.07, W * 0.07, W * 0.07, W * 0.07]
            remaining = W - sum(base_w)
            if max_contribs > 0:
                pair_w = remaining / max_contribs
                src_col_w = pair_w * 0.35
                contrib_col_w = pair_w * 0.65
                col_w_t13 = base_w + [src_col_w if i % 2 == 0 else contrib_col_w
                                       for i in range(max_contribs * 2)]
            else:
                col_w_t13 = base_w
                # Растягиваем последнюю колонку на остаток
                col_w_t13[-1] += remaining

            t13 = Table(t13_rows, colWidths=col_w_t13)
            t13.setStyle(TABLE_STYLE)
            story.append(t13)
            story.append(Paragraph(
                f"<i>Минимум/максимум QH в этой выборке: "
                f"{top_points[-1].get('qh', 0):.6f} / {top_points[0].get('qh', 0):.6f}</i>",
                ParagraphStyle("t13_minmax", fontName=FONT, fontSize=8,
                                textColor=colors.HexColor("#475569"),
                                alignment=TA_LEFT, spaceAfter=2),
            ))
            story.append(Spacer(1, 0.4 * cm))

    # --- 6. Карты рассеивания (прозрачные, для наложения в CorelDraw) ---

    enterprise = request_data.get("enterprise") or {}
    boundary = (enterprise.get("boundary") or [])
    ent_name = enterprise.get("name") or "—"

    sources_for_map = request_data.get("sources") or []
    grid_data = request_data.get("grid") or {}
    show_axes = bool(request_data.get("map_show_axes", True))
    show_title = bool(request_data.get("map_show_title", True))
    # Тип карты: "isolines" (по умолчанию) или "grid" (старая ОНД-сетка с числами)
    map_type = (request_data.get("map_type") or "isolines").lower()

    # Стили легенды и примечания — один раз, потом переиспользуем
    legend_style = ParagraphStyle(
        "color_legend", fontName=FONT, fontSize=10,
        alignment=TA_CENTER, spaceAfter=4, leading=14,
    )
    note_style = ParagraphStyle(
        "map_note", fontName=FONT, fontSize=8,
        alignment=TA_LEFT, textColor=colors.HexColor("#475569"),
        leftIndent=4, rightIndent=4, spaceAfter=4, leading=11,
    )

    for sub_idx, sub in enumerate(by_subs):
        # Поддерживаем две формы: name/code как на верхнем уровне (precomputed
        # от фронта), так и внутри sub["substance"] (recomputed на бэкенде).
        sub_meta = sub.get("substance") or {}
        sub_name = (
            sub_meta.get("name")
            or sub.get("name")
            or sub.get("code")
            or f"Вещество {sub_idx + 1}"
        )
        sub_points = sub.get("points", [])
        sub_pdk = sub.get("pdk") or 0.5
        if not sub_points:
            continue
        try:
            if map_type == "grid":
                # Старая сетка ОНД с числами концентраций в ячейках.
                # _make_concentration_plot ожидает grid_step из grid_data.
                grid_step = grid_data.get("step", 500) if grid_data else 500
                title_text = (
                    f"Карта рассеивания: {sub_name}" if show_title
                    else "Карта рассеивания ЗВ в приземном слое"
                )
                png_buf = _make_concentration_plot(
                    sub_points,
                    grid_step=grid_step,
                    title=title_text,
                    grid_params=grid_data,
                    sources=None,        # источники в карте отключены
                    boundary=boundary,
                )
            else:
                png_buf = _make_transparent_dispersion_map(
                    sub_points,
                    sources=sources_for_map,
                    boundary=boundary,
                    pdk=sub_pdk,
                    substance_name=sub_name,
                    show_axes=show_axes,
                    show_title=show_title,
                    grid_data=grid_data,
                )
            if png_buf is None:
                continue

            story.append(PageBreak())
            section_title = f"6.{sub_idx + 1} Карта рассеивания — {sub_name}"
            story.append(Paragraph(section_title, h1_style))

            info_lines = [f"<b>Предприятие:</b> {ent_name}"]
            if enterprise.get("address"):
                info_lines.append(f"<b>Адрес:</b> {enterprise['address']}")
            info_lines.append(f"<b>Точек контура:</b> {len(boundary)}")
            info_lines.append(f"<b>Вещество:</b> {sub_name}")
            info_lines.append(f"<b>ПДК:</b> {sub_pdk} мг/м³")
            story.append(Paragraph(" &nbsp;·&nbsp; ".join(info_lines), body_style))
            story.append(Spacer(1, 0.3 * cm))

            # Размер картинки под выбранный формат страницы
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(io.BytesIO(png_buf.getvalue()))
                src_w, src_h = ir.getSize()
                ratio = src_h / src_w if src_w else 0.75
            except Exception:
                ratio = 0.75

            max_h = (page_size[1] - 4 * cm) * 0.80
            disp_w = W
            disp_h = W * ratio
            if disp_h > max_h:
                disp_h = max_h
                disp_w = max_h / ratio if ratio else W

            png_buf.seek(0)
            map_img = RLImage(png_buf, width=disp_w, height=disp_h)
            story.append(map_img)

            # Цветовая легенда + примечание (только для типа "isolines",
            # для "grid" они не нужны — там значения прямо в ячейках).
            # Изолируем в свой try/except — если что-то с разметкой,
            # карта останется в PDF, упадёт только пояснение.
            if map_type != "grid":
                try:
                    story.append(Spacer(1, 0.2 * cm))
                    story.append(Paragraph(
                        "<b>Цветовая шкала (доли ПДК):</b><br/>" + _color_legend_html(),
                        legend_style,
                    ))
                    story.append(Paragraph(
                        "<i>Примечание: цветная заливка отображает все области, где "
                        "приземная концентрация выше <b>0,01 ПДК</b>. Отдельные мелкие "
                        "пятна вне основного облака соответствуют локальным пикам "
                        "концентрации у изолированных источников выбросов "
                        "(на расстоянии Xm от каждой трубы). Жирная красная линия — "
                        "граница превышения ПДК (1,0 ПДК).</i>",
                        note_style,
                    ))
                except Exception as e:
                    print(f"[pdf_export] Легенда/примечание #{sub_idx} не построены: {e}")
        except Exception as e:
            traceback_text = ""
            try:
                import traceback as _tb
                traceback_text = _tb.format_exc()
            except Exception:
                pass
            print(f"[pdf_export] Карта рассеивания #{sub_idx} ({sub_name}) не построена: {e}\n{traceback_text}")

    doc.build(story)
    return buf.getvalue()
