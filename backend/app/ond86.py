"""
Расчёт рассеивания загрязняющих веществ в атмосфере по методике ОНД-86.
(Общесоюзный нормативный документ — Приказ МПР №273)

Основные формулы: Берлянд М.Е., 1975 / ОНД-86 раздел 2.
"""

import numpy as np
from .meteo_data import STABILITY_SIGMA

# Коэффициент оседания — F=1 для газов и мелкодисперсных частиц (<10 мкм)
F_GAS = 1.0


# ---------------------------------------------------------------------------
# Вспомогательные функции s1, s2
# ---------------------------------------------------------------------------

def _s1_vectorized(r: np.ndarray) -> np.ndarray:
    """
    Нормированная функция осевой концентрации.
    r = x / Xm   (отношение расстояния к расстоянию максимума)
    Возвращает значения [0, 1]: при r=1 возвращает 1.
    """
    s = np.where(
        r <= 0,
        0.0,
        np.where(
            r <= 1.0,
            3.0 * r ** 4 / (1.0 + 2.0 * r ** 4),
            3.0 / (r ** 4 + 2.0),
        ),
    )
    return s


def _s2_vectorized(y: np.ndarray, x: np.ndarray, sigma_coeff: float) -> np.ndarray:
    """
    Нормированное распределение концентрации по перпендикуляру к ветру.
    Гауссово приближение (ОНД-86, п. 2.16).
    sigma_coeff = tan(β) — зависит от класса устойчивости.
    """
    sigma_y = np.maximum(np.abs(x) * sigma_coeff, 0.5)
    return np.exp(-0.5 * (y / sigma_y) ** 2)


# ---------------------------------------------------------------------------
# Расчёт параметров одного источника (Cm, Xm)
# ---------------------------------------------------------------------------

def calc_source_params(
    M: float,   # г/с
    H: float,   # м
    D: float,   # м
    w0: float,  # м/с
    Tg: float,  # °C
    Ta: float,  # °C
    A: float,   # климатический коэффициент
    F: float = F_GAS,
    eta: float = 1.0,  # коэффициент рельефа
) -> dict:
    """
    Вычисляет Cm (г/м³) и Xm (м) по ОНД-86.
    """
    dT = Tg - Ta
    V1 = np.pi / 4.0 * D ** 2 * w0   # объёмный расход, м³/с

    if dT < 0.5 or V1 < 1e-4:
        return _cold_source(M, H, D, w0, A, F, eta)

    # --- Горячий источник ---
    f = 1000.0 * w0 ** 2 * D / (H ** 2 * dT)
    vm = 0.65 * (V1 * dT / H) ** (1.0 / 3.0)
    vm_prime = 1.3 * w0 * D / H

    # Коэффициент m
    if f < 100:
        m = 1.0 / (0.67 + 0.1 * f ** 0.5 + 0.34 * f ** (1.0 / 3.0))
    else:
        fe = 800.0 * (w0 / (w0 + 3.0)) ** 3
        m = 1.47 / (1.0 + 0.28 * fe ** (1.0 / 3.0))

    # Коэффициент n
    if vm >= 2.0:
        n = 1.0
    elif vm >= 0.5:
        n = 0.532 * vm ** 2 - 2.13 * vm + 3.13
    else:
        n = 4.4 * vm

    # Максимальная приземная концентрация (г/м³)
    Cm = A * M * F * m * n * eta / (H ** 2 * (V1 * dT) ** (1.0 / 3.0))

    # Расстояние до максимума (м)
    if f < 100:
        vm_use = vm
    else:
        vm_use = vm_prime

    if vm_use >= 2.0:
        d = 7.0 * (1.0 + 0.28 * f ** (1.0 / 3.0))
    elif vm_use >= 0.5:
        d = 4.95 * vm_use * (1.0 + 0.28 * f ** (1.0 / 3.0))
    else:
        d = 5.0 * F

    Xm = d * H

    return {
        "Cm": float(Cm),
        "Xm": float(Xm),
        "type": "hot",
        "f": float(f),
        "vm": float(vm),
        "m": float(m),
        "n": float(n),
        "V1": float(V1),
        "dT": float(dT),
    }


