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

def compute_grid(sources, meteo, city_data: dict, grid_radius: float, grid_step: float):
    """
    Рассчитывает приземные концентрации на регулярной сетке.

    Возвращает:
        lats      np.ndarray  — широты точек сетки
        lons      np.ndarray  — долготы точек сетки
        total_mg  np.ndarray  — суммарная концентрация, мг/м³
        src_results list[dict]
    """
    A = city_data.get("A", 200)
    sigma_coeff = STABILITY_SIGMA.get(meteo.stability_class, 0.08)
    wd_rad = meteo.wind_direction * np.pi / 180.0

    # ---------- Построение сетки ----------
    # Центр сетки — первый источник (или центроид)
    center_lat = sum(s.lat for s in sources) / len(sources)
    center_lon = sum(s.lon for s in sources) / len(sources)

    n_steps = int(grid_radius / grid_step)
    offsets = np.arange(-n_steps, n_steps + 1) * grid_step   # [м]

    # Восток/Север offset meshgrid
    dx_e_2d, dy_n_2d = np.meshgrid(offsets, offsets)   # shape (N, N)

    lat_rad_center = center_lat * np.pi / 180.0
    grid_lats = (center_lat + dy_n_2d / 111_000.0).flatten()
    grid_lons = (center_lon + dx_e_2d / (111_000.0 * np.cos(lat_rad_center))).flatten()

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
            Ta=meteo.temperature,
            A=A,
        )

        Cm = params["Cm"]
        Xm = params["Xm"]

        src_results.append({
            "name": src.name,
            "cm_mg": round(Cm * 1000.0, 6),   # г/м³ → мг/м³
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

    total_mg = total_c * 1000.0   # г/м³ → мг/м³
    return grid_lats, grid_lons, total_mg, src_results
