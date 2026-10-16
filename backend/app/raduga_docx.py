"""
Таблицы расчёта рассеивания в формате распечатки «Радуги» (Word, .docx):
1 — исходные данные, 7 — параметры источников, 8 — характеристика выбросов,
12 — характеристики поля концентраций, 13 — наибольшие концентрации.

Текст моноширинный (Courier New), строки сверены с распечатками «Радуги»
символ в символ. Координаты X, Y — метры от левого-нижнего угла расчётной
сетки (как в таблицах 12/13). Направление ветра HB — как в «Радуге»: угол
направления, КУДА дует ветер, от оси OX против часовой стрелки; из
метеорологического θ (откуда дует, от севера по часовой) HB = 270° − θ.
"""

import io
import math

from docx import Document
from lxml import etree
from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .ond86 import source_number

FONT = "Courier New"
FONT_SIZE = 7          # пт: строка таблицы 8 «Радуги» — 116 символов
LINE_PITCH = 8         # пт, точный межстрочный интервал
T7_ROWS_PER_PAGE = 45
T12_COLS = 6           # точек по X в одном блоке таблицы 12
T12_ROWS = 21          # строк Y на странице таблицы 12 (21 строка = сетка 10 км / 500 м)

SEP_T1 = "-" * 62
SEP_T7 = "-" * 116
SEP_T8 = "-" * 116
SEP_T8_IN = ":" + "-" * 115
SEP_T12 = "-" * 80
SEP_T13 = "-" * 111
SEP_T13_END = "-" * 110


# ---------------------------------------------------------------------------
# Числа в стиле «Радуги»
# ---------------------------------------------------------------------------

def _qh12(v: float) -> str:
    """QH в ячейке таблицы 12: 11 знаков (0.000084988 / 0.0013106)."""
    if v < 0.001:
        return f"{v:.9f}"
    return f"{v:.5g}" if v < 1e5 else f"{v:.0f}"


def _qh13(v: float) -> str:
    """QH в таблице 13: 0.001753 или 0.000520762 (меньше 0,001)."""
    return f"{v:.9f}" if v < 0.001 else f"{v:.6f}"


def _hb(theta_met) -> int:
    """Метеорологическое направление (откуда дует) → HB «Радуги»."""
    if theta_met is None or theta_met < 0:
        return 0
    return int(round(270.0 - float(theta_met))) % 360


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Геометрия: метры от левого-нижнего угла сетки
# ---------------------------------------------------------------------------

class _GridXY:
    def __init__(self, points, step):
        lats = [p["lat"] for p in points]
        lons = [p["lon"] for p in points]
        self.lat0 = min(lats)
        self.lon0 = min(lons)
        self.kx = 111_000.0 * math.cos(math.radians(self.lat0))
        self.step = step or 0

    def xy(self, lat, lon):
        return (_f(lon) - self.lon0) * self.kx, (_f(lat) - self.lat0) * 111_000.0

    def node(self, lat, lon):
        """Координаты узла сетки, округлённые к шагу."""
        x, y = self.xy(lat, lon)
        if self.step:
            x = round(x / self.step) * self.step
            y = round(y / self.step) * self.step
        return int(round(x)), int(round(y))


# ---------------------------------------------------------------------------
# Блоки таблиц (списки строк)
# ---------------------------------------------------------------------------

def _table1(obj, n_src, n_sub, temperature, coef_a, u_star):
    return [
        "      ИСХОДНЫЕ  ДАННЫЕ",
        "",
        "    Метеорологические характеристики и коэффициенты,",
        "    определяющие условия рассеивания загрязняющих",
        "             веществ в атмосфере",
        f"Oбъект:    {obj}",
        " " * 52 + "Таблица 1",
        SEP_T1,
        f": Число источников                                   :{n_src:6d} :",
        f": Число рассматриваемых вредных веществ              :{n_sub:6d} :",
        ": Число групп суммирования                           :     0 :",
        f": Средняя максимальная температура наружного воздуха :{temperature:6.1f} :",
        f": Коэффициент, зависящий от стратификации атмосферы  :{coef_a:6g} :",
        f": Скорость ветра повторяемость превышения которой    :{u_star:6g} :",
        ": составляет 5 процентов (м/с)                       :       :",
        SEP_T1,
    ]


