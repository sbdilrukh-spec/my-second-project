import React, { useState } from "react";

export default function SubstancePanel({
  substances,
  selectedSubstance,
  pdk,
  onSelect,
  onPdkChange,
  onAddCustom,
  t,
}) {
  const [showAddForm, setShowAddForm] = useState(false);
  const [newSubstance, setNewSubstance] = useState({
    name: "",
    code: "",
    pdk_mr: "",
    pdk_ss: "",
    hazard_class: "",
  });

  const handleSelectChange = (e) => {
    const code = e.target.value;
    if (code === "") {
      onSelect(null);
      return;
    }
    const found = substances.find((s) => s.code === code);
    if (found) {
      onSelect(found);
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
    onAddCustom(substance);
    onSelect(substance);
    setNewSubstance({ name: "", code: "", pdk_mr: "", pdk_ss: "", hazard_class: "" });
    setShowAddForm(false);
  };

  return (
    <div className="panel-section">
      <h3 className="section-title">{t.substance}</h3>

      <div className="field-row">
        <label>{t.selectSubstance}</label>
        <select
          value={selectedSubstance?.code || ""}
          onChange={handleSelectChange}
        >
          <option value="">— {t.selectSubstance} —</option>
          {substances.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code} — {s.name} (ПДК: {s.pdk_mr ?? "—"})
            </option>
          ))}
        </select>
      </div>

      {selectedSubstance && (
        <div className="substance-info">
          <div className="field-row">
            <span style={{ color: "#64748b", fontSize: 12 }}>
              {t.hazardClass}: {selectedSubstance.hazard_class ?? "—"} |{" "}
              {t.pdkSs}: {selectedSubstance.pdk_ss ?? "—"}
            </span>
          </div>
        </div>
      )}

      <div className="field-row">
        <label>{t.pdkMr}</label>
        <input
          type="number"
          step="0.01"
          min="0"
          value={pdk}
          onChange={(e) => onPdkChange(parseFloat(e.target.value) || 0.5)}
        />
      </div>

      {!showAddForm ? (
        <button
          className="btn-secondary btn-sm"
          style={{ width: "100%", marginTop: 4 }}
          onClick={() => setShowAddForm(true)}
        >
          {t.customSubstance}
        </button>
      ) : (
        <div className="custom-substance-form" style={{ marginTop: 8, padding: 8, border: "1px solid #e2e8f0", borderRadius: 6 }}>
          <div className="field-row">
            <label>{t.substanceName} *</label>
            <input
              type="text"
              value={newSubstance.name}
              onChange={(e) => setNewSubstance({ ...newSubstance, name: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.substanceCode}</label>
            <input
              type="text"
              value={newSubstance.code}
              onChange={(e) => setNewSubstance({ ...newSubstance, code: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.pdkMr} *</label>
            <input
              type="number"
              step="0.001"
              value={newSubstance.pdk_mr}
              onChange={(e) => setNewSubstance({ ...newSubstance, pdk_mr: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.pdkSs}</label>
            <input
              type="number"
              step="0.001"
              value={newSubstance.pdk_ss}
              onChange={(e) => setNewSubstance({ ...newSubstance, pdk_ss: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.hazardClass}</label>
            <select
              value={newSubstance.hazard_class}
              onChange={(e) => setNewSubstance({ ...newSubstance, hazard_class: e.target.value })}
            >
              <option value="">—</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button className="btn-primary btn-sm" style={{ flex: 1 }} onClick={handleSaveCustom}>
              {t.save}
            </button>
            <button className="btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => setShowAddForm(false)}>
              {t.cancel}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
