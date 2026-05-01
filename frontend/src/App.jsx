import React, { useState, useEffect, useCallback, useRef } from "react";
import html2canvas from "html2canvas";
import { fetchCities, fetchSubstances, fetchWeather, calculate, fetchTables, exportPdf, exportExcel } from "./api.js";
import { translations } from "./i18n.js";
import SourceForm, { createDefaultSource } from "./components/SourceForm.jsx";
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
  const savedProject = (() => {
    try { return JSON.parse(localStorage.getItem("ond86_autosave")); } catch { return null; }
  })();

  const [cities, setCities] = useState([]);
  const [substances, setSubstances] = useState([]);
  const [meteo, setMeteo] = useState(savedProject?.meteo || DEFAULT_METEO);
  const [grid, setGrid] = useState(migrateGrid(savedProject?.grid) || DEFAULT_GRID);
  const [selectedSubstance, setSelectedSubstance] = useState(savedProject?.selectedSubstance || null);
  const [sources, setSources] = useState(savedProject?.sources || [createDefaultSource(41.2995, 69.2401, 0)]);
  const [enterprise, setEnterprise] = useState(savedProject?.enterprise || DEFAULT_ENTERPRISE);

  const [result, setResult] = useState(null);
  const [tables, setTables] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tablesLoading, setTablesLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("heatmap");

  const [pickingIndex, setPickingIndex] = useState(null);
  const [pickingEnterprise, setPickingEnterprise] = useState(false);
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

  const allSubstances = [...substances, ...customSubstances];

  // Substance editor modal
  const [showSubstanceEditor, setShowSubstanceEditor] = useState(false);
  // Enterprise boundary editor modal
  const [showBoundaryEditor, setShowBoundaryEditor] = useState(false);

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

  // Центроид контура предприятия — null если контур пуст
  const enterpriseCentroid = (() => {
    const b = enterprise.boundary;
    if (!b || b.length === 0) return null;
    const lat = b.reduce((s, p) => s + (p.lat || 0), 0) / b.length;
    const lon = b.reduce((s, p) => s + (p.lon || 0), 0) / b.length;
    return { lat, lon };
  })();

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
    setSources((prev) =>
      prev.map((src, i) => (i === index ? { ...src, [key]: value } : src))
    );
  }, []);

  const handleAddSource = () => {
    const city = cities.find((c) => c.name === meteo.city);
    // Приоритет: центроид контура предприятия → центр города → дефолт
    const baseLat = enterpriseCentroid?.lat ?? city?.lat ?? 41.3;
    const baseLon = enterpriseCentroid?.lon ?? city?.lon ?? 69.24;
    setSources((prev) => [
      ...prev,
      createDefaultSource(baseLat, baseLon, prev.length),
    ]);
  };

  const handleRemoveSource = (index) => {
    setSources((prev) => prev.filter((_, i) => i !== index));
  };

  const handleBulkAddSources = (parsed) => {
    const city = cities.find((c) => c.name === meteo.city);
    const newSources = parsed.map((s, i) => ({
      ...createDefaultSource(city?.lat ?? 41.3, city?.lon ?? 69.24, sources.length + i),
      ...s,
      name: s.name || `Источник ${sources.length + i + 1}`,
    }));
    setSources((prev) => [...prev, ...newSources]);
  };

  const handlePickFromMap = (index) => {
    setPickingIndex(pickingIndex === index ? null : index);
    setPickingEnterprise(false);
  };

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
    setEnterprise((prev) => ({
      ...prev,
      boundary: [...(prev.boundary || []), { lat, lon }],
    }));
  };

  const handleBoundaryChange = (newBoundary) => {
    setEnterprise((prev) => ({ ...prev, boundary: newBoundary }));

    // Когда контур задан, переносим в центроид все источники,
    // которые ещё стоят в координатах "по умолчанию" (центр текущего города).
    // Если пользователь уже двигал источник — оставляем где есть.
    if (!newBoundary || newBoundary.length === 0) return;
    const cLat = newBoundary.reduce((s, p) => s + (p.lat || 0), 0) / newBoundary.length;
    const cLon = newBoundary.reduce((s, p) => s + (p.lon || 0), 0) / newBoundary.length;
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
  // используется кнопкой "Переместить все источники в контур".
  // В отличие от авто-снапа, двигает источники независимо от того,
  // где они стоят сейчас.
  const handleSnapSourcesToBoundary = () => {
    const b = enterprise.boundary;
    if (!b || b.length === 0) {
      setError("Сначала задайте контур предприятия в модуле «🏭 Координаты предприятия».");
      return;
    }
    const cLat = b.reduce((s, p) => s + (p.lat || 0), 0) / b.length;
    const cLon = b.reduce((s, p) => s + (p.lon || 0), 0) / b.length;
    if (!window.confirm(`Переместить все ${sources.length} источников в центр контура?`)) return;
    setSources((prev) => prev.map((src) => ({ ...src, lat: cLat, lon: cLon })));
  };

  const handleSourceDrag = (index, lat, lon) => {
    handleSourceChange(index, "lat", lat);
    handleSourceChange(index, "lon", lon);
  };

  // Добавление пользовательского вещества
  const handleAddCustomSubstance = (substance) => {
    setCustomSubstances((prev) => [...prev, substance]);
  };

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

  // Сохранение проекта в JSON
  const handleSaveProject = () => {
    const project = { sources, meteo, grid, selectedSubstance, enterprise };
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
          if (project.sources) setSources(project.sources);
          if (project.meteo) setMeteo(project.meteo);
          if (project.grid) setGrid(project.grid);
          if (project.selectedSubstance) setSelectedSubstance(project.selectedSubstance);
          if (project.enterprise) setEnterprise(project.enterprise);
        } catch {
          setError("Ошибка чтения файла проекта");
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  // Генерация таблиц ПДВ/ОВОС
  const handleGenerateTables = async () => {
    setTablesLoading(true);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      const payload = {
        sources, meteo, grid, pdk,
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
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      const payload = { sources, meteo, grid, pdk };
      const res = await calculate(payload);
      // Замораживаем в результате вещество, с которым считали — иначе при смене
      // выбора в дропдауне заголовок съезжает, а цифры остаются от старого расчёта.
      const substanceAtCalc = sources[0]?.substance || selectedSubstance || null;
      setResult({ ...res, _substance: substanceAtCalc, _pdk: pdk });
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

  // Снимок текущего вида Leaflet → base64 PNG
  // Возвращает строку "data:image/png;base64,..." или null при ошибке.
  const captureMapSnapshot = async () => {
    const mapEl = document.querySelector(".leaflet-container");
    if (!mapEl) return null;
    try {
      const canvas = await html2canvas(mapEl, {
        useCORS: true,
        allowTaint: false,
        backgroundColor: null,
        logging: false,
        // Высокое DPI для качественной печати в PDF
        scale: Math.min(2, window.devicePixelRatio || 1),
      });
      return canvas.toDataURL("image/png");
    } catch (err) {
      console.warn("Не удалось захватить карту:", err);
      return null;
    }
  };

  // Экспорт PDF
  const handleExportPdf = async () => {
    setExporting(true);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      const mapSnapshot = await captureMapSnapshot();
      await exportPdf({
        sources, meteo, grid, pdk,
        substance: sources[0]?.substance || selectedSubstance,
        enterprise,
        map_snapshot: mapSnapshot,
      });
    } catch (e) {
      setError("Ошибка генерации PDF.");
    } finally {
      setExporting(false);
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
              style={enterprise.boundary?.length ? { background: "#ECFDF5", borderColor: "#A7F3D0" } : undefined}
            >
              {t.enterpriseBoundary}
              {enterprise.boundary?.length > 0 && (
                <span style={{
                  marginLeft: 4, background: "#047857", color: "#fff",
                  borderRadius: 8, padding: "0 5px", fontSize: 10, fontWeight: 700,
                }}>
                  {enterprise.boundary.length}
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
                    // Применить ПДК ко всем источникам
                    if (found.pdk_mr != null) {
                      setSources(prev => prev.map(s => ({ ...s, pdk: found.pdk_mr, substance: found })));
                    }
                  }
                }}
                style={{ fontSize: 12 }}
              >
                <option value="">-- {t.selectSubstance} --</option>
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
                  setSources(prev => prev.map(s => ({ ...s, pdk: val })));
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
            {enterprise.boundary?.length >= 3 && sources.length > 0 && (
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
                {sources.map((src, i) => (
                  <SourceForm
                    key={i}
                    source={src}
                    index={i}
                    onChange={handleSourceChange}
                    onRemove={handleRemoveSource}
                    onPickFromMap={handlePickFromMap}
                    substances={allSubstances}
                    onAddCustomSubstance={handleAddCustomSubstance}
                    t={t}
                  />
                ))}
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
                // Сначала по коду (точное совпадение), потом по названию (case-insensitive).
                const findSubstance = (code, name) => {
                  if (code) {
                    const byCode = allSubstances.find(s => String(s.code) === String(code));
                    if (byCode) return byCode;
                  }
                  if (name) {
                    const lcName = String(name).trim().toLowerCase();
                    const byName = allSubstances.find(s => (s.name || "").toLowerCase() === lcName);
                    if (byName) return byName;
                  }
                  return null;
                };

                setSources((prev) => [...prev, ...imported.map((s, i) => {
                  // Авторасстановка по сетке если нет координат
                  const row = Math.floor(i / cols);
                  const col = i % cols;
                  const autoLat = centerLat + (row - Math.floor(cols / 2)) * spacing;
                  const autoLon = centerLon + (col - Math.floor(cols / 2)) * spacing;

                  // Подтягиваем вещество из импорта (колонки "Код вещества" / "Название вещества"),
                  // если не нашли — fallback к глобально выбранному.
                  const importedSub = findSubstance(s.substance_code, s.substance_name);
                  const subForSource = importedSub || selectedSubstance || null;

                  return {
                    name: s.name || `Источник ${prev.length + i + 1}`,
                    lat: s.lat || autoLat,
                    lon: s.lon || autoLon,
                    height: s.height || 30,
                    diameter: s.diameter || 1.0,
                    velocity: s.velocity || 8.0,
                    temperature: s.temperature || 120,
                    emission_gs: s.emission_gs || null,
                    emission_ty: s.emission_ty || null,
                    pdk: subForSource?.pdk_mr ?? 0.5,
                    substance: subForSource,
                  };
                })]);
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

          {/* ---- Сохранение / загрузка проекта ---- */}
          <div className="panel-section" style={{ display: "flex", gap: 6 }}>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={handleSaveProject}>
              {t.saveProject}
            </button>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={handleLoadProject}>
              {t.loadProject}
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

          {/* ---- Результаты ---- */}
          <ResultsPanel
            result={result}
            currentPdk={Math.min(...sources.map(s => s.pdk ?? 0.5))}
            onExportPdf={handleExportPdf}
            exporting={exporting}
            onExportExcel={handleExportExcel}
            exportingExcel={exportingExcel}
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
          result={result}
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
          currentPdk={Math.min(...sources.map(s => s.pdk ?? 0.5))}
          meteo={meteo}
          enterprise={enterprise}
          substance={result?._substance || sources[0]?.substance || selectedSubstance}
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
          boundary={enterprise.boundary || []}
          onChange={handleBoundaryChange}
          picking={pickingEnterprise}
          onTogglePicking={handleToggleBoundaryPicking}
          onClose={() => {
            setShowBoundaryEditor(false);
            setPickingEnterprise(false);
          }}
          t={t}
        />
      )}
    </div>
  );
}
