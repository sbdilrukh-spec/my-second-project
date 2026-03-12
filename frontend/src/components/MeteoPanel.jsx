import React from "react";

const STABILITY_CLASSES = ["A", "B", "C", "D", "E", "F"];

export default function MeteoPanel({ meteo, cities, onChange, onLoadWeather, weatherLoading, t }) {
  const set = (key, val) => onChange({ ...meteo, [key]: val });

  const stabilityLabel = (cls) => {
    const map = {
      A: t.stabilityA,
      B: t.stabilityB,
      C: t.stabilityC,
      D: t.stabilityD,
      E: t.stabilityE,
      F: t.stabilityF,
    };
    return map[cls] || cls;
  };

  return (
    <div className="panel-section">
      <h3 className="section-title">{t.meteo}</h3>

      <div className="field-row">
        <label>{t.city}</label>
        <select
          value={meteo.city}
          onChange={(e) => {
            const cityName = e.target.value;
            const cityData = cities.find((c) => c.name === cityName);
            onChange({
              ...meteo,
              city: cityName,
              temperature: cityData ? Math.round(cityData.T_avg * 10) / 10 : meteo.temperature,
            });
          }}
        >
          {cities.map((c) => (
            <option key={c.name} value={c.name}>{c.name}</option>
          ))}
        </select>
      </div>

      {/* Кнопка загрузки погоды */}
      <button
        className="btn-secondary btn-sm"
        style={{ width: "100%", marginBottom: 8 }}
        onClick={onLoadWeather}
        disabled={weatherLoading}
      >
        {weatherLoading ? t.loadingWeather : t.loadWeather}
      </button>

      {/* Режим направления ветра */}
      <div className="field-row">
        <label>{t.windMode}</label>
        <select
          value={meteo.wind_mode || "360"}
          onChange={(e) => set("wind_mode", e.target.value)}
        >
          <option value="360">{t.windMode360}</option>
          <option value="single">{t.windModeSingle}</option>
        </select>
      </div>

      <div className="field-row">
        <label>{t.windSpeed}</label>
        <input
          type="number" step="0.1" min="0.5"
          value={meteo.wind_speed}
          onChange={(e) => set("wind_speed", parseFloat(e.target.value) || 1)}
        />
      </div>

      {meteo.wind_mode === "single" && (
        <div className="field-row">
          <label>{t.windDirection}</label>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="number" step="1" min="0" max="360"
              value={meteo.wind_direction}
              onChange={(e) => set("wind_direction", parseFloat(e.target.value) || 0)}
              style={{ flex: 1 }}
            />
            <span style={{ fontSize: 22 }}>{dirArrow(meteo.wind_direction)}</span>
          </div>
        </div>
      )}

      <div className="field-row">
        <label>{t.stabilityClass}</label>
        <select
          value={meteo.stability_class}
          onChange={(e) => set("stability_class", e.target.value)}
        >
          {STABILITY_CLASSES.map((cls) => (
            <option key={cls} value={cls}>{stabilityLabel(cls)}</option>
          ))}
        </select>
      </div>

      <div className="field-row">
        <label>{t.ambientTemp}</label>
        <input
          type="number" step="0.1"
          value={meteo.temperature}
          onChange={(e) => set("temperature", parseFloat(e.target.value) || 0)}
        />
      </div>
    </div>
  );
}

function dirArrow(deg) {
  const dirs = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"];
  const idx = Math.round(((deg + 180) % 360) / 45) % 8;
  return dirs[idx];
}