_T7_HEAD = [
    ":       :      :ДИАМЕТР  :ПАРАМЕТРЫ ГАЗОВОЗДУШНОЙ СМЕСИ :       К О О Р Д И Н А ТЫ           :УГОЛ МЕЖДУ  :        :",
    ":  КОД  :ВЫСОТА:ТОЧЕЧНОГО:-------------------------------------------------------------------: ОСЬЮ ОХ И  :  УЧЕТ  :",
    ":       :      :ИЛИ ШИРИ-:         :           :        :ТОЧЕЧНОГО,НАЧАЛО  : КОНЕЦ ЛИНЕЙНОГО : НАПРАВЛЕНИЯ:РЕЛЬЕФА :",
    ":       :      :НА ПЛОС- :СКОРОСТЬ :   ОБЪЕМ   :ТЕМПЕРА-:ЛИHЕЙНОГО ИЛИ ЛИНИ:ИЛИ ЛИНИИ ЦЕНТРА :НА СЕВЕР    :        :",
    ":       :      :КОСТНОГО :         :           : ТУРА   :И ЦЕНТРА ПЛОСКОСТ.:   ПЛОСКОСТНОГО  :            :        :",
    SEP_T7,
    ": Н ИСТ.: Н(М) :   Д     : W(М/С)  : V(М,КУБ/С):    Т   :  X1(M)  :  Y1(M) :  X2(M) :  Y2(M) :  С(ГРАД)   :   РН   :",
    SEP_T7,
]


def _table7_pages(obj, rows):
    pages = []
    for page_no, start in enumerate(range(0, max(len(rows), 1), T7_ROWS_PER_PAGE), 1):
        lines = [
            "      ПАРАМЕТРЫ ИСТОЧНИКОВ",
            "",
            f"Объект:     {obj}",
            " " * 99 + f"ТАБЛИЦА 7 СТРАНИЦА {page_no:2d}",
            SEP_T7,
        ] + _T7_HEAD + rows[start:start + T7_ROWS_PER_PAGE] + [SEP_T7]
        pages.append(lines)
    return pages


def _t7_row(num, H, D, w, V, T, x1, y1, x2, y2):
    x2s = f"{x2:8d}" if x2 is not None else "       -"
    y2s = f"{y2:9d}" if y2 is not None else "        -"
    return (":" + f"{num:>7s}{H:7.1f}{D:9.2f}{w:11.4f}{V:12.4f}{T:9.1f}{x1:10d}{y1:9d}"
            + x2s + y2s + f"{90:12d}{1.0:9.2f} :")


_T8_SUB_HEAD = ":КОД ВЕЩ-ВА:НАИМЕНОВАНИЕ(ШИФР) ВЕЩ-ВА:ПДК(MГ/М,КУБ):КОЕФ.ОСЕДАНИЯ: ЧИСЛО ИСТОЧНИКОВ:      Т.ГОД      :    Г/С      :"
_T8_EM_HEAD = [
    ":           В ы б р о с ы             :           В ы б р о с ы             :           В ы б р о с ы              :",
    ": Н ИСТ :  г/с    : мг/куб.м.: т/год  : Н ИСТ :  г/с    : мг/куб.м.: т/год  : Н ИСТ :  г/с    : мг/куб.м.: т/год   :",
]


