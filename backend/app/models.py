from pydantic import BaseModel
from typing import List, Optional


class SubstanceInput(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    pdk_mr: Optional[float] = None
    pdk_ss: Optional[float] = None
    hazard_class: Optional[int] = None


class EmissionEntry(BaseModel):
    """Один выброс одного вещества из источника."""
    substance: Optional[SubstanceInput] = None
    emission_gs: Optional[float] = None    # Выброс, г/с
    emission_ty: Optional[float] = None    # Выброс, т/год
    pdk: Optional[float] = None            # ПДК м.р., мг/м³ (может переопределять substance.pdk_mr)

    def get_emission_gs(self) -> float:
        if self.emission_gs is not None and self.emission_gs > 0:
            return self.emission_gs
        if self.emission_ty is not None and self.emission_ty > 0:
            return self.emission_ty * 1_000_000 / (365.25 * 24 * 3600)
        return 0.0

    def get_pdk(self, fallback: float = 0.5) -> float:
        if self.pdk is not None and self.pdk > 0:
            return self.pdk
        if self.substance and self.substance.pdk_mr is not None and self.substance.pdk_mr > 0:
            return self.substance.pdk_mr
        return fallback

    def get_substance_code(self) -> str:
        """Уникальный ключ для группировки. Если кода нет — пытаемся имя."""
        if self.substance:
            if self.substance.code:
                return str(self.substance.code)
            if self.substance.name:
                return f"name:{self.substance.name}"
        return "unknown"


class SourceInput(BaseModel):
    name: str = "Источник 1"
    lat: float
    lon: float
    height: float        # Высота трубы, м
    diameter: float      # Диаметр устья, м
    velocity: float      # Скорость выхода газов, м/с
    temperature: float   # Температура газов, °C

    # Новая модель: массив выбросов (одно вещество = одна запись)
    emissions: Optional[List[EmissionEntry]] = None

    # Обратная совместимость со старыми проектами / шаблонами:
    # одиночное вещество прямо на источнике. Используется как
    # "первый выброс", если emissions не задан.
    emission_gs: Optional[float] = None
    emission_ty: Optional[float] = None
    pdk: Optional[float] = None
    substance: Optional[SubstanceInput] = None

    def get_emissions(self) -> List[EmissionEntry]:
        """Возвращает массив выбросов, переводя старую плоскую форму в новую."""
        if self.emissions is not None and len(self.emissions) > 0:
            return self.emissions
        # Миграция: одиночный выброс из плоских полей
        return [EmissionEntry(
            substance=self.substance,
            emission_gs=self.emission_gs,
            emission_ty=self.emission_ty,
            pdk=self.pdk,
        )]

    def get_emission_gs(self) -> float:
        """Старый API: суммарный выброс по всем веществам в г/с."""
        return sum(e.get_emission_gs() for e in self.get_emissions())


class MeteoInput(BaseModel):
    city: str
    wind_speed: float        # м/с
    wind_direction: float    # градусы (откуда дует): 0=С, 90=В, 180=Ю, 270=З
    stability_class: str     # A, B, C, D, E, F
    temperature: float       # Температура воздуха, °C
    wind_mode: str = "360"   # "360" — все направления (36 шагов), "single" — одно направление


class GridInput(BaseModel):
    # Новая система: прямоугольная сетка с началом координат в нижнем левом углу
    x_length: float = 7000       # Длина по X, м
    y_length: float = 7000       # Длина по Y, м
    step: float = 500            # Шаг сетки, 100-500 м
    source_offset_x: float = 3500  # Положение источника от X₀, м
    source_offset_y: float = 3500  # Положение источника от Y₀, м
    # Обратная совместимость со старыми проектами
    radius: Optional[float] = None


class BoundaryPoint(BaseModel):
    lat: float
    lon: float


class EnterpriseInput(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    inn: Optional[str] = None
    projectNumber: Optional[str] = None
    client: Optional[str] = None
    developer: Optional[str] = None
    boundary: Optional[List[BoundaryPoint]] = None


class CalculationRequest(BaseModel):
    sources: List[SourceInput]
    meteo: MeteoInput
    grid: GridInput
    pdk: Optional[float] = 0.5
    substance: Optional[SubstanceInput] = None
    enterprise: Optional[EnterpriseInput] = None
    # Снимок карты Leaflet (data URL "data:image/png;base64,...") — только для /export/pdf
    map_snapshot: Optional[str] = None


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


class SubstanceResult(BaseModel):
    """Результат расчёта по одному веществу."""
    code: Optional[str] = None
    name: Optional[str] = None
    pdk: float
    max_c: float
    max_lat: float
    max_lon: float
    exceeds_pdk: bool
    ratio_to_pdk: float
    points: List[GridPoint]
    source_results: List[SourceResult]
    hazard_class: Optional[int] = None


class CalculationResponse(BaseModel):
    # Поля главного (худшего) вещества — для обратной совместимости
    # с фронтендом, который ещё не знает про множественные вещества.
    points: List[GridPoint]
    max_c: float             # мг/м³
    max_lat: float
    max_lon: float
    source_results: List[SourceResult]
    exceeds_pdk: bool
    pdk: float
    szz: Optional[SzzResult] = None

    # Новые поля: результаты по всем веществам.
    by_substance: Optional[List[SubstanceResult]] = None
    primary_code: Optional[str] = None
