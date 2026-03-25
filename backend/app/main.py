from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
import io
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill

from .models import CalculationRequest, CalculationResponse, GridPoint, SourceResult, SzzResult, SzzBoundaryPoint
from .meteo_data import CITIES
from .ond86 import compute_grid, compute_szz_boundary
from .pdf_export import generate_pdf
from .substances import SUBSTANCES
from .tables import generate_pdv_tables, generate_ovos_tables
from .import_sources import parse_csv, parse_excel, generate_template_csv, generate_template_xlsx

app = FastAPI(title="ОНД-86 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# GET /api/cities  — список городов
# ---------------------------------------------------------------------------

@app.get("/api/cities")
def get_cities():
    result = []
    for name, data in CITIES.items():
        result.append({
            "name": name,
            "lat": data["lat"],
            "lon": data["lon"],
            "A": data["A"],
            "T_warm": data.get("T_warm", 20.0),
            "T_cold": data.get("T_cold", 0.0),
            "T_avg": data.get("T_avg", 10.0),
        })
    return result


# ---------------------------------------------------------------------------
# GET /api/substances  — справочник веществ
# ---------------------------------------------------------------------------

@app.get("/api/substances")
def get_substances():
    return SUBSTANCES


# ---------------------------------------------------------------------------
# POST /api/import  — импорт источников из CSV/Excel
# ---------------------------------------------------------------------------

@app.post("/api/import")
async def import_sources(file: UploadFile = File(...)):
    filename = file.filename.lower()
    content = await file.read()

    if filename.endswith(".csv"):
        text = content.decode("utf-8-sig")
        sources = parse_csv(text)
    elif filename.endswith(".xlsx"):
        sources = parse_excel(content)
    else:
        raise HTTPException(status_code=400, detail="Поддерживаются только CSV (.csv) и Excel (.xlsx)")

    # Разделяем на валидные и с ошибками
    valid = []
    errors = []
    for s in sources:
        row_errors = s.pop("_errors", [])
        s.pop("_row", None)
        if row_errors:
            errors.extend(row_errors)
        else:
            valid.append(s)

    return {"sources": valid, "errors": errors, "total": len(sources), "valid_count": len(valid)}


# ---------------------------------------------------------------------------
# GET /api/import/template  — скачать шаблон CSV
# ---------------------------------------------------------------------------

@app.get("/api/import/template")
def get_import_template():
    xlsx_bytes = generate_template_xlsx()
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_sources.xlsx"},
    )


# ---------------------------------------------------------------------------
# GET /api/weather  — текущая погода через Open-Meteo
# ---------------------------------------------------------------------------

@app.get("/api/weather")
async def get_weather(lat: float = Query(...), lon: float = Query(...)):
    import httpx
    from datetime import datetime, timezone

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,wind_speed_10m,wind_direction_10m,cloud_cover,is_day",
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ошибка Open-Meteo: {e}")

    current = data.get("current", {})
    wind_speed = current.get("wind_speed_10m", 3.0)
    cloud_cover = current.get("cloud_cover", 50)
    is_day = current.get("is_day", 1)

    # Определение класса устойчивости по Пасквиллу–Тёрнеру
    stability_class = _determine_stability(wind_speed, cloud_cover, bool(is_day))

    return {
        "temperature": current.get("temperature_2m"),
        "wind_speed": wind_speed,
        "wind_direction": current.get("wind_direction_10m"),
        "cloud_cover": cloud_cover,
        "is_day": bool(is_day),
        "stability_class": stability_class,
        "source": "Open-Meteo",
    }