def _table8(obj, subs):
    lines = [
        "  ХАРАКТЕРИСТИКА ВЫБРОСОВ",
        "",
        f"ОБЬЕКТ:    {obj}",
        " " * 76 + "ТАБЛИЦА 8  СТРАНИЦА  1",
        SEP_T8,
    ]
    for s in subs:
        name = (s["name"] or "")[:26]
        lines += [
            _T8_SUB_HEAD,
            SEP_T8_IN,
            (":" + f"{s['code']:>6s}      {name:<26s}{s['pdk']:8.6f}{s['F']:12.1f}"
             + f"{len(s['entries']):14d}{s['ty']:24.4f}    :{s['gs']:13.6f}:"),
            ":" + " " * 31,
            SEP_T8_IN,
        ] + _T8_EM_HEAD + [SEP_T8]
        for i in range(0, len(s["entries"]), 3):
            row = ""
            for e in s["entries"][i:i + 3]:
                mg = f"{e['mg']:11.1f}" if e["mg"] is not None else "          -"
                row += f"{e['num']:>7s}{e['gs']:11.6f}{mg}{e['ty']:9.4f}"
            lines.append(row)
        lines.append(SEP_T8)
    return lines


_T12_LEGEND = [
    "       ХАРАКТЕРИСТИКИ  ПОЛЯ КОНЦЕНТРАЦИЙ",
    "",
    "                                     Выбор опасного направления ветра",
    "                                     Выбор опасной скорости ветра из скоростей: aвтоматический",
    "                                     Без фона",
    "      Условные  обозначения:",
    "(X,Y) -координаты точек в метрах",
    "QH -концентрация в точке долях ПДК",
    "HB -направление ветра в град.",
    "U - скорость ветра м/с",
]


def _table12_pages(obj, sub_name, grid):
    """
    grid: {(x, y): (qh, hb, u)} → страницы: по T12_COLS точек по X и по
    T12_ROWS строк Y на страницу (иначе блок не помещается на лист A4).
    """
    xs = sorted({k[0] for k in grid})
    ys = sorted({k[1] for k in grid}, reverse=True)
    # Строки Y делим между страницами поровну: 21 строка → 11 + 10, а не
    # 19 + 2 (страница из двух строк выглядит как недозаполненная таблица).
    n_pages_y = max(1, math.ceil(len(ys) / T12_ROWS))
    rows_per_page = math.ceil(len(ys) / n_pages_y) if ys else T12_ROWS
    pages = []
    page_no = 0
    for xs_start in range(0, len(xs), T12_COLS):
        chunk = xs[xs_start:xs_start + T12_COLS]
        for ys_start in range(0, len(ys), rows_per_page):
            page_no += 1
            lines = list(_T12_LEGEND) + [
                f"Объект:    {obj}",
                f"           вещество: {sub_name}".ljust(95) + f"Таблица 12 Cтраница {page_no:2d}",
                SEP_T12,
            ]
            for y in ys[ys_start:ys_start + rows_per_page]:
                qh_cells = hb_cells = ""
                for x in chunk:
                    qh, hb, u = grid.get((x, y), (0.0, 0, 0.0))
                    qh_cells += f"{_qh12(qh):>11s}:"
                    hb_cells += f"{hb:4d}-{u:4.1f}  :"
                lines += [
                    f":Y={y:7d}" + "".join(f" X={x:7d}  " for x in chunk),
                    ":   QH :" + qh_cells,
                    ": HB-U :" + hb_cells,
                    SEP_T12,
                ]
            pages.append(lines)
    return pages


def _table13(obj, sub_name, top_rows, qmin, qmax):
    lines = [
        "          НАИБОЛЬШИЕ  КОНЦЕНТРАЦИИ",
        "(X,Y) - координаты точки",
        "QH -концентрация в точке долях ПДК",
        "HB -направление ветра в град.",
        "U - скорость ветра м/с",
        f"Объект:    {obj}",
        f" вещество:{sub_name}".ljust(83) + "Таблица 13 Cтраница  1",
        SEP_T13,
        ":   QH     :    X   :   Y   :  HB :   U  :Но.Источ: вклад :Но.Источ: Вклад :Но.Источ: Вклад :Но.Источ : Вклад :",
        SEP_T13,
    ]
    for r in top_rows:
        head = f":{_qh13(r['qh']):>11s}{r['x']:8d}{r['y']:8d}{r['hb']:5d}{r['u']:6.1f}"
        contribs = r["contribs"]
        first = contribs[:4]
        lines.append(head + "".join(f"{n:>7s}{v:11.6f}" for n, v in first) + " ")
        # Источников больше четырёх — продолжаем под колонками вкладов
        for i in range(4, len(contribs), 4):
            lines.append(" " * len(head) + "".join(f"{n:>7s}{v:11.6f}" for n, v in contribs[i:i + 4]))
    lines += [
        SEP_T13_END,
        f"Минимальная и максимальная концентрации в точках расчетов:{qmin:15.10f}{qmax:15.10f}",
        SEP_T13_END,
    ]
    return lines


