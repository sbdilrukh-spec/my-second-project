import React, { useState } from "react";

const STACK_DEFAULTS = {
  name: "Источник 1",
  lat: 41.2995,
  lon: 69.2401,
  height: 30,
  diameter: 1.0,
  velocity: 8.0,
  temperature: 120,
};

const EMISSION_DEFAULT = {
  substance: null,
  emission_gs: 5.0,
  emission_ty: null,
  pdk: 0.5,
};

export function createDefaultSource(cityLat, cityLon, idx) {
  return {
    ...STACK_DEFAULTS,
    name: `Источник ${idx + 1}`,
    lat: cityLat ?? STACK_DEFAULTS.lat,
    lon: cityLon ?? STACK_DEFAULTS.lon,
    emissions: [{ ...EMISSION_DEFAULT }],
  };
}

// Перевод старой плоской формы (emission_gs/substance/pdk на верхнем уровне)
// в новую с массивом emissions. Идемпотентна.
export function migrateSource(s) {
  if (!s) return s;
  if (Array.isArray(s.emissions) && s.emissions.length > 0) return s;
  const flat = {
    substance: s.substance || null,
    emission_gs: s.emission_gs ?? null,
    emission_ty: s.emission_ty ?? null,
    pdk: s.pdk ?? 0.5,
  };
  return { ...s, emissions: [flat] };
}

export default function SourceForm({
  source,
  index,
  onChange,
  onEmissionChange,
  onAddEmission,
  onRemoveEmission,
  onRemove,
  onPickFromMap,
  substances,
  onAddCustomSubstance,
  t,
}) {
  const [showAddForm, setShowAddForm] = useState(null); // emIdx или null
  const [newSubstance, setNewSubstance] = useState({
    name: "", code: "", pdk_mr: "", pdk_ss: "", hazard_class: "",
  });

  const stackField = (key, label, type = "number", step = "any") => (
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

  const handleEmissionSubstanceSelect = (emIdx, code) => {
    if (code === "") {
      onEmissionChange(index, emIdx, "substance", null);
      return;
    }
    const found = substances.find((s) => s.code === code);
    if (found) {
      onEmissionChange(index, emIdx, "substance", found);
      if (found.pdk_mr != null) {
        onEmissionChange(index, emIdx, "pdk", found.pdk_mr);
      }
    }
  };

  const handleSaveCustom = (emIdx) => {
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
    onEmissionChange(index, emIdx, "substance", substance);
    if (substance.pdk_mr != null) onEmissionChange(index, emIdx, "pdk", substance.pdk_mr);
    setNewSubstance({ name: "", code: "", pdk_mr: "", pdk_ss: "", hazard_class: "" });
    setShowAddForm(null);
  };

  const emissions = Array.isArray(source.emissions) && source.emissions.length > 0
    ? source.emissions
    : [{ ...EMISSION_DEFAULT }];

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

      {/* --- Параметры трубы --- */}
      {stackField("height", t.height)}
      {stackField("diameter", t.diameter)}
      {stackField("velocity", t.velocity)}
      {stackField("temperature", t.temperature)}

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

      {/* --- Выбросы (массив веществ) --- */}
      <div style={{
        marginTop: 10, padding: "8px 8px 6px",
        border: "1px solid #E2E8F0", borderRadius: 6, background: "#F8FAFC",
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginBottom: 6, fontWeight: 600, fontSize: 12, color: "#334155",
        }}>
          <span>{t.emissionsTitle} ({emissions.length})</span>
          <button
            className="btn-sm btn-primary"
            style={{ fontSize: 11, padding: "3px 8px" }}
            onClick={() => onAddEmission(index)}
          >
            + {t.addEmission}
          </button>
        </div>

        {emissions.map((em, emIdx) => (
          <div
            key={emIdx}
            style={{
              padding: 6, marginBottom: 6, borderRadius: 5,
              background: "#fff", border: "1px solid #E2E8F0",
            }}
          >
            <div style={{
              display: "flex", justifyContent: "space-between",
              alignItems: "center", marginBottom: 4,
            }}>
              <span style={{ fontSize: 11, color: "#64748b", fontWeight: 600 }}>
                #{emIdx + 1}
                {em.substance?.name && (
                  <span style={{ marginLeft: 6, color: "#1E40AF" }}>
                    {em.substance.name}
                  </span>
                )}
              </span>
              {emissions.length > 1 && (
                <button
                  className="btn-sm"
                  style={{
                    color: "#DC2626", background: "#FEE2E2",
                    border: "1px solid #FCA5A5",
                    fontSize: 10, padding: "1px 6px",
                  }}
                  onClick={() => onRemoveEmission(index, emIdx)}
                  title={t.removeEmission}
                >
                  ✕
                </button>
              )}
            </div>

            <div className="field-row">
              <label>{t.substance}</label>
              <select
                value={em.substance?.code || ""}
                onChange={(e) => handleEmissionSubstanceSelect(emIdx, e.target.value)}
                style={{ fontSize: 11 }}
              >
                <option value="">— {t.selectSubstance} —</option>
                {substances.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.code} — {s.name} (ПДК: {s.pdk_mr ?? "—"})
                  </option>
                ))}
              </select>
            </div>

            {em.substance && (
              <div style={{ fontSize: 10, color: "#64748b", padding: "1px 0 0 4px" }}>
                {t.hazardClass}: {em.substance.hazard_class ?? "—"} | {t.pdkSs}: {em.substance.pdk_ss ?? "—"}
              </div>
            )}

            <div className="field-row">
              <label>{t.emissionGs}</label>
              <input
                type="number" step="any" min="0"
                value={em.emission_gs ?? ""}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  onEmissionChange(index, emIdx, "emission_gs", isNaN(v) ? null : v);
                }}
              />
            </div>
            <div className="field-row">
              <label>{t.emissionTy}</label>
              <input
                type="number" step="any" min="0"
                value={em.emission_ty ?? ""}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  onEmissionChange(index, emIdx, "emission_ty", isNaN(v) ? null : v);
                }}
              />
            </div>
            <div className="field-row">
              <label>{t.pdkMr}</label>
              <input
                type="number" step="0.001" min="0"
                value={em.pdk ?? 0.5}
                onChange={(e) => onEmissionChange(index, emIdx, "pdk", parseFloat(e.target.value) || 0.5)}
              />
            </div>

            {showAddForm === emIdx ? (
              <div style={{
                marginTop: 6, padding: 6,
                border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 12,
                background: "#F1F5F9",
              }}>
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
                  <button className="btn-primary btn-sm" style={{ flex: 1 }} onClick={() => handleSaveCustom(emIdx)}>{t.save}</button>
                  <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => setShowAddForm(null)}>{t.cancel}</button>
                </div>
              </div>
            ) : (
              <button
                className="btn-secondary btn-sm"
                style={{ width: "100%", marginTop: 2, fontSize: 10 }}
                onClick={() => setShowAddForm(emIdx)}
              >
                {t.customSubstance}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