def _determine_stability(wind_speed: float, cloud_cover: float, is_day: bool) -> str:
    """Класс устойчивости по Пасквиллу–Тёрнеру."""
    if is_day:
        if cloud_cover < 30:
            radiation = "strong"
        elif cloud_cover < 70:
            radiation = "moderate"
        else:
            radiation = "weak"

        if wind_speed < 2:
            return {"strong": "A", "moderate": "A", "weak": "B"}[radiation]
        elif wind_speed < 3:
            return {"strong": "A", "moderate": "B", "weak": "C"}[radiation]
        elif wind_speed < 5:
            return {"strong": "B", "moderate": "B", "weak": "C"}[radiation]
        elif wind_speed < 6:
            return {"strong": "C", "moderate": "C", "weak": "D"}[radiation]
        else:
            return {"strong": "C", "moderate": "D", "weak": "D"}[radiation]
    else:
        if cloud_cover < 50:
            if wind_speed < 2:
                return "F"
            elif wind_speed < 3:
                return "E"
            elif wind_speed < 5:
                return "D"
            else:
                return "D"
        else:
            if wind_speed < 2:
                return "F"
            elif wind_speed < 3:
                return "F"
            elif wind_speed < 5:
                return "E"
            else:
                return "D"


# ---------------------------------------------------------------------------
# POST /api/calculate  — расчёт поля концентраций
# ---------------------------------------------------------------------------

@app.post("/api/calculate", response_model=CalculationResponse)
def calculate(req: CalculationRequest):
    if not req.sources:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один источник")

    city_data = CITIES.get(req.meteo.city)
    if city_data is None:
        # Если города нет в БД — используем коэффициент по умолчанию
        city_data = {"A": 200, "lat": req.sources[0].lat, "lon": req.sources[0].lon}

    lats, lons, total_mg, src_results = compute_grid(
        sources=req.sources,
        meteo=req.meteo,
        city_data=city_data,
        grid_radius=req.grid.radius,
        grid_step=req.grid.step,
    )

    # Максимум
    max_idx = int(total_mg.argmax())
    max_c = float(total_mg[max_idx])

    # Сборка ответа (отфильтровываем нули для уменьшения объёма)
    threshold = max_c * 0.001   # показываем точки > 0.1% от максимума
    points = [
        GridPoint(lat=float(lats[i]), lon=float(lons[i]), c=round(float(total_mg[i]), 6))
        for i in range(len(lats))
        if total_mg[i] > threshold
    ]

    pdk = req.pdk or 0.5

    # Расчёт границы СЗЗ
    center_lat = sum(s.lat for s in req.sources) / len(req.sources)
    center_lon = sum(s.lon for s in req.sources) / len(req.sources)
    szz_data = compute_szz_boundary(lats, lons, total_mg, pdk, center_lat, center_lon)
    szz = SzzResult(
        boundary=[SzzBoundaryPoint(**p) for p in szz_data["boundary"]],
        max_distance_m=szz_data["max_distance_m"],
        min_distance_m=szz_data["min_distance_m"],
        area_ha=szz_data["area_ha"],
    ) if szz_data["max_distance_m"] > 0 else None

    return CalculationResponse(
        points=points,
        max_c=round(max_c, 6),
        max_lat=float(lats[max_idx]),
        max_lon=float(lons[max_idx]),
        source_results=[SourceResult(**sr) for sr in src_results],
        exceeds_pdk=max_c > pdk,
        pdk=pdk,
        szz=szz,
    )


# ---------------------------------------------------------------------------
# POST /api/tables  — генерация таблиц ПДВ/ОВОС
# ---------------------------------------------------------------------------

@app.post("/api/tables")
def get_tables(req: CalculationRequest):
    if not req.sources:
        raise HTTPException(status_code=400, detail="Необходимо указать хотя бы один источник")

    city_data = CITIES.get(req.meteo.city, {"A": 200})

    lats, lons, total_mg, src_results = compute_grid(
        sources=req.sources,
        meteo=req.meteo,
        city_data=city_data,
        grid_radius=req.grid.radius,
        grid_step=req.grid.step,
    )

    max_idx = int(total_mg.argmax())
    max_c = float(total_mg[max_idx])
    pdk = req.pdk or 0.5

    result_dict = {
        "max_c": max_c,
        "source_results": src_results,
        "exceeds_pdk": max_c > pdk,
        "pdk": pdk,
    }

    substance = req.substance.model_dump() if req.substance else None

    pdv = generate_pdv_tables(req.sources, req.meteo, city_data, substance, result_dict)
    ovos = generate_ovos_tables(req.sources, req.meteo, city_data, substance, result_dict)

    return {"pdv": pdv, "ovos": ovos}