# ---------------------------------------------------------------------------
# Сборка документа
# ---------------------------------------------------------------------------

def _sub_meta(sub):
    meta = sub.get("substance") or {}
    name = meta.get("name") or sub.get("name") or meta.get("code") or sub.get("code") or "—"
    code = meta.get("code") or sub.get("code") or "—"
    return str(code), str(name)


def build_tables(request_data: dict, result_data: dict, coef_a: float) -> list:
    """Список страниц; страница — список строк."""
    sources = request_data.get("sources") or []
    meteo = request_data.get("meteo") or {}
    grid = request_data.get("grid") or {}
    obj = (request_data.get("enterprise") or {}).get("name") or "—"
    by_subs = [s for s in (result_data.get("by_substance") or []) if s.get("points")]
    numbers = [source_number(_Obj(s), i) for i, s in enumerate(sources)]
    all_points = by_subs[0]["points"] if by_subs else []
    gxy = _GridXY(all_points, _f(grid.get("step"), 0)) if all_points else None

    pages = [_table1(obj, len(sources), len(by_subs), _f(meteo.get("temperature")),
                     coef_a, _f(meteo.get("wind_speed")))]

    # --- Таблица 7 ---
    t7 = []
    for s, num in zip(sources, numbers):
        H, D, w, T = (_f(s.get(k)) for k in ("height", "diameter", "velocity", "temperature"))
        V = math.pi * D * D / 4.0 * w
        x1 = y1 = 0
        x2 = y2 = None
        if gxy:
            cx, cy = gxy.xy(s.get("lat"), s.get("lon"))
            x1, y1 = int(round(cx)), int(round(cy))
            if (s.get("source_type") or s.get("type")) == "area" and _f(s.get("area_length")) > 0:
                # Площадной: X1Y1–X2Y2 — концы средней линии, Д — ширина
                half = _f(s.get("area_length")) / 2.0
                a = math.radians(_f(s.get("area_angle")))
                x1, y1 = int(round(cx - half * math.cos(a))), int(round(cy - half * math.sin(a)))
                x2, y2 = int(round(cx + half * math.cos(a))), int(round(cy + half * math.sin(a)))
                D = _f(s.get("area_width"))
        t7.append(_t7_row(num, H, D, w, V, T, x1, y1, x2, y2))
    pages += _table7_pages(obj, t7)

    # --- Таблица 8 ---
    subs8 = {}
    for s, num in zip(sources, numbers):
        D, w = _f(s.get("diameter")), _f(s.get("velocity"))
        V = math.pi * D * D / 4.0 * w
        emissions = s.get("emissions") or []
        if not emissions and (s.get("emission_gs") or s.get("substance")):
            emissions = [{"substance": s.get("substance"), "emission_gs": s.get("emission_gs"),
                          "emission_ty": s.get("emission_ty"), "pdk": s.get("pdk")}]
        for em in emissions:
            sub = em.get("substance") or {}
            gs, ty = _f(em.get("emission_gs")), _f(em.get("emission_ty"))
            if not gs and ty:
                gs = ty * 1_000_000 / (365.25 * 24 * 3600)
            if not ty and gs:
                ty = gs * 365.25 * 24 * 3600 / 1_000_000
            if not gs:
                continue
            code = str(sub.get("code") or sub.get("name") or "—")
            entry = subs8.setdefault(code, {
                "code": code, "name": sub.get("name") or code,
                "pdk": _f(em.get("pdk") or sub.get("pdk_mr"), 0.5),
                "F": _f(sub.get("F"), 1.0) or 1.0, "entries": [],
            })
            # Концентрация в устье, мг/м³ = M / V · 1000 (как колонка «мг/куб.м.» Радуги)
            mg = gs / V * 1000.0 if V > 0 and (s.get("source_type") or s.get("type")) != "area" else None
            entry["entries"].append({"num": num, "gs": gs, "ty": ty, "mg": mg})
    for e in subs8.values():
        e["gs"] = sum(x["gs"] for x in e["entries"])
        e["ty"] = sum(x["ty"] for x in e["entries"])
    pages.append(_table8(obj, list(subs8.values())))

    # --- Таблицы 12 и 13: сначала все таблицы 12 по веществам, затем все
    # таблицы 13 (как в распечатке «Радуги»; часть таблиц 12 в отчёт не идёт,
    # и их удобно вырезать одним блоком) ---
    cells_by_sub = []
    for sub in by_subs:
        code, name = _sub_meta(sub)
        pdk = _f(sub.get("pdk"), 0.5) or 0.5
        cells = {}
        for p in sub["points"]:
            x, y = gxy.node(p["lat"], p["lon"])
            cells[(x, y)] = (_f(p.get("c")) / pdk, _hb(p.get("d")), _f(p.get("u")))
        cells_by_sub.append((sub, name, cells))
        pages += _table12_pages(obj, name, cells)

    for sub, name, cells in cells_by_sub:
        qhs = [v[0] for v in cells.values()]
        top_rows = []
        for tp in sub.get("top_points") or []:
            x, y = gxy.node(tp["lat"], tp["lon"])
            contribs = []
            for c in tp.get("contributions") or []:
                num = c.get("number")
                if not num:
                    idx = c.get("src_index", 0)
                    num = numbers[idx] if 0 <= idx < len(numbers) else f"{idx + 1:02d}"
                contribs.append((str(num), _f(c.get("contribution_pdk"))))
            top_rows.append({
                "qh": _f(tp.get("qh")), "x": x, "y": y,
                "hb": _hb(tp.get("wind_dir_deg")), "u": _f(tp.get("wind_speed_ms")),
                "contribs": contribs,
            })
        pages.append(_table13(obj, name, top_rows, min(qhs) if qhs else 0.0,
                              max(qhs) if qhs else 0.0))
    return pages


