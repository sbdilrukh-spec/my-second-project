import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { fetchCities, fetchSubstances, fetchWeather, calculate, fetchTables, exportPdf, exportMapPng, exportExcel } from "./api.js";
import { translations } from "./i18n.js";
import SourceForm, { createDefaultSource, migrateSource } from "./components/SourceForm.jsx";
import MeteoPanel from "./components/MeteoPanel.jsx";

import EnterpriseCard, { DEFAULT_ENTERPRISE } from "./components/EnterpriseCard.jsx";
import TablesPanel from "./components/TablesPanel.jsx";
import ScenarioPanel from "./components/ScenarioPanel.jsx";
import ImportPanel from "./components/ImportPanel.jsx";
import MapView from "./components/MapView.jsx";
import ResultsPanel from "./components/ResultsPanel.jsx";
import TableInput from "./components/TableInput.jsx";
import SubstanceEditor from "./components/SubstanceEditor.jsx";
import EnterpriseBoundaryEditor from "./components/EnterpriseBoundaryEditor.jsx";
import AddSourceModal from "./components/AddSourceModal.jsx";

const DEFAULT_METEO = {
  city: "Ташкент",
  wind_speed: 2.0,
  wind_direction: 270,
  stability_class: "D",
  temperature: 13.0,
  wind_mode: "360",
};

const DEFAULT_GRID = {
  x_length: 7000,
  y_length: 7000,
  step: 500,
  source_offset_x: 3500,
  source_offset_y: 3500,
};

// Приводит источники к формату бэкенда: фронтенд хранит тип в поле `type`,
// а модель SourceInput ожидает `source_type`. Площадные источники бэкенд
// сам разворачивает в сетку точечных подысточников (ОНД-86).
function toBackendSources(sources) {
  return sources.map((src) => ({
    ...src,
    source_type: src.type === "area" ? "area" : "stack",
  }));
}

// Контуры предприятия: до 5 отдельных объектов. Старые проекты хранят один
// контур в enterprise.boundary — нормализуем всё к массиву контуров boundaries.
export const MAX_BOUNDARIES = 5;

// Сколько карточек источников показывать за раз (кнопка «Показать ещё»)
// и с какого количества сворачивать карточки по умолчанию.
const CARDS_PAGE = 30;
const COLLAPSE_THRESHOLD = 15;

function getBoundaries(ent) {
  if (ent?.boundaries && ent.boundaries.length) return ent.boundaries;
  if (ent?.boundary && ent.boundary.length) return [ent.boundary];
  return [];
}

function allBoundaryPoints(ent) {
  return getBoundaries(ent).reduce((acc, c) => acc.concat(c || []), []);
}

// Гарантируем поле boundaries (для отправки на бэкенд и отрисовки).
function migrateEnterprise(ent) {
  if (!ent) return ent;
  if (Array.isArray(ent.boundaries)) return ent;
  if (Array.isArray(ent.boundary) && ent.boundary.length) {
    return { ...ent, boundaries: [ent.boundary] };
  }
  return { ...ent, boundaries: [] };
}

// Миграция старых проектов (radius -> x_length/y_length) + защита от некорректных значений
function migrateGrid(g) {
  if (!g) return DEFAULT_GRID;

  // Старый формат с radius
  if (g.radius && !g.x_length) {
    return {
      x_length: g.radius * 2,
      y_length: g.radius * 2,
      step: g.step || 500,
      source_offset_x: g.radius,
      source_offset_y: g.radius,
    };
  }

  // Мерджим с дефолтами и валидируем: любое отсутствующее, NaN или слишком маленькое значение
  // заменяется дефолтным. Минимум 500 м для области, чтобы избежать "узкой полосы".
  const validNum = (v, def, min = 500) => {
    const n = parseFloat(v);
    return Number.isFinite(n) && n >= min ? n : def;
  };

  return {
    x_length: validNum(g.x_length, DEFAULT_GRID.x_length, 500),
    y_length: validNum(g.y_length, DEFAULT_GRID.y_length, 500),
    step: validNum(g.step, DEFAULT_GRID.step, 100),
    source_offset_x: validNum(g.source_offset_x, DEFAULT_GRID.source_offset_x, 0),
    source_offset_y: validNum(g.source_offset_y, DEFAULT_GRID.source_offset_y, 0),
  };
}

