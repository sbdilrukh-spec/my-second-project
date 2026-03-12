"""
Генерация стандартных таблиц ПДВ и ОВОС.

Таблицы ПДВ: П-1..П-5
Таблицы ОВОС: О-1..О-6
"""

import numpy as np


def generate_pdv_tables(sources, meteo, city_data, substance, result, enterprise=None):
    """Генерирует таблицы П-1..П-5 для раздела ПДВ."""
    tables = {}

    # П-1: Инвентаризация источников выбросов
    p1_rows = []
    for i, src in enumerate(sources):
        V1 = np.pi / 4 * src.diameter ** 2 * src.velocity
        p1_rows.append({
            "number": i + 1,
            "name": src.name,
            "lat": round(src.lat, 5),
            "lon": round(src.lon, 5),
            "H": src.height,
            "D": src.diameter,
            "w0": src.velocity,
            "Tg": src.temperature,
            "V1": round(V1, 3),
        })
    tables["P1"] = {
        "title": "П-1. Инвентаризация источников выбросов",
        "columns": ["№", "Название", "Широта", "Долгота", "H, м", "D, м", "w0, м/с", "Tг, °C", "V1, м³/с"],
        "rows": p1_rows,
    }

    # П-2: Параметры выбросов ЗВ по источникам
    sub_name = substance.get("name", "—") if substance else "—"
    p2_rows = []
    for i, src in enumerate(sources):
        p2_rows.append({
            "number": i + 1,
            "source": src.name,
            "substance": sub_name,
            "emission_gs": src.get_emission_gs(),
            "emission_ty": src.emission_ty,
        })
    tables["P2"] = {
        "title": "П-2. Параметры выбросов ЗВ по источникам",
        "columns": ["№", "Источник", "Вещество", "Выброс, г/с", "Выброс, т/год"],
        "rows": p2_rows,
    }

    # П-3: Суммарные выбросы по предприятию
    total_gs = sum(src.get_emission_gs() for src in sources)
    total_ty = sum(src.emission_ty or 0 for src in sources)
    tables["P3"] = {
        "title": "П-3. Суммарные выбросы по предприятию",
        "columns": ["Вещество", "Суммарный выброс, г/с", "Суммарный выброс, т/год"],
        "rows": [{"substance": sub_name, "total_gs": round(total_gs, 4), "total_ty": round(total_ty, 4)}],
    }

    # П-4: Результаты расчёта рассеивания
    pdk_val = substance.get("pdk_mr", 0.5) if substance else 0.5
    max_c = result.get("max_c", 0)
    ratio = round(max_c / pdk_val, 3) if pdk_val > 0 else None
    tables["P4"] = {
        "title": "П-4. Результаты расчёта рассеивания",
        "columns": ["Вещество", "Cmax, мг/м³", "ПДК, мг/м³", "Cmax/ПДК", "Превышение"],
        "rows": [{
            "substance": sub_name,
            "max_c": round(max_c, 6),
            "pdk": pdk_val,
            "ratio": ratio,
            "exceeds": "Да" if max_c > pdk_val else "Нет",
        }],
    }

    # П-5: Предлагаемые нормативы ПДВ
    p5_rows = []
    for i, src in enumerate(sources):
        p5_rows.append({
            "number": i + 1,
            "source": src.name,
            "substance": sub_name,
            "pdv_gs": src.get_emission_gs(),
            "pdv_ty": src.emission_ty,
        })
    tables["P5"] = {
        "title": "П-5. Предлагаемые нормативы ПДВ",
        "columns": ["№", "Источник", "Вещество", "ПДВ, г/с", "ПДВ, т/год"],
        "rows": p5_rows,
    }

    return tables


