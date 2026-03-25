import React, { useState, useEffect, useCallback, useRef } from "react";
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

const DEFAULT_METEO = {
  city: "Ташкент",
  wind_speed: 2.0,
  wind_direction: 270,
  stability_class: "D",
  temperature: 13.0,
  wind_mode: "360",
};

const DEFAULT_GRID = {
  radius: 3000,
  step: 100,
};

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
  const [grid, setGrid] = useState(savedProject?.grid || DEFAULT_GRID);
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
  const [inputMode, setInputMode] = useState("cards"); // "cards" | "table"

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

  // Центр карты
  const cityCenter = (() => {
    const city = cities.find((c) => c.name === meteo.city);
    return city ? [city.lat, city.lon] : null;
  })();

  useEffect(() => {
    const city = cities.find((c) => c.name === meteo.city);
    if (!city) return;
    setSources((prev) =>
      prev.map((src, i) =>
        i === 0 ? { ...src, lat: city.lat, lon: city.lon } : src
      )
    );
  }, [meteo.city, cities]);

  const handleSourceChange = useCallback((index, key, value) => {
    setSources((prev) =>
      prev.map((src, i) => (i === index ? { ...src, [key]: value } : src))
    );
  }, []);

  const handleAddSource = () => {
    const city = cities.find((c) => c.name === meteo.city);
    setSources((prev) => [
      ...prev,
      createDefaultSource(city?.lat ?? 41.3, city?.lon ?? 69.24, prev.length),
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
  };

  const handleMapPick = (index, lat, lon) => {
    handleSourceChange(index, "lat", lat);
    handleSourceChange(index, "lon", lon);
    setPickingIndex(null);
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
      setResult(res);
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

  // Экспорт PDF
  const handleExportPdf = async () => {
    setExporting(true);
    try {
      const pdk = Math.min(...sources.map(s => s.pdk ?? 0.5));
      await exportPdf({ sources, meteo, grid, pdk, substance: sources[0]?.substance || selectedSubstance, enterprise });
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
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1 className="app-title">{t.appTitle}</h1>
          <button
            className="btn-lang"
            onClick={() => setLang(lang === "ru" ? "uz" : "ru")}
          >
            {t.lang}
          </button>
        </div>

        <div className="sidebar-scroll">
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
                setSources((prev) => [...prev, ...imported.map((s, i) => ({
                  name: s.name || `Импорт ${prev.length + i + 1}`,
                  lat: s.lat || (cities.find(c => c.name === meteo.city)?.lat ?? 41.3),
                  lon: s.lon || (cities.find(c => c.name === meteo.city)?.lon ?? 69.24),
                  height: s.height || 30,
                  diameter: s.diameter || 1.0,
                  velocity: s.velocity || 8.0,
                  temperature: s.temperature || 120,
                  emission_gs: s.emission_gs || null,
                  emission_ty: s.emission_ty || null,
                }))]);
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
              <label>{t.radius}</label>
              <input
                type="number" step="100" min="100"
                value={grid.radius}
                onChange={(e) => setGrid({ ...grid, radius: parseFloat(e.target.value) || 1000 })}
              />
            </div>
            <div className="field-row">
              <label>{t.step}</label>
              <input
                type="number" step="10" min="10"
                value={grid.step}
                onChange={(e) => setGrid({ ...grid, step: parseFloat(e.target.value) || 50 })}
              />
            </div>
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
          onSourceMove={handleSourceDrag}
          cityCenter={cityCenter}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          gridStep={grid.step}
          gridRadius={grid.radius}
          currentPdk={Math.min(...sources.map(s => s.pdk ?? 0.5))}
          meteo={meteo}
          enterprise={enterprise}
          substance={sources[0]?.substance || selectedSubstance}
        />
      </main>
    </div>
  );
}
