"""
Расчёт рассеивания загрязняющих веществ в атмосфере по методике ОНД-86
(Госкомгидромет СССР, 1987), раздел 2.

Формулы: (2.1)–(2.22) — Cm, xm, um; (2.23а–г) s1; (2.24) низкие источники;
(2.28) s2; (2.29)–(2.30) — концентрация при скорости ветра u ≠ um.
В каждой точке сетки, как в «Радуге», перебираются направления и скорости
ветра (0,5 м/с … U*), и берётся максимум суммарной концентрации; запоминаются
опасные направление HB и скорость U.

Координаты внутри расчёта — метры: x на восток, y на север. Направление ветра
θ — откуда дует (метеорологическое), факел идёт в сторону θ+180°.
"""

import math
import re
import numpy as np

from .ond86_kernel import HAVE_NUMBA
if HAVE_NUMBA:
    from .ond86_kernel import max_field as _kernel_max_field

# Коэффициент оседания по умолчанию — газы и мелкодисперсные аэрозоли
F_GAS = 1.0

# Шаг грубого перебора направлений и полуширина уточнения (градусы)
_DIR_STEP_COARSE = 10
_DIR_REFINE_HALF = 9


# ---------------------------------------------------------------------------
# Номер источника
# ---------------------------------------------------------------------------

def source_number(src, index: int) -> str:
    """
    Номер источника, который задал пользователь (0001, 6001, ...). Если не
    задан: число в начале названия («0001», «№154 ДСК») считается номером,
    иначе — порядковый номер в списке (01, 02, …). То же правило на
    фронтенде (sourceNumber.js).
    """
    num = getattr(src, "number", None)
    if num is not None and str(num).strip():
        return str(num).strip()
    # Старые проекты: номер записан в начале названия («0001», «№154 ДСК №2»)
    name = str(getattr(src, "name", "") or "")
    m = _NAME_NUMBER.match(name)
    if m:
        return m.group(1)
    return f"{index + 1:02d}"


_NAME_NUMBER = re.compile(r"^\s*(?:№|N|#)?\s*(\d+)(?!\d)")


# ---------------------------------------------------------------------------
# Параметры одиночного источника: Cm, xm, um (ОНД-86, п. 2.1–2.22)
# ---------------------------------------------------------------------------

def _n_coef(v: float) -> float:
    """Коэффициент n по vm или v'm (2.7б, 2.7в)."""
    if v >= 2.0:
        return 1.0
    if v >= 0.5:
        return 0.532 * v * v - 2.13 * v + 3.13
    return 4.4 * v