def _cold_source(M, H, D, w0, A, F, eta) -> dict:
    """Холодный источник (ΔТ ≈ 0) — ОНД-86, п. 2.6."""
    V1 = np.pi / 4.0 * D ** 2 * w0
    vm_prime = 1.3 * w0 * D / H
    fe = 800.0 * (w0 / (w0 + 3.0)) ** 3
    m = 1.47 / (1.0 + 0.28 * fe ** (1.0 / 3.0))

    if vm_prime >= 2.0:
        n = 1.0
        d = 14.0 * (1.0 + 0.28 * fe ** (1.0 / 3.0))
    elif vm_prime >= 0.5:
        n = 0.532 * vm_prime ** 2 - 2.13 * vm_prime + 3.13
        d = 9.9 * vm_prime * (1.0 + 0.28 * fe ** (1.0 / 3.0))
    else:
        n = 4.4 * vm_prime
        d = 5.6 * F

    Cm = A * M * F * m * n * eta / (H ** 2 * max(V1, 1e-6) ** (2.0 / 3.0))
    Xm = d * H

    return {
        "Cm": float(Cm),
        "Xm": float(Xm),
        "type": "cold",
        "vm_prime": float(vm_prime),
        "m": float(m),
        "n": float(n),
        "V1": float(V1),
    }


# ---------------------------------------------------------------------------
# Расчёт поля концентраций на сетке (векторизованный)
# ---------------------------------------------------------------------------

def _compute_single_direction(sources, sigma_coeff, A, Ta, wd_rad, grid_lats, grid_lons):
    """
    Рассчитывает поле концентраций для одного направления ветра.
    Возвращает total_c (г/м³) и src_results.
    """
    total_c = np.zeros(len(grid_lats))
    src_results = []

    for src in sources:
        M = src.get_emission_gs()
        if M <= 0:
            continue

        params = calc_source_params(
            M=M,
            H=src.height,
            D=src.diameter,
            w0=src.velocity,
            Tg=src.temperature,
            Ta=Ta,
            A=A,
        )

        Cm = params["Cm"]
        Xm = params["Xm"]

        src_results.append({
            "name": src.name,
            "cm_mg": round(Cm, 6),   # формула ОНД-86 уже даёт мг/м³
            "xm": round(Xm, 1),
        })

        if Cm <= 0 or Xm <= 0:
            continue

        # Перемещение от источника до каждой точки сетки (метры, Восток/Север)
        src_lat_rad = src.lat * np.pi / 180.0
        dx_e = (grid_lons - src.lon) * 111_000.0 * np.cos(src_lat_rad)
        dy_n = (grid_lats - src.lat) * 111_000.0

        # Поворот в систему «по ветру»
        # Ветер дует ОТ направления wind_direction → факел идёт В сторону wind_direction+180°
        x_wind = -(dx_e * np.sin(wd_rad) + dy_n * np.cos(wd_rad))
        y_wind = dx_e * np.cos(wd_rad) - dy_n * np.sin(wd_rad)

        # Концентрации (только подветренная сторона: x_wind > 0)
        r = np.where(x_wind > 0, x_wind / Xm, 0.0)
        s1_vals = _s1_vectorized(r)
        s2_vals = np.where(
            x_wind > 0,
            _s2_vectorized(y_wind, x_wind, sigma_coeff),
            0.0,
        )
        total_c += Cm * s1_vals * s2_vals

    return total_c, src_results


