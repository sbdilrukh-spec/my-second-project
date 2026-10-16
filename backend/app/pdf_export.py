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

from .ond86 import source_number

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
                              boundary: list = None,
                              boundaries: list = None,
                              pdk: float = None,
                              transparent: bool = False,
                              dpi: int = 150) -> io.BytesIO:
    """
    Сеточная карта рассеивания в стиле ОНД-86:
    каждая ячейка содержит числовое значение концентрации.
    Начало координат (0,0) в нижнем левом углу.

    Если передан pdk, значения в ячейках выводятся в долях ПДК
    (c / ПДК), иначе — в исходных единицах (мг/м³).

    transparent=True — прозрачный фон и полупрозрачная заливка ячеек
    (для наложения на свою подложку в CorelDraw): пустые ячейки полностью
    прозрачны, заполненные — цветные с альфой, сквозь них видна подложка.
    dpi — разрешение растра; для экспорта в Corel имеет смысл 300+, чтобы
    цифры оставались чёткими при увеличении.
    """
    from matplotlib.colors import to_rgba
    # Альфа заливки: на прозрачном фоне ячейки полупрозрачны, чтобы сквозь
    # них просвечивала подложка; в PDF (transparent=False) — плотный цвет.
    cell_alpha = 0.45 if transparent else 1.0
    lats = np.array([p["lat"] for p in points_data])
    lons = np.array([p["lon"] for p in points_data])
    conc_raw = np.array([p["c"] for p in points_data])
    # Если задан ПДК — отображаем всё в долях ПДК. Цветовая шкала и
    # подписи ячеек используют одно и то же значение, чтобы единицы
    # совпадали с легендой и Таблицей 13.
    if pdk and pdk > 0:
        conc = conc_raw / pdk
        units_label = "доли ПДК"
    else:
        conc = conc_raw
        units_label = "мг/м³"

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
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)

    font_size = max(4, min(8, int(fig_w / n_x * 10))) if n_x > 0 else 6

    # Заливка ячеек одним слоем pcolormesh (раньше — отдельный Rectangle на
    # каждую ячейку: тысячи объектов matplotlib, экспорт шёл десятки секунд).
    ratio_arr = grid_arr / max_c if max_c > 0 else np.zeros_like(grid_arr)
    max_mask = (np.abs(grid_arr - max_c) < max_c * 0.001) & (grid_arr > 0)
    empty_rgba = (0.0, 0.0, 0.0, 0.0) if transparent else to_rgba("#FFFFFF")
    cell_rgba = np.empty((n_y, n_x, 4))
    cell_rgba[...] = empty_rgba
    for mask, base in (
        (ratio_arr > 0.05, "#FFFFDD"),
        (ratio_arr > 0.3, "#FFFF99"),
        (ratio_arr > 0.7, "#FFCC66"),
        (max_mask, "#FF9999"),
    ):
        cell_rgba[mask] = to_rgba(base, cell_alpha)
    ux = np.asarray(unique_x, dtype=float)
    uy = np.asarray(unique_y, dtype=float)
    x_edges = np.concatenate([[ux[0] - grid_step / 2], (ux[:-1] + ux[1:]) / 2, [ux[-1] + grid_step / 2]])
    y_edges = np.concatenate([[uy[0] - grid_step / 2], (uy[:-1] + uy[1:]) / 2, [uy[-1] + grid_step / 2]])
    mesh = ax.pcolormesh(x_edges, y_edges, np.zeros((n_y, n_x)), shading="flat",
                         edgecolors="#555555", linewidth=0.4)
    mesh.set_array(None)
    mesh.set_facecolor(cell_rgba.reshape(-1, 4))

    # Подписи значений (адаптивный формат для долей ПДК). Рисуются не через
    # ax.text, а поверх растра в _save_with_cell_labels: тысяча Text-объектов
    # matplotlib — основная задержка экспорта сетки.
    cell_labels = []
    for yi, y_val in enumerate(unique_y):
        for xi, x_val in enumerate(unique_x):
            c_val = grid_arr[yi, xi]
            if c_val <= 0:
                continue
            if c_val >= 10:
                txt = f"{c_val:.1f}"
            elif c_val >= 1:
                txt = f"{c_val:.2f}"
            else:
                txt = f"{c_val:.4f}"
            cell_labels.append((x_val, y_val, txt, bool(max_mask[yi, xi])))
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

    # Контуры предприятия / карьеров — каждый отдельной линией, без заливки.
    # Поддерживаем несколько контуров (boundaries); одиночный boundary — как один.
    contours = boundaries if boundaries else ([boundary] if boundary else [])
    for contour in contours:
        if not contour or len(contour) < 2:
            continue
        bx, by = [], []
        for p in contour:
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

    if not transparent:
        # Для CorelDraw заголовок не нужен (имя вещества — в имени файла), а его
        # ширина меняла бы размер PNG от вещества к веществу.
        ax.set_title(title, fontsize=11, fontweight="bold")
    # Маленькая поясняющая надпись, в каких единицах значения в ячейках
    ax.text(
        0.5, -0.06,
        f"Значения в ячейках: {units_label}",
        transform=ax.transAxes, ha="center", va="top",
        fontsize=9, color="#475569", style="italic",
    )

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
    buf = _save_with_cell_labels(fig, ax, cell_labels, font_size, dpi, transparent)
    plt.close(fig)
    return buf