def calc_source_params(
    M: float,   # г/с
    H: float,   # м
    D: float,   # м
    w0: float,  # м/с
    Tg: float,  # °C
    Ta: float,  # °C
    A: float,   # коэффициент стратификации
    F: float = F_GAS,
    eta: float = 1.0,  # коэффициент рельефа
) -> dict:
    """Cm (мг/м³), Xm (м), Um (м/с) и промежуточные величины по ОНД-86."""
    H = max(float(H or 0.0), 2.0)   # п. 2.1: для наземных источников H = 2 м
    D = max(float(D or 0.0), 0.0)
    w0 = max(float(w0 or 0.0), 0.0)
    F = float(F or F_GAS)
    V1 = math.pi * D * D / 4.0 * w0
    dT = float(Tg) - float(Ta)
    vmp = 1.3 * w0 * D / H                       # (2.5) v'm
    fe = 800.0 * vmp ** 3                        # (2.6)
    hot = dT > 0.0 and V1 > 0.0
    f = 1000.0 * w0 * w0 * D / (H * H * dT) if hot else float("inf")

    if hot and f < 100.0:
        vm = 0.65 * (V1 * dT / H) ** (1.0 / 3.0)                           # (2.3)
        m = 1.0 / (0.67 + 0.1 * math.sqrt(f) + 0.34 * f ** (1.0 / 3.0))   # (2.7а)
        if vm >= 0.5:
            vn = vmp if fe < f else vm             # п. 2.4: fe < f < 100 → n по v'm
            n = _n_coef(vn)
            Cm = A * M * F * m * n * eta / (H * H * (V1 * dT) ** (1.0 / 3.0))  # (2.1)
            if vm <= 2.0:
                d = 4.95 * vm * (1.0 + 0.28 * f ** (1.0 / 3.0))             # (2.14)
                um = vm                                                     # (2.17)
            else:
                d = 7.0 * math.sqrt(vm) * (1.0 + 0.28 * f ** (1.0 / 3.0))  # (2.15)
                um = vm * (1.0 + 0.12 * math.sqrt(f))                       # (2.18)
            branch = "hot"
        else:
            n = None
            m = 2.86 * m                                                    # (2.10)
            Cm = A * M * F * m * eta / H ** (7.0 / 3.0)                     # (2.9)
            d = 2.48 * (1.0 + 0.28 * fe ** (1.0 / 3.0))                     # (2.13)
            um = 0.5                                                        # (2.16)
            branch = "hot_weak"
    else:
        # f ≥ 100 или ΔT ≈ 0 — холодный выброс, п. 2.6–2.8
        vm = None
        if vmp >= 0.5 and V1 > 0.0:
            m = None
            n = _n_coef(vmp)
            K = D / (8.0 * V1)                                              # (2.8)
            Cm = A * M * F * n * eta * K / H ** (4.0 / 3.0)                 # (2.8а)
            if vmp <= 2.0:
                d = 11.4 * vmp                                              # (2.20)
                um = vmp                                                    # (2.22)
            else:
                d = 16.0 * math.sqrt(vmp)                                   # (2.21)
                um = 2.2 * vmp                                              # (2.22а)
            branch = "cold"
        else:
            n = None
            m = 0.9                                                         # (2.10а)
            Cm = A * M * F * m * eta / H ** (7.0 / 3.0)
            d = 5.7                                                         # (2.19)
            um = 0.5
            branch = "cold_weak"

    Xm = d * H if F < 2.0 else (5.0 - F) / 4.0 * d * H                     # (2.12)
    return {
        "Cm": float(Cm), "Xm": float(Xm), "Um": float(um), "type": branch,
        "f": None if f == float("inf") else float(f), "vm": vm, "vm_prime": float(vmp),
        "m": m, "n": n, "d": float(d), "V1": float(V1), "dT": float(dT),
        "F": F, "H": H,
    }


# ---------------------------------------------------------------------------
# Безразмерные функции ОНД-86
# ---------------------------------------------------------------------------

def _r_coef(q):
    """(2.29) Cmu = r·Cm, q = u/um."""
    q = np.asarray(q, dtype=float)
    return np.where(q <= 1.0, 0.67 * q + 1.67 * q ** 2 - 1.34 * q ** 3,
                    3.0 * q / (2.0 * q ** 2 - q + 2.0))


def _p_coef(q):
    """(2.30) xmu = p·xm."""
    q = np.asarray(q, dtype=float)
    return np.where(q <= 0.25, 3.0,
                    np.where(q <= 1.0, 8.43 * (1.0 - q) ** 5 + 1.0, 0.32 * q + 0.68))


def _s1(t: np.ndarray, F: float, H: float) -> np.ndarray:
    """(2.23а–г) по оси факела, с поправкой (2.24) для низких источников."""
    s = np.zeros_like(t)
    a = (t > 0) & (t <= 1)
    ta = t[a]
    sa = 3 * ta ** 4 - 8 * ta ** 3 + 6 * ta ** 2
    if H < 10.0:
        h = max(H, 2.0)
        sa = 0.125 * (10.0 - h) + 0.125 * (h - 2.0) * sa                    # (2.24)
    s[a] = sa
    b = (t > 1) & (t <= 8)
    s[b] = 1.13 / (0.13 * t[b] ** 2 + 1.0)
    c = t > 8
    tc = t[c]
    if F <= 1.5:
        s[c] = tc / (3.58 * tc ** 2 - 35.2 * tc + 120.0)
    else:
        s[c] = 1.0 / (0.1 * tc ** 2 + 2.47 * tc - 17.8)
    return s