def compute_grid(sources, meteo, city_data: dict,
                  grid_radius: float = None, grid_step: float = 500,
                  x_length: float = None, y_length: float = None,
                  source_offset_x: float = None, source_offset_y: float = None):
    """
    Рассчитывает приземные концентрации на регулярной сетке.

    Новая система координат: начало (0,0) в нижнем левом углу.
    Источник расположен в (source_offset_x, source_offset_y).

    Режимы:
        wind_mode="360"    — 36 направлений (шаг 10°), MAX в каждой точке (ОВОС)
        wind_mode="single" — одно направление ветра

    Возвращает:
        lats      np.ndarray  — широты точек сетки
        lons      np.ndarray  — долготы точек сетки
        total_mg  np.ndarray  — суммарная концентрация, мг/м³
        src_results list[dict]
    """
    A = city_data.get("A", 200)
    sigma_coeff = STABILITY_SIGMA.get(meteo.stability_class, 0.08)
    wind_mode = getattr(meteo, "wind_mode", "360")

    # ---------- Построение сетки ----------
    center_lat = sum(s.lat for s in sources) / len(sources)
    center_lon = sum(s.lon for s in sources) / len(sources)

    # Обратная совместимость: если передан radius, конвертируем в x_length/y_length
    if x_length is None and grid_radius is not None:
        x_length = grid_radius * 2
        y_length = grid_radius * 2
        source_offset_x = grid_radius
        source_offset_y = grid_radius
    elif x_length is None:
        x_length = 7000
        y_length = 7000
        source_offset_x = 3500
        source_offset_y = 3500

    if y_length is None:
        y_length = x_length
    if source_offset_x is None:
        source_offset_x = x_length / 2
    if source_offset_y is None:
        source_offset_y = y_length / 2

    lat_rad_center = center_lat * np.pi / 180.0

    # Начало координат (нижний левый угол) в географических координатах
    origin_lat = center_lat - source_offset_y / 111_000.0
    origin_lon = center_lon - source_offset_x / (111_000.0 * np.cos(lat_rad_center))

    # Сетка от 0 до x_length / y_length
    n_x = int(x_length / grid_step) + 1
    n_y = int(y_length / grid_step) + 1
    x_offsets = np.arange(n_x) * grid_step  # [0, step, 2*step, ..., x_length]
    y_offsets = np.arange(n_y) * grid_step  # [0, step, 2*step, ..., y_length]

    dx_e_2d, dy_n_2d = np.meshgrid(x_offsets, y_offsets)

    grid_lats = (origin_lat + dy_n_2d / 111_000.0).flatten()
    grid_lons = (origin_lon + dx_e_2d / (111_000.0 * np.cos(lat_rad_center))).flatten()

    if wind_mode == "360":
        # ---------- Полный обзор 360° ----------
        # 36 направлений с шагом 10°, в каждой точке берём МАКСИМУМ
        total_c_max = np.zeros(len(grid_lats))
        src_results = None

        for angle_deg in range(0, 360, 10):
            wd_rad = angle_deg * np.pi / 180.0
            c_dir, sr = _compute_single_direction(
                sources, sigma_coeff, A, meteo.temperature, wd_rad,
                grid_lats, grid_lons,
            )
            total_c_max = np.maximum(total_c_max, c_dir)
            if src_results is None:
                src_results = sr  # параметры Cm/Xm не зависят от направления

        total_mg = total_c_max  # формула ОНД-86 уже даёт мг/м³
    else:
        # ---------- Одно направление ----------
        wd_rad = meteo.wind_direction * np.pi / 180.0
        total_c, src_results = _compute_single_direction(
            sources, sigma_coeff, A, meteo.temperature, wd_rad,
            grid_lats, grid_lons,
        )
        total_mg = total_c  # формула ОНД-86 уже даёт мг/м³

    if src_results is None:
        src_results = []

    return grid_lats, grid_lons, total_mg, src_results


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
# Многовеществный расчёт: один источник может выбрасывать N веществ.
# Для каждого уникального вещества прогоняется отдельный compute_grid с
# правильным emission_gs, и результаты собираются в словарь.
# ---------------------------------------------------------------------------

class _SubstanceSourceProxy:
    """Лёгкий прокси: подсовывает compute_grid `get_emission_gs()` от одного вещества."""

    __slots__ = ("name", "lat", "lon", "height", "diameter", "velocity",
                 "temperature", "_emission_gs")

    def __init__(self, src, emission_gs: float, name: str = None):
        self.name = name or src.name
        self.lat = src.lat
        self.lon = src.lon
        self.height = src.height
        self.diameter = src.diameter
        self.velocity = src.velocity
        self.temperature = src.temperature
        self._emission_gs = emission_gs

    def get_emission_gs(self) -> float:
        return self._emission_gs