def _save_with_cell_labels(fig, ax, labels, font_size, dpi, transparent,
                           pad_inches=0.3) -> io.BytesIO:
    """
    Растр фигуры + подписи ячеек, нарисованные PIL прямо по пикселям, затем
    обрезка по содержимому (как bbox_inches="tight"). Эквивалент ax.text +
    savefig, но в десятки раз быстрее на сетках в сотни/тысячи ячеек.
    """
    from PIL import Image, ImageDraw, ImageFont
    from matplotlib import font_manager

    if transparent:
        fig.patch.set_alpha(0.0)
        ax.patch.set_alpha(0.0)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    img = Image.fromarray(np.asarray(fig.canvas.buffer_rgba()).copy(), "RGBA")
    height = img.height

    size_px = max(6, int(round(font_size * dpi / 72.0)))
    regular = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), size_px)
    bold = ImageFont.truetype(
        font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold")),
        size_px,
    )
    draw = ImageDraw.Draw(img)
    if labels:
        pts = ax.transData.transform(np.array([(x, y) for x, y, _, _ in labels], dtype=float))
        for (px, py), (_, _, txt, is_max) in zip(pts, labels):
            draw.text((px, height - py), txt, anchor="mm",
                      font=bold if is_max else regular,
                      fill=(204, 0, 0, 255) if is_max else (0, 0, 0, 255))

    # Обрезка как у bbox_inches="tight" (подписи ячеек внутри осей, на неё не влияют)
    bbox = fig.get_tightbbox(renderer)
    x0 = max(0, int((bbox.x0 - pad_inches) * dpi))
    x1 = min(img.width, int(np.ceil((bbox.x1 + pad_inches) * dpi)))
    y0 = max(0, int(height - (bbox.y1 + pad_inches) * dpi))
    y1 = min(height, int(np.ceil(height - (bbox.y0 - pad_inches) * dpi)))
    img = img.crop((x0, y0, x1, y1))
    if not transparent:
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img).convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=3, dpi=(dpi, dpi))
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