# ---------------------------------------------------------------------------
# Подготовка источников и поле одного источника
# ---------------------------------------------------------------------------

def _subsource_offsets(src):
    """
    Смещения (dx на восток, dy на север, м) точечных подысточников от центра.
    Трубный источник — одна точка; площадной (source_type == "area") —
    центры ячеек сетки N×N внутри прямоугольника L×W, повёрнутого на
    area_angle (от оси X на восток, против часовой стрелки).
    """
    if getattr(src, "source_type", "stack") != "area":
        return [(0.0, 0.0)]
    L = getattr(src, "area_length", None) or 0.0
    W = getattr(src, "area_width", None) or 0.0
    if L <= 0 or W <= 0:
        return [(0.0, 0.0)]
    n = int(getattr(src, "area_subdivisions", None) or 5)
    n = max(1, min(n, 20))
    ang = math.radians(getattr(src, "area_angle", None) or 0.0)
    cos_a, sin_a = math.cos(ang), math.sin(ang)
    offsets = []
    for i in range(n):
        u = -L / 2.0 + L * (i + 0.5) / n
        for j in range(n):
            v = -W / 2.0 + W * (j + 0.5) / n
            offsets.append((u * cos_a - v * sin_a, u * sin_a + v * cos_a))
    return offsets


class _Frame:
    """Локальная система координат в метрах вокруг центра (lat0, lon0)."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0 = lat0
        self.lon0 = lon0
        self.kx = 111_000.0 * math.cos(math.radians(lat0))
        self.ky = 111_000.0

    def to_xy(self, lat, lon):
        return (np.asarray(lon) - self.lon0) * self.kx, (np.asarray(lat) - self.lat0) * self.ky


def _prepare_sources(sources, Ta, A, frame: _Frame):
    """Параметры ОНД-86 и координаты подысточников для каждого источника."""
    prepared = []
    for idx, src in enumerate(sources):
        M = src.get_emission_gs()
        if M <= 0:
            continue
        F = getattr(src, "F", None) or F_GAS
        pr = calc_source_params(M=M, H=src.height, D=src.diameter, w0=src.velocity,
                                Tg=src.temperature, Ta=Ta, A=A, F=F)
        x0, y0 = frame.to_xy(src.lat, src.lon)
        offs = _subsource_offsets(src)
        prepared.append({
            "src": src, "index": idx, "pr": pr,
            "sx": np.array([float(x0) + o[0] for o in offs]),
            "sy": np.array([float(y0) + o[1] for o in offs]),
            "w": 1.0 / len(offs),
        })
    return prepared


def _source_field(p, px, py, ex, ey, u):
    """
    Концентрация (мг/м³) от одного источника.
    px, py — (N,1); ex, ey — единичный вектор факела, (1,K) или (N,K);
    u — скорость ветра, скаляр или (N,1). Результат — (N,K).
    """
    pr = p["pr"]
    q = u / pr["Um"]
    Cmu = _r_coef(q) * pr["Cm"]
    xmu = _p_coef(q) * pr["Xm"]
    k = np.minimum(u, 5.0)
    total = None
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        for sx, sy in zip(p["sx"], p["sy"]):
            dx = px - sx
            dy = py - sy
            xa = dx * ex + dy * ey                 # вдоль факела
            ya = dx * ey - dy * ex                 # поперёк факела
            pos = xa > 0
            t = np.where(pos, xa / xmu, 0.0)
            s1 = _s1(t, pr["F"], pr["H"])
            ty = np.where(pos, k * ya * ya / np.where(pos, xa * xa, 1.0), 0.0)   # (2.28)
            s2 = 1.0 / (1.0 + 5 * ty + 12.8 * ty ** 2 + 17 * ty ** 3 + 45.1 * ty ** 4) ** 2
            c = np.where(pos, s1 * s2, 0.0)
            total = c if total is None else total + c
    return Cmu * p["w"] * total


def _plume_vectors(theta_deg):
    th = np.radians(theta_deg)
    return -np.sin(th), -np.cos(th)


def _wind_speeds(prepared, u_star: float):
    """Перебираемые скорости: 0,5 м/с … U* с шагом 0,5 плюс um источников."""
    u_star = max(float(u_star or 0.0), 0.5)
    speeds = set(np.round(np.arange(0.5, u_star + 1e-9, 0.5), 2).tolist())
    speeds.add(round(u_star, 2))
    ums = {round(min(max(p["pr"]["Um"], 0.5), u_star), 2) for p in prepared}
    if len(ums) > 30:
        ums = {round(v * 4) / 4 for v in ums}
    speeds |= ums
    return sorted(speeds)


def _max_field(prepared, px, py, speeds, fixed_dir=None):
    """
    Максимум суммарной концентрации по направлениям и скоростям ветра.
    Возвращает (c_max, dir_deg, u) для каждой точки. Основной путь — ядро
    numba (ond86_kernel); без numba — тот же перебор на numpy.
    """
    if HAVE_NUMBA and prepared:
        def cat(fn):
            return np.concatenate([fn(p) for p in prepared]).astype(np.float64)
        SX = cat(lambda p: p["sx"])
        SY = cat(lambda p: p["sy"])
        CMW = cat(lambda p: np.full(len(p["sx"]), p["pr"]["Cm"] * p["w"]))
        XM = cat(lambda p: np.full(len(p["sx"]), p["pr"]["Xm"]))
        UM = cat(lambda p: np.full(len(p["sx"]), p["pr"]["Um"]))
        FS = cat(lambda p: np.full(len(p["sx"]), p["pr"]["F"]))
        HS = cat(lambda p: np.full(len(p["sx"]), p["pr"]["H"]))
        if fixed_dir is not None:
            dirs = np.array([float(fixed_dir) % 360.0])
        else:
            dirs = np.arange(0, 360, _DIR_STEP_COARSE, dtype=np.float64)
        best, bdir, bu = _kernel_max_field(
            np.ascontiguousarray(px, dtype=np.float64), np.ascontiguousarray(py, dtype=np.float64),
            SX, SY, CMW, XM, UM, FS, HS,
            np.asarray(speeds, dtype=np.float64), float(max(speeds)),
            dirs, _DIR_REFINE_HALF,
        )
        bdir = np.where(best > 0, np.round(bdir) % 360, -1)
        return best, bdir, bu
    return _max_field_numpy(prepared, px, py, speeds, fixed_dir)


def _max_field_numpy(prepared, px, py, speeds, fixed_dir=None):
    """Запасной перебор на numpy (если нет numba)."""
    npt = len(px)
    pxc = px[:, None]
    pyc = py[:, None]
    best = np.zeros(npt)
    bdir = np.full(npt, -1.0)
    bu = np.zeros(npt)

    def scan(theta):   # theta: (1,K) или (N,K)
        ex, ey = _plume_vectors(theta)
        for u in speeds:
            tot = None
            for p in prepared:
                c = _source_field(p, pxc, pyc, ex, ey, u)
                tot = c if tot is None else tot + c
            j = np.argmax(tot, axis=1)
            v = tot[np.arange(npt), j]
            upd = v > best
            best[upd] = v[upd]
            bdir[upd] = np.broadcast_to(theta, tot.shape)[np.arange(npt), j][upd]
            bu[upd] = u

    if not prepared:
        return best, bdir, bu
    if fixed_dir is not None:
        scan(np.array([[float(fixed_dir)]]))
    else:
        scan(np.arange(0, 360, _DIR_STEP_COARSE, dtype=float)[None, :])
        # Уточнение направления с шагом 1° вокруг найденного максимума
        offs = np.arange(-_DIR_REFINE_HALF, _DIR_REFINE_HALF + 1, dtype=float)[None, :]
        scan((bdir[:, None] + offs) % 360.0)
    bdir = np.where(best > 0, np.round(bdir) % 360, -1)
    return best, bdir, bu


def _contributions_at(prepared, x, y, theta, u):
    """Вклады источников (мг/м³) в точках x, y при направлении theta и скорости u."""
    ex, ey = _plume_vectors(np.asarray(theta, float)[:, None])
    xc = np.asarray(x, float)[:, None]
    yc = np.asarray(y, float)[:, None]
    uc = np.asarray(u, float)[:, None]
    return [(p, _source_field(p, xc, yc, ex, ey, uc)[:, 0]) for p in prepared]


# ---------------------------------------------------------------------------
# Расчёт поля на сетке
# ---------------------------------------------------------------------------

def _grid_center(sources):
    return (sum(s.lat for s in sources) / len(sources),
            sum(s.lon for s in sources) / len(sources))


def compute_grid(sources, meteo, city_data: dict,
                 grid_radius: float = None, grid_step: float = 500,
                 x_length: float = None, y_length: float = None,
                 source_offset_x: float = None, source_offset_y: float = None,
                 center_lat: float = None, center_lon: float = None):
    """
    Приземные концентрации на регулярной сетке (начало (0,0) — нижний левый
    угол, источник/центр — в точке (source_offset_x, source_offset_y)).

    center_lat/center_lon — точка привязки сетки. По умолчанию — центроид
    переданных источников; многовеществный расчёт передаёт центроид ВСЕХ
    источников проекта, чтобы сетка была общей для всех веществ.

    Режимы: wind_mode="360" — перебор направлений; "single" — одно направление.
    Скорость ветра всегда перебирается от 0,5 м/с до U* (meteo.wind_speed).

    Возвращает lats, lons, total_mg, src_results, dir_at_max, u_at_max.
    """
    A = city_data.get("A", 200)
    wind_mode = getattr(meteo, "wind_mode", "360")

    if center_lat is None or center_lon is None:
        center_lat, center_lon = _grid_center(sources)

    if x_length is None and grid_radius is not None:
        x_length = y_length = grid_radius * 2
        source_offset_x = source_offset_y = grid_radius
    elif x_length is None:
        x_length = y_length = 7000
        source_offset_x = source_offset_y = 3500
    if y_length is None:
        y_length = x_length
    if source_offset_x is None:
        source_offset_x = x_length / 2
    if source_offset_y is None:
        source_offset_y = y_length / 2

    frame = _Frame(center_lat, center_lon)
    n_x = int(x_length / grid_step) + 1
    n_y = int(y_length / grid_step) + 1
    gx, gy = np.meshgrid(np.arange(n_x) * grid_step - source_offset_x,
                         np.arange(n_y) * grid_step - source_offset_y)
    px = gx.flatten().astype(float)
    py = gy.flatten().astype(float)
    grid_lats = center_lat + py / frame.ky
    grid_lons = center_lon + px / frame.kx

    prepared = _prepare_sources(sources, meteo.temperature, A, frame)
    speeds = _wind_speeds(prepared, meteo.wind_speed)
    fixed = meteo.wind_direction if wind_mode == "single" else None
    total_mg, dir_at_max, u_at_max = _max_field(prepared, px, py, speeds, fixed)

    # Параметры источников для таблиц: Cm, Xm, Um по ОНД-86. Для площадного
    # аналитический Cm относится к выбросу из одной точки и завышен — отчётным
    # берём максимум его собственного поля на сетке при опасной скорости.
    src_results = []
    for p in prepared:
        pr = p["pr"]
        cm = pr["Cm"]
        if len(p["sx"]) > 1:
            ex, ey = _plume_vectors(np.arange(0, 360, _DIR_STEP_COARSE, dtype=float)[None, :])
            own = _source_field(p, px[:, None], py[:, None], ex, ey, pr["Um"])
            cm = float(own.max()) if own.size else cm
        src_results.append({
            "name": p["src"].name,
            "number": getattr(p["src"], "number", None),
            "cm_mg": round(cm, 6),
            "xm": round(pr["Xm"], 1),
            "um": round(pr["Um"], 2),
        })

    return grid_lats, grid_lons, total_mg, src_results, dir_at_max, u_at_max


# ---------------------------------------------------------------------------
# Граница СЗЗ
# ---------------------------------------------------------------------------

def compute_szz_boundary(grid_lats, grid_lons, total_mg, pdk, center_lat, center_lon):
    """
    Определяет границу СЗЗ — точки, где концентрация равна ПДК.
    Возвращает список точек контура [{lat, lon, distance_m, angle_deg}]
    и статистику {max_distance, min_distance, area_ha}.
    """
    n_dirs = 36
    boundary = []

    for i in range(n_dirs):
        angle = i * 10.0
        angle_rad = angle * np.pi / 180.0

        # Вычисляем расстояние от центра до каждой точки сетки в данном направлении
        dx = (grid_lons - center_lon) * 111_000.0 * np.cos(center_lat * np.pi / 180.0)
        dy = (grid_lats - center_lat) * 111_000.0

        # Угол каждой точки от центра
        point_angles = np.arctan2(dx, dy) * 180.0 / np.pi
        point_angles = point_angles % 360

        # Фильтруем точки в секторе ±5° от данного направления
        angle_diff = np.abs(point_angles - angle)
        angle_diff = np.minimum(angle_diff, 360 - angle_diff)
        in_sector = angle_diff < 5.0

        if not np.any(in_sector):
            continue

        distances = np.sqrt(dx ** 2 + dy ** 2)
        sector_distances = distances[in_sector]
        sector_conc = total_mg[in_sector]

        # Находим максимальное расстояние, где концентрация >= ПДК
        exceeds = sector_conc >= pdk
        if np.any(exceeds):
            max_dist = float(sector_distances[exceeds].max())
        else:
            max_dist = 0.0

        # Точка на границе СЗЗ
        dist_deg_lat = max_dist * np.cos(angle_rad) / 111_000.0
        dist_deg_lon = max_dist * np.sin(angle_rad) / (111_000.0 * np.cos(center_lat * np.pi / 180.0))

        boundary.append({
            "lat": round(center_lat + dist_deg_lat, 6),
            "lon": round(center_lon + dist_deg_lon, 6),
            "distance_m": round(max_dist, 1),
            "angle_deg": angle,
        })

    # Статистика
    all_distances = [p["distance_m"] for p in boundary]
    max_distance = max(all_distances) if all_distances else 0
    min_distance = min(d for d in all_distances if d > 0) if any(d > 0 for d in all_distances) else 0

    # Площадь превышения ПДК (приблизительно)
    exceeds_mask = total_mg >= pdk
    n_exceeds = int(exceeds_mask.sum())
    n_total = len(total_mg)
    side = int(np.sqrt(n_total))
    if side > 0:
        grid_step_approx = np.abs(grid_lats[1] - grid_lats[0]) * 111_000.0 if n_total > 1 else 100
        cell_area = grid_step_approx ** 2
        area_m2 = n_exceeds * cell_area
        area_ha = area_m2 / 10_000.0
    else:
        area_ha = 0

    return {
        "boundary": boundary,
        "max_distance_m": round(max_distance, 1),
        "min_distance_m": round(min_distance, 1),
        "area_ha": round(area_ha, 2),
    }


# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Многовеществный расчёт: один источник может выбрасывать N веществ.
# Для каждого вещества — отдельный compute_grid на ОБЩЕЙ сетке (привязка к
# центроиду всех источников проекта), чтобы карты всех веществ совпадали
# и ложились на одну подложку.
# ---------------------------------------------------------------------------

class _SubstanceSourceProxy:
    """Лёгкий прокси: подсовывает compute_grid выброс одного вещества."""

    __slots__ = ("name", "number", "lat", "lon", "height", "diameter", "velocity",
                 "temperature", "_emission_gs", "source_type", "area_length",
                 "area_width", "area_angle", "area_subdivisions", "F")

    def __init__(self, src, emission_gs: float, number: str, F: float = None):
        self.name = src.name
        self.number = number
        self.lat = src.lat
        self.lon = src.lon
        self.height = src.height
        self.diameter = src.diameter
        self.velocity = src.velocity
        self.temperature = src.temperature
        self._emission_gs = emission_gs
        self.F = F or F_GAS
        # Параметры площадного источника — чтобы прокси тоже разворачивался в сетку
        self.source_type = getattr(src, "source_type", "stack")
        self.area_length = getattr(src, "area_length", None)
        self.area_width = getattr(src, "area_width", None)
        self.area_angle = getattr(src, "area_angle", None)
        self.area_subdivisions = getattr(src, "area_subdivisions", None)

    def get_emission_gs(self) -> float:
        return self._emission_gs


def compute_per_substance(sources, meteo, city_data, **grid_kwargs):
    """
    Отдельный расчёт на каждое вещество. Возвращает:
      {
        "by_substance": {code: {substance, pdk, max_c, max_lat, max_lon,
                                exceeds_pdk, ratio_to_pdk, source_results,
                                points: [{lat, lon, c, d, u}], top_points}},
        "primary_code": str,   # вещество с худшим max_c/ПДК
        "lats", "lons": ndarray (общая сетка для всех веществ)
      }
    """
    numbers = [source_number(s, i) for i, s in enumerate(sources)]
    center_lat, center_lon = _grid_center(sources)
    grid_kwargs = dict(grid_kwargs, center_lat=center_lat, center_lon=center_lon)
    frame = _Frame(center_lat, center_lon)
    A_factor = city_data.get("A", 200)

    substance_groups = {}  # code -> {"substance", "pdk", "pairs": [(src, em_gs, number)]}
    for src, number in zip(sources, numbers):
        for entry in src.get_emissions():
            em_gs = entry.get_emission_gs()
            if em_gs <= 0:
                continue
            code = entry.get_substance_code()
            group = substance_groups.setdefault(code, {
                "substance": entry.substance, "pdk": entry.get_pdk(), "pairs": [],
            })
            group["pairs"].append((src, em_gs, number))
            # Разные ПДК у одного вещества — берём самый строгий
            current_pdk = entry.get_pdk()
            if current_pdk and current_pdk < group["pdk"]:
                group["pdk"] = current_pdk

    def build_top_n(proxies, lats_arr, lons_arr, total_mg_arr, dir_arr, u_arr,
                    pdk_value, top_n=10):
        """Top-N точек по убыванию концентрации с вкладами источников (Таблица 13)."""
        if len(total_mg_arr) == 0:
            return []
        n = min(top_n, len(total_mg_arr))
        top_idx = np.argpartition(-total_mg_arr, n - 1)[:n]
        top_idx = top_idx[np.argsort(-total_mg_arr[top_idx])]

        # Вклады источников при опасных направлении и скорости каждой точки
        prepared = _prepare_sources(proxies, meteo.temperature, A_factor, frame)
        x, y = frame.to_xy(lats_arr[top_idx], lons_arr[top_idx])
        contribs = _contributions_at(prepared, x, y, dir_arr[top_idx], u_arr[top_idx])

        # Координаты в метрах от левого-нижнего угла сетки (как X, Y в «Радуге»)
        origin_lat_grid = float(np.min(lats_arr))
        origin_lon_grid = float(np.min(lons_arr))
        kx = 111_000.0 * np.cos(np.radians(origin_lat_grid))

        result = []
        for k, idx in enumerate(top_idx):
            i = int(idx)
            c_mg = float(total_mg_arr[i])
            angle = int(dir_arr[i])
            items = sorted(
                [(p, float(vals[k])) for p, vals in contribs if vals[k] > 0],
                key=lambda pv: -pv[1],
            )
            result.append({
                "qh": (c_mg / pdk_value) if pdk_value > 0 else 0.0,
                "c_mg": c_mg,
                "x_m": int(round((float(lons_arr[i]) - origin_lon_grid) * kx)),
                "y_m": int(round((float(lats_arr[i]) - origin_lat_grid) * 111_000.0)),
                "lat": float(lats_arr[i]),
                "lon": float(lons_arr[i]),
                "wind_dir_deg": angle if angle >= 0 else None,
                "wind_speed_ms": float(u_arr[i]),
                "contributions": [
                    {
                        "src_index": p["index"],
                        "number": p["src"].number,
                        "name": p["src"].name,
                        "contribution_mg": round(v, 9),
                        "contribution_pdk": round(v / pdk_value if pdk_value > 0 else 0.0, 9),
                    }
                    for p, v in items
                ],
            })
        return result

    def substance_result(proxies, sub_dict, pdk_value):
        lats, lons, total_mg, src_results, dir_at_max, u_at_max = compute_grid(
            sources=proxies, meteo=meteo, city_data=city_data, **grid_kwargs,
        )
        max_idx = int(total_mg.argmax()) if len(total_mg) else 0
        max_c = float(total_mg[max_idx]) if len(total_mg) else 0.0
        return lats, lons, {
            "substance": sub_dict,
            "pdk": pdk_value,
            "max_c": max_c,
            "max_lat": float(lats[max_idx]) if len(lats) else 0.0,
            "max_lon": float(lons[max_idx]) if len(lons) else 0.0,
            "exceeds_pdk": bool(max_c > pdk_value),
            "ratio_to_pdk": (max_c / pdk_value) if pdk_value > 0 else 0.0,
            "source_results": src_results,
            "points": [
                {"lat": float(lats[i]), "lon": float(lons[i]), "c": float(total_mg[i]),
                 "d": int(dir_at_max[i]), "u": float(u_at_max[i])}
                for i in range(len(lats))
            ],
            "top_points": build_top_n(proxies, lats, lons, total_mg, dir_at_max,
                                      u_at_max, pdk_value),
        }

    # Ничего не задано — один общий расчёт по суммарному выбросу (старое поведение)
    if not substance_groups:
        proxies = [_SubstanceSourceProxy(s, s.get_emission_gs(), n)
                   for s, n in zip(sources, numbers)]
        lats, lons, data = substance_result(proxies, None, 0.5)
        return {"by_substance": {"unknown": data}, "primary_code": "unknown",
                "lats": lats, "lons": lons}

    by_substance = {}
    common_lats = common_lons = None
    for code, group in substance_groups.items():
        sub_meta = group["substance"]
        F = getattr(sub_meta, "F", None) if sub_meta is not None else None
        proxies = [_SubstanceSourceProxy(src, em_gs, number, F)
                   for src, em_gs, number in group["pairs"]]
        sub_dict = None
        if sub_meta is not None:
            sub_dict = {
                "code": sub_meta.code,
                "name": sub_meta.name,
                "pdk_mr": sub_meta.pdk_mr,
                "pdk_ss": sub_meta.pdk_ss,
                "hazard_class": sub_meta.hazard_class,
                "F": F,
            }
        pdk_value = float(group["pdk"]) if group["pdk"] else 0.5
        lats, lons, data = substance_result(proxies, sub_dict, pdk_value)
        if common_lats is None:
            common_lats, common_lons = lats, lons
        by_substance[code] = data

    primary_code = max(by_substance.keys(), key=lambda k: by_substance[k]["ratio_to_pdk"])
    return {
        "by_substance": by_substance,
        "primary_code": primary_code,
        "lats": common_lats,
        "lons": common_lons,
    }
