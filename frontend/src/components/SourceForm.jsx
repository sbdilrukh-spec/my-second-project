import React, { useState } from "react";

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
  substance: null,
  pdk: 0.5,
};

export function createDefaultSource(cityLat, cityLon, idx) {
  return {
    ...DEFAULTS,
    name: `Источник ${idx + 1}`,
    lat: cityLat ?? DEFAULTS.lat,
    lon: cityLon ?? DEFAULTS.lon,
  };
}

export default function SourceForm({ source, index, onChange, onRemove, onPickFromMap, substances, onAddCustomSubstance, t }) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSubstance, setNewSubstance] = useState({
    name: "", code: "", pdk_mr: "", pdk_ss: "", hazard_class: "",
  });

  const field = (key, label, type = "number", step = "any") => (
    <div className="field-row">
      <label>{label}</label>
      <input
        type={type}
        step={step}
        value={source[key] ?? ""}
        onChange={(e) => {
          if (type === "number") {
            const v = parseFloat(e.target.value);
            onChange(index, key, isNaN(v) ? null : v);
          } else {
            onChange(index, key, e.target.value);
          }
        }}
      />
    </div>
  );

  const handleSubstanceSelect = (e) => {
    const code = e.target.value;
    if (code === "") {
      onChange(index, "substance", null);
      return;
    }
    const found = substances.find((s) => s.code === code);
    if (found) {
      onChange(index, "substance", found);
      if (found.pdk_mr != null) {
        onChange(index, "pdk", found.pdk_mr);
      }
    }
  };

  const handleSaveCustom = () => {
    if (!newSubstance.name || !newSubstance.pdk_mr) return;
    const substance = {
      code: newSubstance.code || `USER_${Date.now()}`,
      name: newSubstance.name,
      pdk_mr: parseFloat(newSubstance.pdk_mr) || null,
      pdk_ss: parseFloat(newSubstance.pdk_ss) || null,
      hazard_class: newSubstance.hazard_class ? parseInt(newSubstance.hazard_class) : null,
      custom: true,
    };
    if (onAddCustomSubstance) onAddCustomSubstance(substance);
    onChange(index, "substance", substance);
    if (substance.pdk_mr != null) onChange(index, "pdk", substance.pdk_mr);
    setNewSubstance({ name: "", code: "", pdk_mr: "", pdk_ss: "", hazard_class: "" });
    setShowAddForm(false);
  };

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

      {field("emission_gs", t.emissionGs)}
      {field("emission_ty", t.emissionTy)}

      {/* --- Вещество и ПДК --- */}
      <div className="field-row">
        <label>{t.substance}</label>
        <select
          value={source.substance?.code || ""}
          onChange={handleSubstanceSelect}
          style={{ fontSize: 12 }}
        >
          <option value="">— {t.selectSubstance} —</option>
          {substances.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code} — {s.name} (ПДК: {s.pdk_mr ?? "—"})
            </option>
          ))}
        </select>
      </div>

      {source.substance && (
        <div style={{ fontSize: 11, color: "#64748b", padding: "2px 0 0 4px" }}>
          {t.hazardClass}: {source.substance.hazard_class ?? "—"} | {t.pdkSs}: {source.substance.pdk_ss ?? "—"}
        </div>
      )}

      <div className="field-row">
        <label>{t.pdkMr}</label>
        <input
          type="number"
          step="0.01"
          min="0"
          value={source.pdk ?? 0.5}
          onChange={(e) => onChange(index, "pdk", parseFloat(e.target.value) || 0.5)}
        />
      </div>

      {!showAddForm ? (
        <button
          className="btn-secondary btn-sm"
          style={{ width: "100%", marginTop: 2, fontSize: 11 }}
          onClick={() => setShowAddForm(true)}
        >
          {t.customSubstance}
        </button>
      ) : (
        <div style={{ marginTop: 6, padding: 6, border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12 }}>
          <div className="field-row">
            <label>{t.substanceName} *</label>
            <input type="text" value={newSubstance.name}
              onChange={(e) => setNewSubstance({ ...newSubstance, name: e.target.value })} />
          </div>
          <div className="field-row">
            <label>{t.substanceCode}</label>
            <input type="text" value={newSubstance.code}
              onChange={(e) => setNewSubstance({ ...newSubstance, code: e.target.value })} />
          </div>
          <div className="field-row">
            <label>{t.pdkMr} *</label>
            <input type="number" step="0.001" value={newSubstance.pdk_mr}
              onChange={(e) => setNewSubstance({ ...newSubstance, pdk_mr: e.target.value })} />
          </div>
          <div className="field-row">
            <label>{t.pdkSs}</label>
            <input type="number" step="0.001" value={newSubstance.pdk_ss}
              onChange={(e) => setNewSubstance({ ...newSubstance, pdk_ss: e.target.value })} />
          </div>
          <div className="field-row">
            <label>{t.hazardClass}</label>
            <select value={newSubstance.hazard_class}
              onChange={(e) => setNewSubstance({ ...newSubstance, hazard_class: e.target.value })}>
              <option value="">—</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
            <button className="btn-primary btn-sm" style={{ flex: 1 }} onClick={handleSaveCustom}>{t.save}</button>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => setShowAddForm(false)}>{t.cancel}</button>
          </div>
        </div>
      )}

      {/* --- Координаты --- */}
      <div className="field-row" style={{ marginTop: 6 }}>
        <label>{t.sourcePos}</label>
        <div style={{ display: "flex", gap: 6 }}>
          <input
            type="number" step="any" placeholder={t.lat}
            value={source.lat ?? ""}
            onChange={(e) => onChange(index, "lat", parseFloat(e.target.value) || 0)}
            style={{ flex: 1 }}
          />
          <input
            type="number" step="any" placeholder={t.lon}
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