def compute_per_substance(sources, meteo, city_data, **grid_kwargs):
    """
    Делает по отдельному расчёту на каждое вещество.
    Возвращает dict со структурой:

      {
        "by_substance": {
          "<code>": {
            "substance": {code, name, pdk_mr, hazard_class},
            "pdk": float,
            "max_c": float,
            "max_lat": float,
            "max_lon": float,
            "exceeds_pdk": bool,
            "ratio_to_pdk": float,
            "source_results": [...],   # Cm/Xm на это вещество
            "points": [{lat, lon, c}, ...],
          },
          ...
        },
        "primary_code": str,    # код вещества с худшим max_c/pdk
        "lats": ndarray,        # общая сетка (одинаковая у всех веществ)
        "lons": ndarray,
      }
    """
    # Собираем все (источник, выброс) пары, группируем по коду вещества
    substance_groups = {}  # code -> {"substance": meta, "pairs": [(src, emission_gs)]}
    for src in sources:
        for entry in src.get_emissions():
            em_gs = entry.get_emission_gs()
            if em_gs <= 0:
                continue
            code = entry.get_substance_code()
            if code not in substance_groups:
                substance_groups[code] = {
                    "substance": entry.substance,
                    "pdk": entry.get_pdk(),
                    "pairs": [],
                }
            substance_groups[code]["pairs"].append((src, em_gs))
            # Если ПДК на разных строках одного вещества разные —
            # берём минимальный (самый строгий)
            current_pdk = entry.get_pdk()
            if current_pdk and current_pdk < substance_groups[code]["pdk"]:
                substance_groups[code]["pdk"] = current_pdk

    # Если ничего не задано — fallback к старой логике (один общий расчёт)
    if not substance_groups:
        lats, lons, total_mg, src_results = compute_grid(
            sources=sources, meteo=meteo, city_data=city_data, **grid_kwargs,
        )
        max_idx = int(total_mg.argmax()) if len(total_mg) else 0
        max_c = float(total_mg[max_idx]) if len(total_mg) else 0.0
        return {
            "by_substance": {
                "unknown": {
                    "substance": None,
                    "pdk": 0.5,
                    "max_c": max_c,
                    "max_lat": float(lats[max_idx]) if len(lats) else 0.0,
                    "max_lon": float(lons[max_idx]) if len(lons) else 0.0,
                    "exceeds_pdk": max_c > 0.5,
                    "ratio_to_pdk": max_c / 0.5 if max_c > 0 else 0.0,
                    "source_results": src_results,
                    "points": [
                        {"lat": float(lats[i]), "lon": float(lons[i]), "c": float(total_mg[i])}
                        for i in range(len(lats))
                    ],
                }
            },
            "primary_code": "unknown",
            "lats": lats,
            "lons": lons,
        }

    by_substance = {}
    common_lats = None
    common_lons = None

    for code, group in substance_groups.items():
        proxies = [_SubstanceSourceProxy(src, em_gs) for src, em_gs in group["pairs"]]
        lats, lons, total_mg, src_results = compute_grid(
            sources=proxies, meteo=meteo, city_data=city_data, **grid_kwargs,
        )
        if common_lats is None:
            common_lats = lats
            common_lons = lons

        max_idx = int(total_mg.argmax()) if len(total_mg) else 0
        max_c = float(total_mg[max_idx]) if len(total_mg) else 0.0
        pdk_value = float(group["pdk"]) if group["pdk"] else 0.5

        # Готовим метаданные вещества
        sub_meta = group["substance"]
        sub_dict = None
        if sub_meta is not None:
            sub_dict = {
                "code": sub_meta.code,
                "name": sub_meta.name,
                "pdk_mr": sub_meta.pdk_mr,
                "pdk_ss": sub_meta.pdk_ss,
                "hazard_class": sub_meta.hazard_class,
            }

        by_substance[code] = {
            "substance": sub_dict,
            "pdk": pdk_value,
            "max_c": max_c,
            "max_lat": float(lats[max_idx]) if len(lats) else 0.0,
            "max_lon": float(lons[max_idx]) if len(lons) else 0.0,
            "exceeds_pdk": bool(max_c > pdk_value),
            "ratio_to_pdk": (max_c / pdk_value) if pdk_value > 0 else 0.0,
            "source_results": src_results,
            "points": [
                {"lat": float(lats[i]), "lon": float(lons[i]), "c": float(total_mg[i])}
                for i in range(len(lats))
            ],
        }

    # Главное вещество — с наибольшим отношением max_c / pdk
    primary_code = max(by_substance.keys(),
                       key=lambda k: by_substance[k]["ratio_to_pdk"])

    return {
        "by_substance": by_substance,
        "primary_code": primary_code,
        "lats": common_lats,
        "lons": common_lons,
    }