export default function App() {
  const [lang, setLang] = useState("ru");
  const t = translations[lang];

  // --- Восстановление из localStorage ---
  // Лениво, строго один раз: на больших проектах JSON.parse занимает десятки
  // миллисекунд, и парсить его на каждом рендере (каждое нажатие клавиши) нельзя.
  const [savedProject] = useState(() => {
    try { return JSON.parse(localStorage.getItem("ond86_autosave")); } catch { return null; }
  });

  const [cities, setCities] = useState([]);
  const [substances, setSubstances] = useState([]);
  const [meteo, setMeteo] = useState(savedProject?.meteo || DEFAULT_METEO);
  const [grid, setGrid] = useState(migrateGrid(savedProject?.grid) || DEFAULT_GRID);
  const [selectedSubstance, setSelectedSubstance] = useState(savedProject?.selectedSubstance || null);
  const [sources, setSources] = useState(
    savedProject?.sources
      ? savedProject.sources.map(migrateSource)
      : [createDefaultSource(41.2995, 69.2401, 0)]
  );
  const [enterprise, setEnterprise] = useState(migrateEnterprise(savedProject?.enterprise || DEFAULT_ENTERPRISE));

  const [result, setResult] = useState(null);
  const [displaySubstanceCode, setDisplaySubstanceCode] = useState(null); // выбранное для отображения вещество (если расчёт многовеществный)
  const [tables, setTables] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("heatmap");

  // Поиск и порционный вывод карточек: при сотнях источников рендерить все
  // карточки сразу нельзя — DOM разрастается и интерфейс замирает.
  const [sourceFilter, setSourceFilter] = useState("");
  const [visibleCards, setVisibleCards] = useState(CARDS_PAGE);

  const [pickingIndex, setPickingIndex] = useState(null);
  const [pickingEnterprise, setPickingEnterprise] = useState(false);
  // Активный объект (контур) при вводе координат кликом по карте / в таблице
  const [activeBoundaryIdx, setActiveBoundaryIdx] = useState(0);
  const [inputMode, setInputMode] = useState("cards"); // "cards" | "table"
  const [sidebarWide, setSidebarWide] = useState(false);

  // --- Сценарии (до/после) ---
  const [scenarioMode, setScenarioMode] = useState(false);
  const [baselineResult, setBaselineResult] = useState(null);

  // --- Автосохранение каждые 30 секунд ---
  const autosaveRef = useRef();
  autosaveRef.current = { sources, meteo, grid, selectedSubstance, enterprise };

  useEffect(() => {
    const save = () => {
      localStorage.setItem("ond86_autosave", JSON.stringify(autosaveRef.current));
    };
    const interval = setInterval(save, 30000);
    window.addEventListener("beforeunload", save);
    return () => {
      clearInterval(interval);
      window.removeEventListener("beforeunload", save);
      save();
    };
  }, []);

  // Загрузка городов и веществ
  useEffect(() => {
    fetchCities()
      .then(setCities)
      .catch(() => {
        setCities([
          { name: "Ташкент", lat: 41.2995, lon: 69.2401, A: 200, T_avg: 13.1 },
          { name: "Навои", lat: 40.0839, lon: 65.3792, A: 220, T_avg: 14.0 },
          { name: "Самарканд", lat: 39.649, lon: 66.975, A: 200, T_avg: 12.7 },
        ]);
      });
    fetchSubstances()
      .then(setSubstances)
      .catch(() => {});
  }, []);

  // Загрузка пользовательских веществ из localStorage
  const [customSubstances, setCustomSubstances] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("customSubstances") || "[]");
    } catch { return []; }
  });

  useEffect(() => {
    localStorage.setItem("customSubstances", JSON.stringify(customSubstances));
  }, [customSubstances]);

  // useMemo: стабильная ссылка на объединённый список — иначе каждый рендер
  // создаёт новый массив и ломает React.memo у 200 карточек SourceForm.
  const allSubstances = useMemo(
    () => [...substances, ...customSubstances],
    [substances, customSubstances]
  );

  // «Усыновление» веществ из загруженного проекта: файл проекта хранит вещество
  // внутри каждого выброса, но выпадающие списки строятся из справочника
  // (бэкенд + пользовательские). Если проект создан на другой машине (например,
  // на сайте, где добавляли свои вещества), локальный справочник их не знает —
  // добавляем такие вещества в пользовательские, чтобы списки и импорт их видели.
  useEffect(() => {
    if (substances.length === 0) return; // ждём справочник с бэкенда
    const known = new Set(allSubstances.map((s) => String(s.code)));
    const missing = [];
    for (const src of sources) {
      for (const em of src.emissions || []) {
        const sub = em?.substance;
        if (sub?.code && !known.has(String(sub.code)) &&
            !missing.some((m) => String(m.code) === String(sub.code))) {
          missing.push({ ...sub, custom: true });
        }
      }
    }
    if (missing.length > 0) {
      setCustomSubstances((prev) => [...prev, ...missing]);
    }
  }, [sources, substances, allSubstances]);

  // Карточки после фильтра поиска. Сохраняем исходный индекс i — все
  // обработчики (onChange, onRemove, ...) работают по индексу в sources.
  const filteredSources = useMemo(() => {
    const items = sources.map((src, i) => ({ src, i }));
    const q = sourceFilter.trim().toLowerCase();
    if (!q) return items;
    return items.filter(({ src, i }) =>
      (src.name || "").toLowerCase().includes(q) || String(i + 1) === q
    );
  }, [sources, sourceFilter]);

  // Substance editor modal
  const [showSubstanceEditor, setShowSubstanceEditor] = useState(false);
  // Enterprise boundary editor modal
  const [showBoundaryEditor, setShowBoundaryEditor] = useState(false);
  // Триггер-счётчик: при изменении карта приближается к контуру предприятия
  const [fitMapTrigger, setFitMapTrigger] = useState(0);
  const requestFitToBoundary = useCallback(() => {
    setFitMapTrigger((c) => c + 1);
  }, []);

  const reloadSubstances = useCallback(() => {
    fetchSubstances()
      .then(setSubstances)
      .catch(() => {});
  }, []);

  // Центр карты
  const cityCenter = (() => {
    const city = cities.find((c) => c.name === meteo.city);
    return city ? [city.lat, city.lon] : null;
  })();

  // displayedResult — то, что реально показывается на карте и в панели результатов.
  // Если есть многовеществный расчёт (by_substance), берём данные для выбранного
  // displaySubstanceCode. Иначе используем плоские поля результата.
  const displayedResult = useMemo(() => {
    if (!result) return null;
    if (Array.isArray(result.by_substance) && result.by_substance.length > 0) {
      const code = displaySubstanceCode || result.primary_code;
      const sub = result.by_substance.find(s => s.code === code) || result.by_substance[0];
      if (sub) {
        return {
          ...result,
          points: sub.points,
          max_c: sub.max_c,
          max_lat: sub.max_lat,
          max_lon: sub.max_lon,
          source_results: sub.source_results,
          exceeds_pdk: sub.exceeds_pdk,
          pdk: sub.pdk,
          _substance: { code: sub.code, name: sub.name, pdk_mr: sub.pdk, hazard_class: sub.hazard_class },
        };
      }
    }
    return result;
  }, [result, displaySubstanceCode]);

  // Центроид всех контуров предприятия (по всем точкам) — null если пусто
  const enterpriseCentroid = (() => {
    const b = allBoundaryPoints(enterprise);
    if (!b || b.length === 0) return null;
    const lat = b.reduce((s, p) => s + (p.lat || 0), 0) / b.length;
    const lon = b.reduce((s, p) => s + (p.lon || 0), 0) / b.length;
    return { lat, lon };
  })();

  // Список контуров и суммарное число точек — для бейджей/кнопок
  const boundaryList = getBoundaries(enterprise);
  const boundaryPointCount = boundaryList.reduce((n, c) => n + (c?.length || 0), 0);

  useEffect(() => {
    const city = cities.find((c) => c.name === meteo.city);
    if (!city) return;
    // Если контур предприятия задан — он становится якорем,
    // источник #0 не «прыгает» при смене города.
    if (enterpriseCentroid) return;
    setSources((prev) =>
      prev.map((src, i) =>
        i === 0 ? { ...src, lat: city.lat, lon: city.lon } : src
      )
    );
  }, [meteo.city, cities, enterpriseCentroid?.lat, enterpriseCentroid?.lon]);

  const handleSourceChange = useCallback((index, key, value) => {
    // Старые ключи (substance/pdk/emission_gs/emission_ty) перенаправляем
    // в первый элемент массива emissions — для обратной совместимости с
    // компонентами, которые ещё не знают про многовеществную модель
    // (например, TableInput, ImportPanel).
    const LEGACY_KEYS = new Set(["substance", "pdk", "emission_gs", "emission_ty"]);
    setSources((prev) =>
      prev.map((src, i) => {
        if (i !== index) return src;
        // Переключение на площадной тип: материализуем размеры площадки.
        // У источников из импорта/старых проектов полей area_* нет вообще;
        // форма показывает подстановку "200×100", но в данных пусто — бэкенд
        // молча считал такой источник точечным.
        if (key === "type" && value === "area") {
          return {
            ...src,
            type: "area",
            area_length: src.area_length || 200,
            area_width: src.area_width || 100,
            area_angle: src.area_angle ?? 0,
            area_subdivisions: src.area_subdivisions || 5,
          };
        }
        if (LEGACY_KEYS.has(key)) {
          const ems = Array.isArray(src.emissions) && src.emissions.length > 0
            ? [...src.emissions]
            : [{ substance: null, emission_gs: null, emission_ty: null, pdk: 0.5 }];
          ems[0] = { ...ems[0], [key]: value };
          return { ...src, emissions: ems };
        }
        return { ...src, [key]: value };
      })
    );
  }, []);

  // Изменение конкретного поля одной строки выбросов
  const handleEmissionChange = useCallback((srcIdx, emIdx, key, value) => {
    setSources((prev) =>
      prev.map((src, i) => {
        if (i !== srcIdx) return src;
        const ems = Array.isArray(src.emissions) ? [...src.emissions] : [];
        if (emIdx < 0 || emIdx >= ems.length) return src;
        ems[emIdx] = { ...ems[emIdx], [key]: value };
        return { ...src, emissions: ems };
      })
    );
  }, []);

  const handleAddEmission = useCallback((srcIdx) => {
    setSources((prev) =>
      prev.map((src, i) => {
        if (i !== srcIdx) return src;
        const ems = Array.isArray(src.emissions) ? [...src.emissions] : [];
        ems.push({ substance: null, emission_gs: null, emission_ty: null, pdk: 0.5 });
        return { ...src, emissions: ems };
      })
    );
  }, []);

  const handleRemoveEmission = useCallback((srcIdx, emIdx) => {
    setSources((prev) =>
      prev.map((src, i) => {
        if (i !== srcIdx) return src;
        const ems = Array.isArray(src.emissions) ? [...src.emissions] : [];
        if (ems.length <= 1) return src; // последнюю не удаляем
        const next = ems.filter((_, idx) => idx !== emIdx);
        return { ...src, emissions: next };
      })
    );
  }, []);

  const handleAddSource = () => {
    const city = cities.find((c) => c.name === meteo.city);
    // Приоритет: центроид контура предприятия → центр города → дефолт
    const baseLat = enterpriseCentroid?.lat ?? city?.lat ?? 41.3;
    const baseLon = enterpriseCentroid?.lon ?? city?.lon ?? 69.24;
    // Открываем модал выбора типа — базовые координаты сохраняются в стейте
    setPendingNewSourceBase({ lat: baseLat, lon: baseLon });
    setShowAddSourceModal(true);
  };

  const [showAddSourceModal, setShowAddSourceModal] = useState(false);
  const [pendingNewSourceBase, setPendingNewSourceBase] = useState(null);

  const handleConfirmAddSource = (type) => {
    const base = pendingNewSourceBase || { lat: 41.3, lon: 69.24 };
    const newSrc = createDefaultSource(base.lat, base.lon, sources.length || 0);
    newSrc.type = type === "area" ? "area" : "stack";
    if (newSrc.type === "area") {
      newSrc.area_length = newSrc.area_length || 200;
      newSrc.area_width = newSrc.area_width || 100;
      newSrc.area_angle = newSrc.area_angle ?? 0;
      newSrc.area_subdivisions = newSrc.area_subdivisions || 5;
      // Для площадных (низкие/неорганизованные) — умеренная высота, холодный выброс
      newSrc.height = newSrc.height ?? 5;
    }
    setSources((prev) => [...prev, newSrc]);
    setShowAddSourceModal(false);
    setPendingNewSourceBase(null);
  };

  const handleRemoveSource = useCallback((index) => {
    setSources((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleBulkAddSources = (parsed) => {
    const city = cities.find((c) => c.name === meteo.city);
    const newSources = parsed.map((s, i) => ({
      ...createDefaultSource(city?.lat ?? 41.3, city?.lon ?? 69.24, sources.length + i),
      ...s,
      name: s.name || `Источник ${sources.length + i + 1}`,
    }));
    setSources((prev) => [...prev, ...newSources]);
  };

  const handlePickFromMap = useCallback((index) => {
    // Функциональная форма — чтобы обработчик не зависел от pickingIndex
    // и оставался стабильным (иначе рвётся React.memo у карточек).
    setPickingIndex((prev) => (prev === index ? null : index));
    setPickingEnterprise(false);
  }, []);

  const handleMapPick = (index, lat, lon) => {
    handleSourceChange(index, "lat", lat);
    handleSourceChange(index, "lon", lon);
    setPickingIndex(null);
  };

  const handleToggleBoundaryPicking = () => {
    setPickingEnterprise((v) => !v);
    setPickingIndex(null);
  };

  // Клик по карте в режиме пикинга — добавляет точку в контур, режим остаётся
  const handleEnterprisePick = (lat, lon) => {
    setEnterprise((prev) => {
      const bs = getBoundaries(prev).map((c) => [...c]);
      const idx = Math.min(activeBoundaryIdx, MAX_BOUNDARIES - 1);
      while (bs.length <= idx) bs.push([]);
      bs[idx] = [...bs[idx], { lat, lon }];
      return { ...prev, boundaries: bs, boundary: bs[0] || [] };
    });
  };

  // Редактор отдаёт весь массив контуров (объектов)
  const handleBoundaryChange = (newBoundaries) => {
    const bs = Array.isArray(newBoundaries) ? newBoundaries : [];
    setEnterprise((prev) => ({ ...prev, boundaries: bs, boundary: bs[0] || [] }));

    // Когда контур задан, переносим в центроид все источники, которые ещё стоят
    // в координатах "по умолчанию" (центр текущего города). Центроид — по всем
    // точкам всех объектов. Если источник уже двигали — оставляем как есть.
    const pts = bs.reduce((acc, c) => acc.concat(c || []), []);
    if (pts.length === 0) return;
    const cLat = pts.reduce((s, p) => s + (p.lat || 0), 0) / pts.length;
    const cLon = pts.reduce((s, p) => s + (p.lon || 0), 0) / pts.length;
    const city = cities.find((c) => c.name === meteo.city);
    setSources((prev) => prev.map((src) => {
      const isAtCityDefault =
        city &&
        Math.abs((src.lat ?? 0) - city.lat) < 1e-4 &&
        Math.abs((src.lon ?? 0) - city.lon) < 1e-4;
      return isAtCityDefault ? { ...src, lat: cLat, lon: cLon } : src;
    }));
  };

  // Принудительный перенос всех источников в центроид контура —
  // используется кнопкой "Переместить все источники в контур" и
  // авто-снапом после подтверждения импорта.
  const handleSnapSourcesToBoundary = (opts = {}) => {
    const b = allBoundaryPoints(enterprise);
    if (!b || b.length === 0) {
      if (!opts.silent) {
        setError("Сначала задайте контур предприятия в модуле «🏭 Координаты предприятия».");
      }
      return;
    }
    const cLat = b.reduce((s, p) => s + (p.lat || 0), 0) / b.length;
    const cLon = b.reduce((s, p) => s + (p.lon || 0), 0) / b.length;
    if (!opts.silent) {
      if (!window.confirm(`Переместить все ${sources.length} источников в центр контура?`)) return;
    }
    setSources((prev) => prev.map((src) => ({ ...src, lat: cLat, lon: cLon })));
  };

  // Стабильная ссылка + одно обновление стейта: маркеры на карте мемоизированы
  // и не должны пересоздаваться из-за новой функции на каждый рендер.
  const handleSourceDrag = useCallback((index, lat, lon) => {
    setSources((prev) => prev.map((src, i) => (i === index ? { ...src, lat, lon } : src)));
  }, []);

  // Добавление пользовательского вещества
  const handleAddCustomSubstance = useCallback((substance) => {
    setCustomSubstances((prev) => [...prev, substance]);
  }, []);

  // Загрузка погоды
  const [weatherLoading, setWeatherLoading] = useState(false);
  const handleLoadWeather = async () => {
    const city = cities.find((c) => c.name === meteo.city);
    if (!city) return;
    setWeatherLoading(true);
    try {
      const data = await fetchWeather(city.lat, city.lon);
      setMeteo((prev) => ({
        ...prev,
        temperature: data.temperature ?? prev.temperature,
        wind_speed: data.wind_speed ?? prev.wind_speed,
        wind_direction: data.wind_direction ?? prev.wind_direction,
        stability_class: data.stability_class ?? prev.stability_class,
      }));
    } catch {
      setError(t.weatherError);
    } finally {
      setWeatherLoading(false);
    }
  };

  // Сохранение проекта в JSON. customSubstances кладём в файл, чтобы проект
  // был самодостаточным: на другой машине справочник может не знать
  // добавленных вручную веществ.
  const handleSaveProject = () => {
    const project = { sources, meteo, grid, selectedSubstance, enterprise, customSubstances };
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${enterprise.projectNumber || "project"}_ond86.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Загрузка проекта из JSON
  const handleLoadProject = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const project = JSON.parse(ev.target.result);
          if (project.sources) setSources(project.sources.map(migrateSource));
          if (project.meteo) setMeteo(project.meteo);
          if (project.grid) setGrid(project.grid);
          if (project.selectedSubstance) setSelectedSubstance(project.selectedSubstance);
          if (project.enterprise) setEnterprise(migrateEnterprise(project.enterprise));
          // Вещества, сохранённые вместе с проектом, добавляем в пользовательский
          // справочник (без дублей по коду).
          if (Array.isArray(project.customSubstances) && project.customSubstances.length > 0) {
            setCustomSubstances((prev) => {
              const known = new Set([...substances, ...prev].map((s) => String(s.code)));
              const added = project.customSubstances.filter(
                (s) => s?.code && !known.has(String(s.code))
              );
              return added.length > 0 ? [...prev, ...added] : prev;
            });
          }
        } catch {
          setError("Ошибка чтения файла проекта");
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  // Сброс проекта в исходное состояние
  const handleResetProject = () => {
    if (!window.confirm("Сбросить проект? Все источники, метеоданные, область и данные предприятия будут очищены. Это действие нельзя отменить.")) {
      return;
    }
    setSources([createDefaultSource(41.2995, 69.2401, 0)]);
    setMeteo(DEFAULT_METEO);
    setGrid(DEFAULT_GRID);
    setSelectedSubstance(null);
    setEnterprise(DEFAULT_ENTERPRISE);
    setResult(null);
    setTables(null);
    setBaselineResult(null);
    setDisplaySubstanceCode(null);
    setError(null);
    localStorage.removeItem("ond86_autosave");
  };

  // Генерация таблиц ПДВ/ОВОС
  const handleGenerateTables = async () => {
    setTablesLoading(true);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      const payload = {
        sources: toBackendSources(sources), meteo, grid, pdk,
        substance: sources[0]?.substance || selectedSubstance,
        enterprise,
      };
      const res = await fetchTables(payload);
      setTables(res);
    } catch {
      setError("Ошибка формирования таблиц");
    } finally {
      setTablesLoading(false);
    }
  };

  // Расчёт
  const handleCalculate = async () => {
    setLoading(true);
    setError(null);
    try {
      // Минимальный ПДК среди всех выбросов всех источников (для совместимости со старым API)
      const allPdks = sources.flatMap(s => (s.emissions || []).map(e => e.pdk ?? 0.5));
      const pdk = allPdks.length ? Math.min(...allPdks) : 0.5;
      // Площадные источники разворачиваются в сетку точечных подысточников
      // на бэкенде (ОНД-86, суперпозиция). Передаём тип и геометрию как есть.
      const payload = { sources: toBackendSources(sources), meteo, grid, pdk };
      const res = await calculate(payload);
      // Замораживаем в результате вещество главного (худшего) расчёта.
      // by_substance теперь содержит результаты по всем веществам отдельно.
      const primarySub = res.by_substance?.find?.(s => s.code === res.primary_code) || res.by_substance?.[0];
      const substanceAtCalc = primarySub
        ? { code: primarySub.code, name: primarySub.name, pdk_mr: primarySub.pdk, hazard_class: primarySub.hazard_class }
        : (sources[0]?.emissions?.[0]?.substance || selectedSubstance || null);
      setResult({ ...res, _substance: substanceAtCalc, _pdk: pdk });
      // По умолчанию отображаем главное вещество
      setDisplaySubstanceCode(res.primary_code || null);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail.map(d => `${d.loc?.join(".")}: ${d.msg}`).join("; "));
      } else {
        setError(detail || e?.message || "Ошибка расчёта. Проверьте подключение к серверу.");
      }
    } finally {
      setLoading(false);
    }
  };

  // Тип карты рассеивания в PDF:
  //   "isolines" — изолинии в долях ПДК с цветной заливкой
  //   "grid"     — старая ОНД-сетка с числами концентраций в ячейках
  const [pdfMapType, setPdfMapType] = useState("isolines");

  // Экспорт PDF
  const handleExportPdf = async () => {
    if (!result) {
      setError("Сначала нажмите «Рассчитать», потом «Экспорт PDF».");
      return;
    }
    setExporting(true);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      // Передаём уже готовые результаты — бэкенд пропустит пересчёт.
      // Для типа "grid" оси не нужны (внутри сетки уже свои оси и подписи).
      // Для "isolines" — оси и заголовок включены, фон белый.
      const showAxesInPdf = pdfMapType !== "grid";
      await exportPdf({
        sources, meteo, grid, pdk,
        substance: sources[0]?.substance || selectedSubstance,
        enterprise,
        precomputed_result: result,
        map_type: pdfMapType,
        map_show_axes: showAxesInPdf,
        map_show_title: showAxesInPdf,
      });
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || "неизвестная ошибка";
      console.error("PDF export failed:", e);
      setError(`Ошибка генерации PDF: ${detail}`);
    } finally {
      setExporting(false);
    }
  };

  // Экспорт PNG карт рассеивания (для CorelDraw)
  const [exportingPng, setExportingPng] = useState(false);
  const handleExportMapPng = async () => {
    if (!result) {
      setError("Сначала нажмите «Рассчитать», потом «Скачать PNG карт».");
      return;
    }
    setExportingPng(true);
    setError(null);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      await exportMapPng({
        sources, meteo, grid, pdk,
        substance: sources[0]?.substance || selectedSubstance,
        enterprise,
        precomputed_result: result,
      });
    } catch (e) {
      const detail = e?.message || "неизвестная ошибка";
      console.error("Map PNG export failed:", e);
      setError(`Ошибка скачивания PNG: ${detail}`);
    } finally {
      setExportingPng(false);
    }
  };

  // Экспорт Excel
  const [exportingExcel, setExportingExcel] = useState(false);
  const handleExportExcel = async () => {
    setExportingExcel(true);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      await exportExcel({ sources, meteo, grid, pdk, substance: sources[0]?.substance || selectedSubstance, enterprise });
    } catch (e) {
      setError("Ошибка генерации Excel.");
    } finally {
      setExportingExcel(false);
    }
  };

  return (
    <div className="app-layout">
      {/* ===== ЛЕВАЯ ПАНЕЛЬ ===== */}
      <aside className={`sidebar ${sidebarWide ? "sidebar-wide" : ""}`}>
        <div className="sidebar-header">
          <h1 className="app-title">{t.appTitle}</h1>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button
              className="btn-lang"
              onClick={() => setSidebarWide(!sidebarWide)}
              title={sidebarWide ? "Сузить панель" : "Расширить панель"}
            >
              {sidebarWide ? "« " : " »"}
            </button>
            <button
              className="btn-editor"
              onClick={() => setShowSubstanceEditor(true)}
              title={t.substanceEditor}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
              </svg>
              {t.substanceEditor}
            </button>
            <button
              className="btn-editor"
              onClick={() => setShowBoundaryEditor(true)}
              title={t.enterpriseBoundary}
              style={boundaryPointCount ? { background: "#ECFDF5", borderColor: "#A7F3D0" } : undefined}
            >
              {t.enterpriseBoundary}
              {boundaryPointCount > 0 && (
                <span style={{
                  marginLeft: 4, background: "#047857", color: "#fff",
                  borderRadius: 8, padding: "0 5px", fontSize: 10, fontWeight: 700,
                }}>
                  {boundaryList.length > 1 ? `${boundaryList.length}об · ${boundaryPointCount}` : boundaryPointCount}
                </span>
              )}
            </button>
            <button
              className="btn-lang"
              onClick={() => setLang(lang === "ru" ? "uz" : "ru")}
            >
              {t.lang}
            </button>
          </div>
        </div>

        <div className="sidebar-scroll">
          {/* ---- Вещество и ПДК (общее для всех источников) ---- */}
          <div className="panel-section">
            <h3 className="section-title">{t.substance}</h3>
            <div className="field-row">
              <label>{t.selectSubstance}</label>
              <select
                value={selectedSubstance?.code || ""}
                onChange={(e) => {
                  const code = e.target.value;
                  if (code === "") { setSelectedSubstance(null); return; }
                  const found = allSubstances.find((s) => s.code === code);
                  if (found) {
                    setSelectedSubstance(found);
                    // Применяем выбранное вещество к ПЕРВОМУ выбросу каждого источника,
                    // если у того ещё не задано вещество. Не трогаем уже настроенные.
                    if (found.pdk_mr != null) {
                      setSources(prev => prev.map(s => {
                        const ems = Array.isArray(s.emissions) && s.emissions.length > 0
                          ? [...s.emissions]
                          : [{ substance: null, emission_gs: null, emission_ty: null, pdk: 0.5 }];
                        // Если у первого выброса нет вещества — заполняем дефолтом
                        if (!ems[0].substance) {
                          ems[0] = { ...ems[0], substance: found, pdk: found.pdk_mr };
                        }
                        return { ...s, emissions: ems };
                      }));
                    }
                  }
                }}
                style={{ fontSize: 12 }}
              >
                <option value="">-- {t.selectSubstance} --</option>
                {/* Вещество из загруженного проекта, которого нет в справочнике */}
                {selectedSubstance?.code && !allSubstances.some((s) => String(s.code) === String(selectedSubstance.code)) && (
                  <option value={selectedSubstance.code}>
                    {selectedSubstance.code} — {selectedSubstance.name} (ПДК: {selectedSubstance.pdk_mr ?? "—"})
                  </option>
                )}
                {allSubstances.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code} — {s.name} (ПДК: {s.pdk_mr ?? "—"})
                  </option>
                ))}
              </select>
            </div>
            {selectedSubstance && (
              <div style={{ fontSize: 11, color: "#64748b", padding: "2px 0 0 4px" }}>
                {t.hazardClass}: {selectedSubstance.hazard_class ?? "—"} | {t.pdkSs}: {selectedSubstance.pdk_ss ?? "—"}
              </div>
            )}
            <div className="field-row">
              <label>{t.pdkMr}</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={selectedSubstance?.pdk_mr ?? 0.5}
                onChange={(e) => {
                  const val = parseFloat(e.target.value) || 0.5;
                  setSelectedSubstance(prev => prev ? { ...prev, pdk_mr: val } : { code: "", name: "", pdk_mr: val });
                  // Применяем ПДК к первому выбросу каждого источника
                  setSources(prev => prev.map(s => {
                    const ems = Array.isArray(s.emissions) && s.emissions.length > 0
                      ? [...s.emissions]
                      : [{ substance: null, emission_gs: null, emission_ty: null, pdk: 0.5 }];
                    ems[0] = { ...ems[0], pdk: val };
                    return { ...s, emissions: ems };
                  }));
                }}
              />
            </div>
          </div>

          {/* ---- Источники ---- */}
          <div className="panel-section">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 4 }}>
              <h3 className="section-title" style={{ margin: 0 }}>{t.sources}</h3>
              <div style={{ display: "flex", gap: 4 }}>
                <button
                  className={`btn-sm ${inputMode === "cards" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setInputMode("cards")}
                  style={{ fontSize: 11, padding: "3px 8px" }}
                >
                  Карточки
                </button>
                <button
                  className={`btn-sm ${inputMode === "table" ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setInputMode("table")}
                  style={{ fontSize: 11, padding: "3px 8px" }}
                >
                  Таблица
                </button>
              </div>
            </div>

            {/* Кнопка "Переместить все источники в контур" — видна только когда контур задан */}
            {boundaryPointCount >= 3 && sources.length > 0 && (
              <button
                className="btn-secondary btn-sm"
                style={{ width: "100%", marginTop: 6, fontSize: 11, color: "#7C2D12", borderColor: "#FED7AA" }}
                onClick={handleSnapSourcesToBoundary}
                title="Установит все источники в центроид контура"
              >
                🎯 Переместить все источники в контур
              </button>
            )}

            {inputMode === "cards" ? (
              <>
                <button className="btn-secondary btn-sm" style={{ width: "100%", marginTop: 6 }} onClick={handleAddSource}>
                  {t.addSource}
                </button>
                {sources.length > COLLAPSE_THRESHOLD && (
                  <input
                    type="text"
                    placeholder="🔍 Поиск источника (название или №)"
                    value={sourceFilter}
                    onChange={(e) => {
                      setSourceFilter(e.target.value);
                      setVisibleCards(CARDS_PAGE);
                    }}
                    style={{ width: "100%", marginTop: 6, fontSize: 12, padding: "5px 8px", boxSizing: "border-box" }}
                  />
                )}
                {filteredSources.slice(0, visibleCards).map(({ src, i }) => (
                  <SourceForm
                    key={i}
                    source={src}
                    index={i}
                    onChange={handleSourceChange}
                    onEmissionChange={handleEmissionChange}
                    onAddEmission={handleAddEmission}
                    onRemoveEmission={handleRemoveEmission}
                    onRemove={handleRemoveSource}
                    onPickFromMap={handlePickFromMap}
                    substances={allSubstances}
                    onAddCustomSubstance={handleAddCustomSubstance}
                    defaultCollapsed={sources.length > COLLAPSE_THRESHOLD}
                    t={t}
                  />
                ))}
                {filteredSources.length > visibleCards && (
                  <button
                    className="btn-secondary btn-sm"
                    style={{ width: "100%", marginTop: 6, fontSize: 11 }}
                    onClick={() => setVisibleCards((c) => c + CARDS_PAGE)}
                  >
                    Показать ещё {Math.min(CARDS_PAGE, filteredSources.length - visibleCards)} (показано {visibleCards} из {filteredSources.length})
                  </button>
                )}
              </>
            ) : (
              <>
                <TableInput
                  sources={sources}
                  onChange={handleSourceChange}
                  onAdd={handleBulkAddSources}
                  onRemove={handleRemoveSource}
                  t={t}
                />
                <button className="btn-secondary btn-sm" style={{ width: "100%", marginTop: 6 }} onClick={handleAddSource}>
                  {t.addSource}
                </button>
              </>
            )}

            {/* ---- Импорт CSV/Excel ---- */}
            <ImportPanel
              onImport={(imported) => {
                const city = cities.find(c => c.name === meteo.city);
                const centerLat = city?.lat ?? 41.3;
                const centerLon = city?.lon ?? 69.24;
                const spacing = 0.002; // ~200м между источниками
                const cols = Math.ceil(Math.sqrt(imported.length));

                // Находит вещество по коду или названию из импорта.
                // Сначала по коду (точное совпадение), затем без учёта ведущих
                // нулей — Excel превращает код "0301" в число 301, срезая нули, —
                // потом по названию (case-insensitive).
                const normCode = (c) => String(c ?? "").trim().toLowerCase().replace(/\.0+$/, "");
                const stripZeros = (s) => s.replace(/^0+(?=.)/, "");
                const findSubstance = (code, name) => {
                  const q = normCode(code);
                  if (q) {
                    const byCode = allSubstances.find(s => normCode(s.code) === q);
                    if (byCode) return byCode;
                    const byCodeNoZeros = allSubstances.find(
                      s => stripZeros(normCode(s.code)) === stripZeros(q)
                    );
                    if (byCodeNoZeros) return byCodeNoZeros;
                  }
                  if (name) {
                    const lcName = String(name).trim().toLowerCase();
                    const byName = allSubstances.find(s => (s.name || "").toLowerCase() === lcName);
                    if (byName) return byName;
                  }
                  return null;
                };

                // Группируем строки по имени источника:
                // несколько строк с одним name → один источник с несколькими выбросами.
                const groups = new Map();
                imported.forEach((row, i) => {
                  const name = (row.name && String(row.name).trim()) || `Источник ${i + 1}`;
                  if (!groups.has(name)) groups.set(name, []);
                  groups.get(name).push(row);
                });

                const totalGroups = groups.size;
                const gridCols = Math.ceil(Math.sqrt(totalGroups));

                const newSources = [];
                let groupIdx = 0;
                for (const [name, rows] of groups.entries()) {
                  const first = rows[0];
                  // Авторасстановка по сетке если нет координат
                  const r = Math.floor(groupIdx / gridCols);
                  const c = groupIdx % gridCols;
                  const autoLat = centerLat + (r - Math.floor(gridCols / 2)) * spacing;
                  const autoLon = centerLon + (c - Math.floor(gridCols / 2)) * spacing;

                  // Каждая строка в группе → одна запись в emissions
                  const emissions = rows.map((row) => {
                    const sub = findSubstance(row.substance_code, row.substance_name) || selectedSubstance || null;
                    return {
                      substance: sub,
                      emission_gs: row.emission_gs ?? null,
                      emission_ty: row.emission_ty ?? null,
                      pdk: sub?.pdk_mr ?? 0.5,
                    };
                  });

                  newSources.push({
                    name,
                    lat: first.lat || autoLat,
                    lon: first.lon || autoLon,
                    height: first.height || 30,
                    diameter: first.diameter || 1.0,
                    velocity: first.velocity || 8.0,
                    temperature: first.temperature || 120,
                    emissions,
                  });
                  groupIdx += 1;
                }

                setSources((prev) => [...prev, ...newSources]);
              }}
              t={t}
            />
          </div>

          {/* ---- Метеоданные ---- */}
          <MeteoPanel
            meteo={meteo}
            cities={cities}
            onChange={setMeteo}
            onLoadWeather={handleLoadWeather}
            weatherLoading={weatherLoading}
            t={t}
          />

          {/* ---- Карточка предприятия ---- */}
          <EnterpriseCard
            enterprise={enterprise}
            onChange={setEnterprise}
            t={t}
          />

          {/* ---- Расчётная область ---- */}
          <div className="panel-section">
            <h3 className="section-title">{t.grid}</h3>
            <div className="field-row">
              <label>Длина X, м</label>
              <input
                type="number" step="500" min="500"
                value={grid.x_length}
                onChange={(e) => setGrid({ ...grid, x_length: parseFloat(e.target.value) || 7000 })}
              />
            </div>
            <div className="field-row">
              <label>Длина Y, м</label>
              <input
                type="number" step="500" min="500"
                value={grid.y_length}
                onChange={(e) => setGrid({ ...grid, y_length: parseFloat(e.target.value) || 7000 })}
              />
            </div>
            <div className="field-row">
              <label>{t.step} (100-500 м)</label>
              <input
                type="number" step="50" min="100" max="500"
                value={grid.step}
                onChange={(e) => setGrid({ ...grid, step: Math.max(100, Math.min(500, parseFloat(e.target.value) || 500)) })}
              />
            </div>
            <div className="field-row">
              <label>Источник X₀, м</label>
              <input
                type="number" step="100" min="0"
                value={grid.source_offset_x}
                onChange={(e) => setGrid({ ...grid, source_offset_x: parseFloat(e.target.value) || 0 })}
              />
            </div>
            <div className="field-row">
              <label>Источник Y₀, м</label>
              <input
                type="number" step="100" min="0"
                value={grid.source_offset_y}
                onChange={(e) => setGrid({ ...grid, source_offset_y: parseFloat(e.target.value) || 0 })}
              />
            </div>
            <button
              className="btn-secondary btn-sm"
              style={{ width: "100%", marginTop: 4, fontSize: 11 }}
              onClick={() => setGrid({ ...grid, source_offset_x: grid.x_length / 2, source_offset_y: grid.y_length / 2 })}
            >
              Источник по центру
            </button>
            <button
              className="btn-secondary btn-sm"
              style={{ width: "100%", marginTop: 4, fontSize: 11 }}
              onClick={() => setGrid(DEFAULT_GRID)}
            >
              Сбросить область (7000×7000)
            </button>
          </div>

          {/* ---- Сохранение / загрузка / сброс проекта ---- */}
          <div className="panel-section" style={{ display: "flex", gap: 6 }}>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={handleSaveProject}>
              {t.saveProject}
            </button>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={handleLoadProject}>
              {t.loadProject}
            </button>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={handleResetProject}>
              {t.resetProject || "Сбросить проект"}
            </button>
          </div>

          {/* ---- Кнопка расчёта ---- */}
          {error && (
            <div className="error-msg">{error}</div>
          )}

          <button
            className="btn-primary btn-calculate"
            onClick={handleCalculate}
            disabled={loading || sources.length === 0}
          >
            {loading ? t.calculating : t.calculate}
          </button>

          {/* ---- Переключатель отображаемого вещества (если расчёт многовеществный) ---- */}
          {result?.by_substance?.length > 1 && (
            <div className="panel-section" style={{ background: "#F0F9FF", border: "1px solid #BAE6FD", borderRadius: 6, padding: 8 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#075985", marginBottom: 6 }}>
                {t.substanceSwitcher}
              </div>
              <select
                value={displaySubstanceCode || ""}
                onChange={(e) => setDisplaySubstanceCode(e.target.value || null)}
                style={{ width: "100%", fontSize: 12, padding: "4px 6px" }}
              >
                {result.by_substance.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.name || s.code}
                    {s.exceeds_pdk ? " ⚠" : " ✓"}
                    {" "}— Cmax = {s.max_c.toFixed(4)} мг/м³
                    {s.code === result.primary_code ? " (главное)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* ---- Результаты ---- */}
          <ResultsPanel
            result={displayedResult}
            currentPdk={displayedResult?.pdk ?? 0.5}
            onExportPdf={handleExportPdf}
            exporting={exporting}
            onExportMapPng={handleExportMapPng}
            exportingPng={exportingPng}
            onExportExcel={handleExportExcel}
            exportingExcel={exportingExcel}
            pdfMapType={pdfMapType}
            onChangePdfMapType={setPdfMapType}
            t={t}
          />

          {/* ---- Сценарии (до/после) ---- */}
          {result && (
            <ScenarioPanel
              scenarioMode={scenarioMode}
              onToggle={() => setScenarioMode(!scenarioMode)}
              onSaveBaseline={() => setBaselineResult(JSON.parse(JSON.stringify(result)))}
              baselineResult={baselineResult}
              currentResult={result}
              t={t}
            />
          )}

          {/* ---- Таблицы ПДВ/ОВОС ---- */}
          {result && (
            <>
              <button
                className="btn-secondary"
                style={{ width: "100%", marginTop: 8 }}
                onClick={handleGenerateTables}
                disabled={tablesLoading}
              >
                {tablesLoading ? t.generatingTables : t.generateTables}
              </button>
              <TablesPanel tables={tables} t={t} />
            </>
          )}
        </div>
      </aside>

      {/* ===== КАРТА ===== */}
      <main className="map-area">
        <MapView
          sources={sources}
          result={displayedResult}
          pickingIndex={pickingIndex}
          onPick={handleMapPick}
          pickingEnterprise={pickingEnterprise}
          onEnterprisePick={handleEnterprisePick}
          onSourceMove={handleSourceDrag}
          cityCenter={cityCenter}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          gridStep={grid.step}
          gridXLength={grid.x_length}
          gridYLength={grid.y_length}
          sourceOffsetX={grid.source_offset_x}
          sourceOffsetY={grid.source_offset_y}
          currentPdk={displayedResult?.pdk ?? 0.5}
          meteo={meteo}
          enterprise={enterprise}
          substance={displayedResult?._substance || sources[0]?.emissions?.[0]?.substance || selectedSubstance}
          fitMapTrigger={fitMapTrigger}
        />
      </main>

      {/* ===== Справочник веществ ===== */}
      {showSubstanceEditor && (
        <SubstanceEditor
          substances={allSubstances}
          onSubstancesChanged={reloadSubstances}
          onClose={() => setShowSubstanceEditor(false)}
          t={t}
        />
      )}

      {/* ===== Редактор контура предприятия ===== */}
      {showBoundaryEditor && (
        <EnterpriseBoundaryEditor
          boundaries={boundaryList}
          activeIdx={activeBoundaryIdx}
          onActiveIdxChange={setActiveBoundaryIdx}
          maxObjects={MAX_BOUNDARIES}
          onChange={handleBoundaryChange}
          picking={pickingEnterprise}
          onTogglePicking={handleToggleBoundaryPicking}
          onFitMap={() => {
            requestFitToBoundary();
            setShowBoundaryEditor(false);
            setPickingEnterprise(false);
          }}
          onAfterImport={(importedCount) => {
            // После подтверждения импорта спрашиваем — переместить ли все
            // источники в центр контура. Это закрывает кейс, когда источники
            // заранее были раскиданы где-то в стороне, а контур теперь здесь.
            if (sources.length === 0) return;
            if (sources.length === 1 || window.confirm(
              `Импортировано ${importedCount} точек контура.\n\n` +
              `Переместить все ${sources.length} источников в центр контура? ` +
              `Это нужно, если источники сейчас не на промплощадке.`
            )) {
              handleSnapSourcesToBoundary({ silent: true });
            }
          }}
          onClose={() => {
            setShowBoundaryEditor(false);
            setPickingEnterprise(false);
          }}
          t={t}
        />
      )}
      <AddSourceModal
        visible={showAddSourceModal}
        onClose={() => setShowAddSourceModal(false)}
        onConfirm={handleConfirmAddSource}
        t={t}
      />
    </div>
  );
}