class _Obj:
    """Обёртка dict → атрибуты для source_number."""

    def __init__(self, d):
        self.number = d.get("number")
        self.name = d.get("name")


def generate_raduga_docx(request_data: dict, result_data: dict, coef_a: float = 200) -> bytes:
    pages = build_tables(request_data, result_data, coef_a)

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.left_margin = section.right_margin = Cm(1.5)
    # Верх/низ 1,0 см: так на лист входит 21 строка Y таблицы 12
    # (13 строк шапки + 21·4 = 97 строк по 8 пт = 27,4 см из 27,7 см).
    section.top_margin = section.bottom_margin = Cm(1.0)
    section.header_distance = section.footer_distance = Cm(0.5)

    style = doc.styles["Normal"]
    style.font.name = FONT
    style.font.size = Pt(FONT_SIZE)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rfonts.set(qn(attr), FONT)
    pf = style.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(LINE_PITCH)

    # Абзацы собираем прямо в XML: doc.add_paragraph() на тысячи строк очень
    # медленный (python-docx добавляет текст посимвольно и ищет место вставки).
    body = doc.element.body
    sect_pr = body.find(qn("w:sectPr"))
    W_P, W_PPR, W_R, W_T = qn("w:p"), qn("w:pPr"), qn("w:r"), qn("w:t")
    W_PBB, XML_SPACE = qn("w:pageBreakBefore"), "{http://www.w3.org/XML/1998/namespace}space"
    for page_no, lines in enumerate(pages):
        for i, line in enumerate(lines):
            p = etree.Element(W_P)
            if i == 0 and page_no > 0:
                etree.SubElement(etree.SubElement(p, W_PPR), W_PBB)
            text = line.rstrip()
            if text:
                t = etree.SubElement(etree.SubElement(p, W_R), W_T)
                t.text = text
                t.set(XML_SPACE, "preserve")
            sect_pr.addprevious(p)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