# ---------------------------------------------------------------------------
# POST /api/export/pdf  — генерация PDF-отчёта
# ---------------------------------------------------------------------------

@app.post("/api/export/pdf")
def export_pdf(req: CalculationRequest):
    city_data = CITIES.get(req.meteo.city, {"A": 200})

    lats, lons, total_mg, src_results = compute_grid(
        sources=req.sources,
        meteo=req.meteo,
        city_data=city_data,
        grid_radius=req.grid.radius,
        grid_step=req.grid.step,
    )

    max_idx = int(total_mg.argmax())
    max_c = float(total_mg[max_idx])
    pdk = req.pdk or 0.5

    # Для PDF берём все точки (для графика)
    points_for_pdf = [
        {"lat": float(lats[i]), "lon": float(lons[i]), "c": float(total_mg[i])}
        for i in range(len(lats))
    ]

    request_dict = req.model_dump()
    result_dict = {
        "points": points_for_pdf,
        "max_c": max_c,
        "max_lat": float(lats[max_idx]),
        "max_lon": float(lons[max_idx]),
        "source_results": src_results,
        "exceeds_pdk": max_c > pdk,
        "pdk": pdk,
    }

    pdf_bytes = generate_pdf(request_dict, result_dict)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ond86_report.pdf"},
    )


# ---------------------------------------------------------------------------
# POST /api/export/excel  — генерация Excel-отчёта (таблицы ПДВ + ОВОС)
# ---------------------------------------------------------------------------

@app.post("/api/export/excel")
def export_excel(req: CalculationRequest):
    city_data = CITIES.get(req.meteo.city, {"A": 200})

    lats, lons, total_mg, src_results = compute_grid(
        sources=req.sources,
        meteo=req.meteo,
        city_data=city_data,
        grid_radius=req.grid.radius,
        grid_step=req.grid.step,
    )

    max_idx = int(total_mg.argmax())
    max_c = float(total_mg[max_idx])
    pdk = req.pdk or 0.5

    result_dict = {
        "max_c": max_c,
        "source_results": src_results,
        "exceeds_pdk": max_c > pdk,
        "pdk": pdk,
    }

    substance = req.substance.model_dump() if req.substance else None

    pdv = generate_pdv_tables(req.sources, req.meteo, city_data, substance, result_dict)
    ovos = generate_ovos_tables(req.sources, req.meteo, city_data, substance, result_dict)

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    all_tables = {**pdv, **ovos}

    for key, table_data in all_tables.items():
        title = table_data["title"]
        columns = table_data["columns"]
        rows = table_data["rows"]

        ws = wb.create_sheet(title=key)

        # Title row
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(columns))
        cell = ws.cell(row=1, column=1, value=title)
        cell.font = Font(bold=True, size=13)
        cell.alignment = Alignment(horizontal="center")

        # Header row
        for col_idx, col_name in enumerate(columns, 1):
            cell = ws.cell(row=3, column=col_idx, value=col_name)
            cell.font = header_font_white
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", wrap_text=True)
            cell.border = thin_border

        # Data rows
        for row_idx, row_data in enumerate(rows, 4):
            values = list(row_data.values())
            for col_idx, val in enumerate(values, 1):
                if col_idx > len(columns):
                    break
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = thin_border
                cell.alignment = Alignment(horizontal="center")

        # Auto-width
        for col_idx in range(1, len(columns) + 1):
            max_len = len(str(columns[col_idx - 1]))
            for row in ws.iter_rows(min_row=4, min_col=col_idx, max_col=col_idx):
                for cell in row:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
            ws.column_dimensions[openpyxl.utils.get_column_letter(col_idx)].width = min(max_len + 4, 30)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = "ond86_tables.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# GET /  — health check
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "app": "ОНД-86 Расчёт рассеивания"}
