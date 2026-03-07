from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import io

from .models import CalculationRequest, CalculationResponse, GridPoint, SourceResult
from .meteo_data import CITIES
from .ond86 import compute_grid
from .pdf_export import generate_pdf

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

    return CalculationResponse(
        points=points,
        max_c=round(max_c, 6),
        max_lat=float(lats[max_idx]),
        max_lon=float(lons[max_idx]),
        source_results=[SourceResult(**sr) for sr in src_results],
        exceeds_pdk=max_c > pdk,
        pdk=pdk,
    )


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
# GET /  — health check
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "ok", "app": "ОНД-86 Расчёт рассеивания"}