class _SrcView:
    """dict источника → атрибуты number/name для source_number."""

    def __init__(self, d):
        self.number = d.get("number")
        self.name = d.get("name")


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

    # Коэффициент A — из справочника городов (стратификация атмосферы)
    try:
        from .meteo_data import CITIES as _CITIES
        _coef_A = _CITIES.get(meteo_t1.get("city", ""), {}).get("A", 200)
    except Exception:
        _coef_A = 200

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
         str(_coef_A)],
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

    # Начало координат (левый-нижний угол сетки) — те же оси X,Y в метрах,
    # что в Таблицах 12/13 «Радуги». Origin считаем как в compute_grid.
    _lats0 = [s.get("lat") for s in sources_list if s.get("lat") is not None]
    _lons0 = [s.get("lon") for s in sources_list if s.get("lon") is not None]
    if _lats0 and _lons0:
        _c_lat = sum(_lats0) / len(_lats0)
        _c_lon = sum(_lons0) / len(_lons0)
        _sox = grid_t1.get("source_offset_x")
        _soy = grid_t1.get("source_offset_y")
        if _sox is None:
            _sox = (grid_t1.get("x_length", 7000) or 7000) / 2
        if _soy is None:
            _soy = (grid_t1.get("y_length", 7000) or 7000) / 2
        _lat_rad = _c_lat * np.pi / 180.0
        _origin_lat = _c_lat - _soy / 111_000.0
        _origin_lon = _c_lon - _sox / (111_000.0 * np.cos(_lat_rad))
    else:
        _origin_lat = _origin_lon = _lat_rad = 0.0

    def _src_xy(lat, lon):
        try:
            x = (float(lon) - _origin_lon) * 111_000.0 * np.cos(_lat_rad)
            y = (float(lat) - _origin_lat) * 111_000.0
            return f"{int(round(x))}", f"{int(round(y))}"
        except (TypeError, ValueError):
            return "—", "—"

    src_headers = [
        "Код", "H, м", "D, м", "w₀, м/с", "V, м³/с", "Tг, °C",
        "X1, м", "Y1, м", "X2, м", "Y2, м", "C, °", "РН",
    ]
    src_rows = [src_headers]
    for idx, s in enumerate(sources_list, 1):
        src_num = source_number(_SrcView(s), idx - 1)
        d = s.get("diameter") or 0.0
        w = s.get("velocity") or 0.0
        # Объём газовоздушной смеси V = π·D²/4 · w₀
        try:
            V = round(3.14159265 * (float(d) ** 2) / 4.0 * float(w), 4)
        except (TypeError, ValueError):
            V = "—"
        x1, y1 = _src_xy(s.get("lat"), s.get("lon"))
        # Точечный источник — конец линии не задан (прочерк). Угол C: для
        # площадного берём его поворот, иначе 90° (ось на север, как в Радуге).
        is_area = (s.get("source_type") or s.get("type")) == "area"
        angle = s.get("area_angle") if is_area else 90
        src_rows.append([
            src_num,
            str(s.get("height", "—")),
            str(s.get("diameter", "—")),
            str(s.get("velocity", "—")),
            str(V),
            str(s.get("temperature", "—")),
            x1, y1, "—", "—",
            str(angle if angle is not None else 90),
            "1.00",
        ])
    col_w = [W * f for f in [0.07, 0.06, 0.06, 0.08, 0.09, 0.07,
                             0.10, 0.10, 0.09, 0.09, 0.06, 0.06]]
    t7 = Table(src_rows, colWidths=col_w)
    t7.setStyle(TABLE_STYLE)
    story.append(t7)
    story.append(Paragraph(
        "<i>X, Y — координаты источника в метрах от левого-нижнего угла расчётной "
        "области (X2, Y2 — конец линейного/площадного источника). C — угол оси "
        "источника к северу, град. РН — коэффициент учёта рельефа.</i>",
        body_style,
    ))
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
                "src_num": source_number(_SrcView(src), src_idx - 1),
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
                    # Коэффициент оседания F (1.0 газы, 3.0 пыль) — если задан
                    "F": sub.get("F"),
                }

    # Карта максимальных концентраций источников по веществам (мг/м³) для колонки
    # «мг/куб.м.» — берём Cm из результатов расчёта (source_results каждого вещества).
    _cm_by_code = {}
    for _sub in by_subs_for_t1:
        _meta = _sub.get("substance") or {}
        _code = _meta.get("code") or _sub.get("code") or "—"
        _m = {}
        for _sr in (_sub.get("source_results") or []):
            if _sr.get("name") is not None:
                _m[_sr["name"]] = _sr.get("cm_mg")
        _cm_by_code[_code] = _m

    if not subs_emissions:
        story.append(Paragraph("<i>Выбросы веществ не заданы.</i>", body_style))
    else:
        for code, entries in subs_emissions.items():
            sub_meta = subs_meta_map.get(code, {})
            sub_name = sub_meta.get("name") or "—"
            pdk_val = sub_meta.get("pdk_mr") or 0.5
            F_val = sub_meta.get("F")
            if F_val is None:
                F_val = 1.0   # по умолчанию газ (без оседания)
            total_gs = sum(e["em_gs"] for e in entries)
            total_ty = sum(e["em_ty"] for e in entries)
            cm_map = _cm_by_code.get(code, {})
            # Шапка вещества (как в Радуге: код, наименование, ПДК, коэф. оседания,
            # число источников, суммарный выброс т/год и г/с)
            story.append(Paragraph(
                f"<b>Код {code}</b> · <b>{sub_name}</b> · "
                f"ПДК={pdk_val} мг/м³ · Коэф. оседания F={F_val} · "
                f"Источников={len(entries)} · Σ т/год={round(total_ty, 4)} · "
                f"Σ г/с={round(total_gs, 6)}",
                body_style,
            ))
            # Подтаблица: по 3 источника в строке (Н ИСТ · г/с · мг/м³ · т/год),
            # как в Радуге. Каждый блок из 4 колонок.
            t8_headers = (["Н ист.", "г/с", "мг/м³", "т/год"] * 3)
            t8_rows = [t8_headers]
            triple = []
            for e in entries:
                cm_val = cm_map.get(e["src_name"])
                cm_txt = f"{cm_val:.4f}" if isinstance(cm_val, (int, float)) else "—"
                triple.extend([
                    e["src_num"],
                    f"{e['em_gs']:.6f}",
                    cm_txt,
                    f"{e['em_ty']:.4f}",
                ])
                if len(triple) == 12:
                    t8_rows.append(triple)
                    triple = []
            if triple:
                triple.extend([""] * (12 - len(triple)))  # добить последнюю строку
                t8_rows.append(triple)
            _bw = W / 12.0
            t8 = Table(t8_rows, colWidths=[_bw] * 12)
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

            # Вклады источников (до 10, как в Радуге) — в одну колонку с переносом,
            # чтобы уместить их по ширине страницы: «№ист = доля ПДК».
            _MAX_CONTRIBS = 10
            _contrib_style = ParagraphStyle(
                "t13_contrib", fontName=FONT, fontSize=7, leading=8,
            )
            t13_headers = ["QH", "X, м", "Y, м", "HB, °", "U, м/с",
                           "Источники (№ = вклад, доли ПДК)"]
            t13_rows = [t13_headers]
            for tp in top_points:
                contribs = (tp.get("contributions") or [])[:_MAX_CONTRIBS]
                parts = [
                    f"{c.get('number') or (c.get('src_index', 0) + 1)}={c.get('contribution_pdk', 0):.4f}"
                    for c in contribs
                ]
                contrib_cell = Paragraph(", ".join(parts) if parts else "—", _contrib_style)
                t13_rows.append([
                    f"{tp.get('qh', 0):.4f}",
                    str(tp.get("x_m", 0)),
                    str(tp.get("y_m", 0)),
                    # HB как в «Радуге»: куда дует ветер, от оси OX против часовой
                    str((270 - tp["wind_dir_deg"]) % 360 if tp.get("wind_dir_deg") is not None else "—"),
                    f"{tp.get('wind_speed_ms', 0):.1f}",
                    contrib_cell,
                ])

            col_w_t13 = [W * f for f in [0.09, 0.08, 0.08, 0.07, 0.07, 0.61]]
            t13 = Table(t13_rows, colWidths=col_w_t13)
            t13.setStyle(TABLE_STYLE)
            story.append(t13)

            # Итоговая строка — минимальная и максимальная концентрации по ВСЕМ
            # точкам расчёта (в долях ПДК), как в «Радуге».
            _pts = sub.get("points") or []
            if _pts and sub_pdk_v:
                _qhs = [p["c"] / sub_pdk_v for p in _pts if p.get("c") is not None]
                _gmin = min(_qhs) if _qhs else 0.0
                _gmax = max(_qhs) if _qhs else 0.0
            else:
                _gmin = top_points[-1].get("qh", 0)
                _gmax = top_points[0].get("qh", 0)
            story.append(Paragraph(
                f"Минимальная и максимальная концентрации в точках расчётов: "
                f"{_gmin:.10f}   {_gmax:.10f}",
                ParagraphStyle("t13_minmax", fontName=FONT, fontSize=8,
                                textColor=colors.HexColor("#475569"),
                                alignment=TA_LEFT, spaceAfter=2),
            ))
            story.append(Spacer(1, 0.4 * cm))

    # --- 6. Карты рассеивания (прозрачные, для наложения в CorelDraw) ---

    enterprise = request_data.get("enterprise") or {}
    boundary = (enterprise.get("boundary") or [])
    # Несколько контуров-объектов (до 5); если нет — используем одиночный boundary.
    boundaries = enterprise.get("boundaries") or ([boundary] if boundary else [])
    boundary_points_total = sum(len(c or []) for c in boundaries)
    ent_name = enterprise.get("name") or "—"

    grid_data = request_data.get("grid") or {}

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
            # Сетка ОНД с числами концентраций (доли ПДК) в ячейках
            grid_step = grid_data.get("step", 500) if grid_data else 500
            png_buf = _make_concentration_plot(
                sub_points,
                grid_step=grid_step,
                title=f"Карта приземных концентраций {sub_name}, доли ПДК",
                grid_params=grid_data,
                sources=None,        # источники в карте отключены
                boundaries=boundaries,
                pdk=sub_pdk,         # значения в ячейках — в долях ПДК
            )
            if png_buf is None:
                continue

            story.append(PageBreak())
            section_title = f"6.{sub_idx + 1} Карта рассеивания — {sub_name}"
            story.append(Paragraph(section_title, h1_style))

            info_lines = [f"<b>Предприятие:</b> {ent_name}"]
            if enterprise.get("address"):
                info_lines.append(f"<b>Адрес:</b> {enterprise['address']}")
            _cont_label = f"Объектов: {len(boundaries)}, точек: {boundary_points_total}" if len(boundaries) > 1 else f"Точек контура: {boundary_points_total}"
            info_lines.append(f"<b>{_cont_label}</b>")
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
