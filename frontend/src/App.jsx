import React, { useState, useEffect, useCallback } from "react";
import { fetchCities, calculate, exportPdf } from "./api.js";
import { translations } from "./i18n.js";
import SourceForm, { createDefaultSource } from "./components/SourceForm.jsx";
import MeteoPanel from "./components/MeteoPanel.jsx";
import MapView from "./components/MapView.jsx";
import ResultsPanel from "./components/ResultsPanel.jsx";

const DEFAULT_METEO = {
  city: "Ташкент",
  wind_speed: 2.0,
  wind_direction: 270,
  stability_class: "D",
  temperature: 13.0,
};

const DEFAULT_GRID = {
  radius: 3000,
  step: 100,
};

export default function App() {
  const [lang, setLang] = useState("ru");
  const t = translations[lang];

  const [cities, setCities] = useState([]);
  const [meteo, setMeteo] = useState(DEFAULT_METEO);
  const [grid, setGrid] = useState(DEFAULT_GRID);
  const [pdk, setPdk] = useState(0.5);
  const [sources, setSources] = useState([createDefaultSource(41.2995, 69.2401, 0)]);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("heatmap"); // "heatmap" | "grid"

  // Индекс источника, для которого ждём клик на карте
  const [pickingIndex, setPickingIndex] = useState(null);

  // Загрузка городов
  useEffect(() => {
    fetchCities()
      .then(setCities)
      .catch(() => {
        // Если бэкенд недоступен — fallback список
        setCities([
          { name: "Ташкент", lat: 41.2995, lon: 69.2401, A: 200, T_avg: 13.1 },
          { name: "Навои", lat: 40.0839, lon: 65.3792, A: 220, T_avg: 14.0 },
          { name: "Самарканд", lat: 39.649, lon: 66.975, A: 200, T_avg: 12.7 },
          { name: "Бухара", lat: 39.7747, lon: 64.4286, A: 220, T_avg: 14.2 },
          { name: "Фергана", lat: 40.3834, lon: 71.7864, A: 160, T_avg: 12.5 },
        ]);
      });
  }, []);

  // Центр карты — по выбранному городу
  const cityCenter = (() => {
    const city = cities.find((c) => c.name === meteo.city);
    return city ? [city.lat, city.lon] : null;
  })();

  // При смене города — обновить позиции источников к центру города
  useEffect(() => {
    const city = cities.find((c) => c.name === meteo.city);
    if (!city) return;
    setSources((prev) =>
      prev.map((src, i) =>
        i === 0 ? { ...src, lat: city.lat, lon: city.lon } : src
      )
    );
  }, [meteo.city, cities]);

  // --- Изменение поля источника ---
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

  // --- Клик на карте для позиционирования источника ---
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

  // --- Расчёт ---
  const handleCalculate = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        sources,
        meteo,
        grid,
        pdk,
      };
      const res = await calculate(payload);
      setResult(res);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (Array.isArray(detail)) {
        // Pydantic validation errors — собираем в читаемый текст
        setError(detail.map(d => `${d.loc?.join(".")}: ${d.msg}`).join("; "));
      } else {
        setError(detail || e?.message || "Ошибка расчёта. Проверьте подключение к серверу.");
      }
    } finally {
      setLoading(false);
    }
  };

  // --- Экспорт PDF ---
  const handleExportPdf = async () => {
    setExporting(true);
    try {
      await exportPdf({ sources, meteo, grid, pdk });
    } catch (e) {
      setError("Ошибка генерации PDF.");
    } finally {
      setExporting(false);
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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 className="section-title" style={{ margin: 0 }}>{t.sources}</h3>
              <button className="btn-secondary btn-sm" onClick={handleAddSource}>
                {t.addSource}
              </button>
            </div>

            {sources.map((src, i) => (
              <SourceForm
                key={i}
                source={src}
                index={i}
                onChange={handleSourceChange}
                onRemove={handleRemoveSource}
                onPickFromMap={handlePickFromMap}
                t={t}
              />
            ))}
          </div>

          {/* ---- Метеоданные ---- */}
          <MeteoPanel
            meteo={meteo}
            cities={cities}
            onChange={setMeteo}
            t={t}
          />

          {/* ---- Загрязняющее вещество ---- */}
          <div className="panel-section">
            <h3 className="section-title">Загрязняющее вещество</h3>
            <div className="field-row">
              <label>{t.pdk}</label>
              <input
                type="number" step="0.01" min="0"
                value={pdk}
                onChange={(e) => setPdk(parseFloat(e.target.value) || 0.5)}
              />
            </div>
          </div>

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
            onExportPdf={handleExportPdf}
            exporting={exporting}
            t={t}
          />
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
        />
      </main>
    </div>
  );
}
