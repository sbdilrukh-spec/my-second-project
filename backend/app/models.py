from pydantic import BaseModel
from typing import List, Optional


class SourceInput(BaseModel):
    name: str = "Источник 1"
    lat: float
    lon: float
    height: float        # Высота трубы, м
    diameter: float      # Диаметр устья, м
    velocity: float      # Скорость выхода газов, м/с
    temperature: float   # Температура газов, °C
    emission_gs: Optional[float] = None   # Выброс г/с
    emission_ty: Optional[float] = None   # Выброс т/год

    def get_emission_gs(self) -> float:
        """Возвращает выброс в г/с."""
        if self.emission_gs is not None and self.emission_gs > 0:
            return self.emission_gs
        if self.emission_ty is not None and self.emission_ty > 0:
            return self.emission_ty * 1_000_000 / (365.25 * 24 * 3600)
        return 0.0


class MeteoInput(BaseModel):
    city: str
    wind_speed: float        # м/с
    wind_direction: float    # градусы (откуда дует): 0=С, 90=В, 180=Ю, 270=З
    stability_class: str     # A, B, C, D, E, F
    temperature: float       # Температура воздуха, °C
    wind_mode: str = "360"   # "360" — все направления (36 шагов), "single" — одно направление


class GridInput(BaseModel):
    radius: float    # Радиус расчётной области, м
    step: float      # Шаг сетки, м


class SubstanceInput(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    pdk_mr: Optional[float] = None
    pdk_ss: Optional[float] = None
    hazard_class: Optional[int] = None


class EnterpriseInput(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    inn: Optional[str] = None
    projectNumber: Optional[str] = None
    client: Optional[str] = None
    developer: Optional[str] = None


class CalculationRequest(BaseModel):
    sources: List[SourceInput]
    meteo: MeteoInput
    grid: GridInput
    pdk: Optional[float] = 0.5
    substance: Optional[SubstanceInput] = None
    enterprise: Optional[EnterpriseInput] = None


class GridPoint(BaseModel):
    lat: float
    lon: float
    c: float      # концентрация, мг/м³


class SourceResult(BaseModel):
    name: str
    cm_mg: float   # Максимальная концентрация, мг/м³
    xm: float      # Расстояние до максимума, м


class SzzBoundaryPoint(BaseModel):
    lat: float
    lon: float
    distance_m: float
    angle_deg: float


class SzzResult(BaseModel):
    boundary: List[SzzBoundaryPoint]
    max_distance_m: float
    min_distance_m: float
    area_ha: float


class CalculationResponse(BaseModel):
    points: List[GridPoint]
    max_c: float             # мг/м³
    max_lat: float
    max_lon: float
    source_results: List[SourceResult]
    exceeds_pdk: bool
    pdk: float
    szz: Optional[SzzResult] = None
