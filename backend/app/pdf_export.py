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

    # Маркеры источников — пронумерованные кружки
    src_list = sources or []
    if not src_list and grid_params:
        # Совместимость: если sources не передан, используем offset из grid_params
        sx = grid_params.get("source_offset_x", x_range / 2)
        sy = grid_params.get("source_offset_y", y_range / 2)
        src_list = [{"_xy": (sx, sy)}]

    for idx, src in enumerate(src_list):
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
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), facecolor="none")
    ax.set_facecolor("none")

    # Заливка между изолиниями (полупрозрачная розово-красная палитра)
    fill_colors = [
        "#FFE4E1", "#FFCCCC", "#FF9999", "#FF7777",
        "#F87171", "#EF4444", "#DC2626", "#B91C1C",
        "#991B1B", "#7F1D1D",
    ]
    fill_levels = [0.0] + list(iso_levels)
    cf = ax.contourf(
        XI, YI, Z_pdk, levels=fill_levels,
        colors=fill_colors[:len(fill_levels) - 1],
        alpha=0.45, extend="max",
    )

    # Линии изолиний — поверх заливки, более насыщенные
    cl = ax.contour(
        XI, YI, Z_pdk, levels=iso_levels,
        colors="#7F1D1D", linewidths=0.9, alpha=0.95,
    )
    # Подписи на линиях с белой обводкой текста — читаются на любом фоне
    labels = ax.clabel(cl, inline=True, fontsize=8, fmt=lambda v: f"{v:g} ПДК")
    for lab in labels or []:
        lab.set_path_effects([])  # сброс
    # Перерисовываем подписи белой обводкой через PathEffect
    try:
        import matplotlib.patheffects as pe
        for lab in labels or []:
            lab.set_path_effects([
                pe.Stroke(linewidth=2.5, foreground="white"),
                pe.Normal(),
            ])
    except Exception:
        pass

    # Изолиния 1.0 ПДК — выделена
    if any(abs(lv - 1.0) < 1e-6 for lv in iso_levels):
        cl_one = ax.contour(
            XI, YI, Z_pdk, levels=[1.0],
            colors="#DC2626", linewidths=2.4,
        )
        try:
            ax.clabel(cl_one, inline=True, fontsize=10, fmt=lambda v: "1,0 ПДК")
        except Exception:
            pass

    # Источники — пронумерованные кружки
    if sources:
        for i, src in enumerate(sources):
            try:
                sx = (float(src["lon"]) - origin_lon) * 111_000.0 * np.cos(lat_rad)
                sy = (float(src["lat"]) - origin_lat) * 111_000.0
            except (KeyError, TypeError, ValueError):
                continue
            ax.plot(sx, sy, "o", color="#7C2D12", markersize=12,
                    markeredgecolor="white", markeredgewidth=1.5, zorder=10)
            ax.text(sx, sy, str(i + 1), color="white", fontsize=8,
                    fontweight="bold", ha="center", va="center", zorder=11)

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
            ax.plot(bx, by, color="#EA580C", linewidth=1.8,
                    solid_capstyle="round", zorder=8)

    ax.set_xlim(0, x_length)
    ax.set_ylim(0, y_length)
    ax.set_aspect("equal")

    if show_axes:
        ax.set_xlabel("X, м", fontsize=9)
        ax.set_ylabel("Y, м", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.3, linestyle="--", color="#888")
    else:
        ax.set_axis_off()

    if show_title and substance_name:
        ax.set_title(
            f"Карта приземных концентраций {substance_name}, доли ПДК",
            fontsize=11, fontweight="bold", pad=8,
        )

    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    buf = io.BytesIO()
    fig.savefig(
        buf, format="png", dpi=150,
        bbox_inches="tight" if (show_axes or show_title) else None,
        pad_inches=0.05 if (show_axes or show_title) else 0,
        transparent=True,
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
            sub_meta = sub.get("substance") or {}
            sub_pdk = sub.get("pdk") or 0.5
            max_c = sub.get("max_c", 0)
            ratio = (max_c / sub_pdk) if sub_pdk > 0 else 0
            sub_rows.append([
                str(sub_meta.get("code") or sub.get("code") or "—"),
                str(sub_meta.get("name") or "—"),
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

    # --- 6. Карты рассеивания (прозрачные, для наложения в CorelDraw) ---
    from reportlab.platypus import PageBreak

    enterprise = request_data.get("enterprise") or {}
    boundary = (enterprise.get("boundary") or [])
    ent_name = enterprise.get("name") or "—"

    sources_for_map = request_data.get("sources") or []
    grid_data = request_data.get("grid") or {}
    show_axes = bool(request_data.get("map_show_axes", True))
    show_title = bool(request_data.get("map_show_title", True))

    for sub_idx, sub in enumerate(by_subs):
        sub_meta = sub.get("substance") or {}
        sub_name = sub_meta.get("name") or sub.get("code") or f"Вещество {sub_idx + 1}"
        sub_points = sub.get("points", [])
        sub_pdk = sub.get("pdk") or 0.5
        if not sub_points:
            continue
        try:
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
