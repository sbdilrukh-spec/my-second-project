"""
Быстрое ядро поиска максимума концентрации по направлениям и скоростям ветра
(numba). Формулы те же, что в ond86._source_field: (2.23)–(2.24) s1,
(2.28) s2, (2.29)–(2.30) r и p. Если numba недоступна, ond86 считает тем же
перебором на numpy (медленнее).

Порядок поиска в каждой точке:
  1) грубо: направления через 10° × все скорости из списка;
  2) направление уточняется с шагом 1° (±9°) при всех скоростях;
  3) скорость уточняется с шагом 0,1 м/с (±0,4) при найденном направлении.
"""

import math
import numpy as np

try:
    from numba import njit, prange
    HAVE_NUMBA = True
except ImportError:  # pragma: no cover
    HAVE_NUMBA = False


if HAVE_NUMBA:

    @njit(cache=True, inline="always")
    def _r(q):
        if q <= 1.0:
            return 0.67 * q + 1.67 * q * q - 1.34 * q * q * q
        return 3.0 * q / (2.0 * q * q - q + 2.0)

    @njit(cache=True, inline="always")
    def _p(q):
        if q <= 0.25:
            return 3.0
        if q <= 1.0:
            return 8.43 * (1.0 - q) ** 5 + 1.0
        return 0.32 * q + 0.68

    @njit(cache=True, inline="always")
    def _s1(t, F, H):
        if t <= 0.0:
            return 0.0
        if t <= 1.0:
            s = 3.0 * t ** 4 - 8.0 * t ** 3 + 6.0 * t ** 2
            if H < 10.0:
                h = H if H > 2.0 else 2.0
                s = 0.125 * (10.0 - h) + 0.125 * (h - 2.0) * s
            return s
        if t <= 8.0:
            return 1.13 / (0.13 * t * t + 1.0)
        if F <= 1.5:
            return t / (3.58 * t * t - 35.2 * t + 120.0)
        return 1.0 / (0.1 * t * t + 2.47 * t - 17.8)

    @njit(cache=True)
    def _conc(x, y, theta_deg, u, SX, SY, CMU, XMU, FS, HS):
        """Суммарная концентрация в точке при направлении theta и скорости u."""
        th = theta_deg * math.pi / 180.0
        ex = -math.sin(th)
        ey = -math.cos(th)
        k = u if u < 5.0 else 5.0
        total = 0.0
        for s in range(SX.size):
            dx = x - SX[s]
            dy = y - SY[s]
            xa = dx * ex + dy * ey
            if xa <= 0.0:
                continue
            ya = dx * ey - dy * ex
            ty = k * ya * ya / (xa * xa)
            if ty > 50.0:          # s2 < 1e-12 — вклад пренебрежимо мал
                continue
            s2 = 1.0 / (1.0 + 5.0 * ty + 12.8 * ty ** 2 + 17.0 * ty ** 3 + 45.1 * ty ** 4) ** 2
            total += CMU[s] * _s1(xa / XMU[s], FS[s], HS[s]) * s2
        return total

    @njit(cache=True)
    def _params_at(u, CMW, XM, UM, CMU, XMU):
        for s in range(CMW.size):
            q = u / UM[s]
            CMU[s] = _r(q) * CMW[s]
            XMU[s] = _p(q) * XM[s]

    @njit(cache=True, parallel=True)
    def max_field(px, py, SX, SY, CMW, XM, UM, FS, HS, speeds, u_star,
                  coarse_dirs, refine_half):
        npt = px.size
        ns = SX.size
        nu = speeds.size
        best = np.zeros(npt)
        bdir = np.full(npt, -1.0)
        bu = np.zeros(npt)

        CMU_all = np.empty((nu, ns))
        XMU_all = np.empty((nu, ns))
        for iu in range(nu):
            _params_at(speeds[iu], CMW, XM, UM, CMU_all[iu], XMU_all[iu])

        for i in prange(npt):
            x = px[i]
            y = py[i]
            b = 0.0
            bd = -1.0
            bv = 0.0
            # 1) грубый перебор направлений × скорости
            for d in coarse_dirs:
                for iu in range(nu):
                    c = _conc(x, y, d, speeds[iu], SX, SY, CMU_all[iu], XMU_all[iu], FS, HS)
                    if c > b:
                        b = c
                        bd = d
                        bv = speeds[iu]
            if b <= 0.0:
                continue
            # 2) уточнение направления с шагом 1°
            if coarse_dirs.size > 1:
                d0 = bd
                for off in range(-refine_half, refine_half + 1):
                    d = (d0 + off) % 360.0
                    for iu in range(nu):
                        c = _conc(x, y, d, speeds[iu], SX, SY, CMU_all[iu], XMU_all[iu], FS, HS)
                        if c > b:
                            b = c
                            bd = d
                            bv = speeds[iu]
            # 3) уточнение скорости с шагом 0,1 м/с
            CMU = np.empty(ns)
            XMU = np.empty(ns)
            u0 = bv
            for j in range(-4, 5):
                u = round((u0 + 0.1 * j) * 10.0) / 10.0
                if j == 0 or u < 0.5 or u > u_star:
                    continue
                _params_at(u, CMW, XM, UM, CMU, XMU)
                c = _conc(x, y, bd, u, SX, SY, CMU, XMU, FS, HS)
                if c > b:
                    b = c
                    bv = u
            best[i] = b
            bdir[i] = bd
            bu[i] = bv
        return best, bdir, bu
