import React from "react";

const DEFAULTS = {
  name: "Источник 1",
  lat: 41.2995,
  lon: 69.2401,
  height: 30,
  diameter: 1.0,
  velocity: 8.0,
  temperature: 120,
  emission_gs: 5.0,
  emission_ty: null,
};

export function createDefaultSource(cityLat, cityLon, idx) {
  return {
    ...DEFAULTS,
    name: `Источник ${idx + 1}`,
    lat: cityLat ?? DEFAULTS.lat,
    lon: cityLon ?? DEFAULTS.lon,
  };
}

export default function SourceForm({ source, index, onChange, onRemove, onPickFromMap, t }) {
  const field = (key, label, type = "number", step = "any") => (
    <div className="field-row">
      <label>{label}</label>
      <input
        type={type}
        step={step}
        value={source[key] ?? ""}
        onChange={(e) =>
          onChange(index, key, type === "number" ? parseFloat(e.target.value) || 0 : e.target.value)
        }
      />
    </div>
  );

  return (
    <div className="source-card">
      <div className="source-header">
        <input
          className="source-name-input"
          type="text"
          value={source.name}
          onChange={(e) => onChange(index, "name", e.target.value)}
        />
        <button className="btn-danger btn-sm" onClick={() => onRemove(index)}>
          {t.removeSource}
        </button>
      </div>

      {field("height", t.height)}
      {field("diameter", t.diameter)}
      {field("velocity", t.velocity)}
      {field("temperature", t.temperature)}

      <div className="field-row">
        <label>{t.emissionGs}</label>
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="number"
            step="any"
            placeholder="г/с"
            value={source.emission_gs ?? ""}
            onChange={(e) => onChange(index, "emission_gs", parseFloat(e.target.value) || null)}
            style={{ flex: 1 }}
          />
          <span style={{ alignSelf: "center", color: "#64748b", fontSize: 12 }}>{t.emissionTy}</span>
          <input
            type="number"
            step="any"
            placeholder="т/год"
            value={source.emission_ty ?? ""}
            onChange={(e) => onChange(index, "emission_ty", parseFloat(e.target.value) || null)}
            style={{ flex: 1 }}
          />
        </div>
      </div>

      <div className="field-row">
        <label>{t.sourcePos}</label>
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="number"
            step="any"
            placeholder={t.lat}
            value={source.lat ?? ""}
            onChange={(e) => onChange(index, "lat", parseFloat(e.target.value) || 0)}
            style={{ flex: 1 }}
          />
          <input
            type="number"
            step="any"
            placeholder={t.lon}
            value={source.lon ?? ""}
            onChange={(e) => onChange(index, "lon", parseFloat(e.target.value) || 0)}
            style={{ flex: 1 }}
          />
        </div>
      </div>
      <button className="btn-secondary btn-sm" style={{ marginTop: 4, width: "100%" }}
        onClick={() => onPickFromMap(index)}>
        📍 {t.clickMap}
      </button>
    </div>
  );
}