def generate_ovos_tables(sources, meteo, city_data, substance, result, enterprise=None):
    """Генерирует таблицы О-1..О-6 для раздела ОВОС."""
    tables = {}

    # О-1: Характеристика источников выбросов
    o1_rows = []
    for i, src in enumerate(sources):
        V1 = np.pi / 4 * src.diameter ** 2 * src.velocity
        o1_rows.append({
            "number": i + 1,
            "name": src.name,
            "H": src.height,
            "D": src.diameter,
            "w0": src.velocity,
            "Tg": src.temperature,
            "V1": round(V1, 3),
            "type": "организованный",
        })
    tables["O1"] = {
        "title": "О-1. Характеристика источников выбросов",
        "columns": ["№", "Название", "H, м", "D, м", "w0, м/с", "Tг, °C", "V1, м³/с", "Тип"],
        "rows": o1_rows,
    }

    # О-2: Перечень и количество ЗВ
    sub_name = substance.get("name", "—") if substance else "—"
    sub_code = substance.get("code", "—") if substance else "—"
    pdk_mr = substance.get("pdk_mr") if substance else None
    pdk_ss = substance.get("pdk_ss") if substance else None
    hazard = substance.get("hazard_class") if substance else None
    total_gs = sum(src.get_emission_gs() for src in sources)
    total_ty = sum(src.emission_ty or 0 for src in sources)
    tables["O2"] = {
        "title": "О-2. Перечень и количество ЗВ",
        "columns": ["Код", "Название", "Класс опасности", "ПДК м.р.", "ПДК с.с.", "Выброс, г/с", "Выброс, т/год"],
        "rows": [{
            "code": sub_code, "name": sub_name, "hazard_class": hazard,
            "pdk_mr": pdk_mr, "pdk_ss": pdk_ss,
            "total_gs": round(total_gs, 4), "total_ty": round(total_ty, 4),
        }],
    }

    # О-3: Метеорологические условия расчёта
    tables["O3"] = {
        "title": "О-3. Метеорологические условия расчёта",
        "columns": ["Параметр", "Значение"],
        "rows": [
            {"param": "Город", "value": meteo.city},
            {"param": "Коэффициент A", "value": city_data.get("A", 200)},
            {"param": "Класс устойчивости", "value": meteo.stability_class},
            {"param": "Скорость ветра, м/с", "value": meteo.wind_speed},
            {"param": "Направление ветра, °", "value": meteo.wind_direction},
            {"param": "Температура воздуха, °C", "value": meteo.temperature},
            {"param": "Режим ветра", "value": getattr(meteo, "wind_mode", "360")},
        ],
    }

    # О-4: Результаты расчёта приземных концентраций
    max_c = result.get("max_c", 0)
    pdk_val = pdk_mr or 0.5
    tables["O4"] = {
        "title": "О-4. Результаты расчёта приземных концентраций",
        "columns": ["Вещество", "Фон", "Расчётная Cmax", "Cmax+фон", "ПДК", "Доля ПДК"],
        "rows": [{
            "substance": sub_name,
            "background": 0,
            "max_c": round(max_c, 6),
            "max_c_bg": round(max_c, 6),
            "pdk": pdk_val,
            "ratio": round(max_c / pdk_val, 3) if pdk_val > 0 else None,
        }],
    }

    # О-5: Вклад отдельных источников
    src_results = result.get("source_results", [])
    total_cm = sum(sr.get("cm_mg", 0) for sr in src_results) or 1
    o5_rows = []
    for sr in src_results:
        cm = sr.get("cm_mg", 0)
        o5_rows.append({
            "source": sr.get("name", "—"),
            "substance": sub_name,
            "cm_mg": round(cm, 6),
            "xm": sr.get("xm", 0),
            "share": round(cm / total_cm * 100, 1) if total_cm > 0 else 0,
        })
    tables["O5"] = {
        "title": "О-5. Вклад отдельных источников",
        "columns": ["Источник", "Вещество", "Cm, мг/м³", "Xm, м", "Доля, %"],
        "rows": o5_rows,
    }

    # О-6: Сводная таблица воздействия
    exceeds = max_c > pdk_val
    tables["O6"] = {
        "title": "О-6. Сводная таблица воздействия",
        "columns": ["Вещество", "Класс опасности", "ПДК", "Cmax", "Превышение", "Вывод"],
        "rows": [{
            "substance": sub_name,
            "hazard_class": hazard,
            "pdk": pdk_val,
            "max_c": round(max_c, 6),
            "exceeds": "Да" if exceeds else "Нет",
            "conclusion": "Требуются мероприятия по снижению" if exceeds else "Воздействие в пределах нормы",
        }],
    }

    return tables
