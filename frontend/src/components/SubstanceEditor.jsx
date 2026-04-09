import React, { useState, useMemo } from "react";
import { addSubstance, updateSubstance, deleteSubstance } from "../api.js";

const EMPTY_FORM = {
  code: "",
  name: "",
  pdk_mr: "",
  pdk_ss: "",
  hazard_class: "",
  F: "1.0",
};

export default function SubstanceEditor({ substances, onSubstancesChanged, onClose, t }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all"); // "all" | "custom"
  const [editingCode, setEditingCode] = useState(null); // code of substance being edited
  const [formData, setFormData] = useState(EMPTY_FORM);
  const [showAddForm, setShowAddForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  // Filtered and searched substances
  const filtered = useMemo(() => {
    let list = substances;
    if (filter === "custom") {
      list = list.filter((s) => s.custom);
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      list = list.filter(
        (s) =>
          s.code.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q)
      );
    }
    return list;
  }, [substances, search, filter]);

  const showSuccess = (msg) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 2500);
  };

  // --- Add ---
  const handleOpenAdd = () => {
    setEditingCode(null);
    setFormData(EMPTY_FORM);
    setShowAddForm(true);
    setError(null);
  };

  // --- Edit ---
  const handleOpenEdit = (sub) => {
    setShowAddForm(false);
    setEditingCode(sub.code);
    setFormData({
      code: sub.code,
      name: sub.name,
      pdk_mr: sub.pdk_mr != null ? String(sub.pdk_mr) : "",
      pdk_ss: sub.pdk_ss != null ? String(sub.pdk_ss) : "",
      hazard_class: sub.hazard_class != null ? String(sub.hazard_class) : "",
      F: sub.F != null ? String(sub.F) : "1.0",
    });
    setError(null);
  };

  const handleCancelEdit = () => {
    setEditingCode(null);
    setShowAddForm(false);
    setFormData(EMPTY_FORM);
    setError(null);
  };

  // --- Save (add or update) ---
  const handleSave = async () => {
    if (!formData.code.trim()) {
      setError(t.codeRequired);
      return;
    }
    if (!formData.name.trim()) {
      setError(t.nameRequired);
      return;
    }

    const payload = {
      code: formData.code.trim(),
      name: formData.name.trim(),
      pdk_mr: formData.pdk_mr !== "" ? parseFloat(formData.pdk_mr) : null,
      pdk_ss: formData.pdk_ss !== "" ? parseFloat(formData.pdk_ss) : null,
      hazard_class: formData.hazard_class !== "" ? parseInt(formData.hazard_class) : null,
      F: formData.F !== "" ? parseFloat(formData.F) : 1.0,
    };

    setSaving(true);
    setError(null);
    try {
      if (editingCode) {
        await updateSubstance(editingCode, payload);
        showSuccess(t.substanceSaved);
      } else {
        await addSubstance(payload);
        showSuccess(t.substanceAdded);
      }
      setEditingCode(null);
      setShowAddForm(false);
      setFormData(EMPTY_FORM);
      onSubstancesChanged();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setError(detail || e?.message || "Error");
    } finally {
      setSaving(false);
    }
  };

  // --- Delete ---
  const handleDelete = async (sub) => {
    const msg = t.confirmDelete.replace("{name}", sub.name);
    if (!window.confirm(msg)) return;

    try {
      await deleteSubstance(sub.code);
      showSuccess(t.substanceDeleted);
      onSubstancesChanged();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setError(detail || e?.message || "Error");
    }
  };

  const handleFieldChange = (key, value) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  // --- Inline form for add / edit ---
  const renderForm = () => (
    <div className="se-form">
      <div className="se-form-grid">
        <div className="se-form-field">
          <label>{t.substanceCode} *</label>
          <input
            type="text"
            value={formData.code}
            onChange={(e) => handleFieldChange("code", e.target.value)}
            disabled={!!editingCode}
            placeholder="0301"
          />
        </div>
        <div className="se-form-field">
          <label>{t.substanceName} *</label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => handleFieldChange("name", e.target.value)}
            placeholder={t.substanceName}
          />
        </div>
        <div className="se-form-field">
          <label>{t.pdkMr}</label>
          <input
            type="number"
            step="0.001"
            min="0"
            value={formData.pdk_mr}
            onChange={(e) => handleFieldChange("pdk_mr", e.target.value)}
            placeholder="0.5"
          />
        </div>
        <div className="se-form-field">
          <label>{t.pdkSs}</label>
          <input
            type="number"
            step="0.001"
            min="0"
            value={formData.pdk_ss}
            onChange={(e) => handleFieldChange("pdk_ss", e.target.value)}
            placeholder="0.05"
          />
        </div>
        <div className="se-form-field">
          <label>{t.hazardClass}</label>
          <select
            value={formData.hazard_class}
            onChange={(e) => handleFieldChange("hazard_class", e.target.value)}
          >
            <option value="">--</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="3">3</option>
            <option value="4">4</option>
          </select>
        </div>
        <div className="se-form-field">
          <label>{t.coeffF}</label>
          <input
            type="number"
            step="0.1"
            min="1"
            value={formData.F}
            onChange={(e) => handleFieldChange("F", e.target.value)}
            placeholder="1.0"
          />
        </div>
      </div>

      {error && <div className="se-error">{error}</div>}

      <div className="se-form-actions">
        <button className="btn-primary btn-sm" onClick={handleSave} disabled={saving}>
          {saving ? "..." : t.save}
        </button>
        <button className="btn-secondary btn-sm" onClick={handleCancelEdit}>
          {t.cancel}
        </button>
      </div>
    </div>
  );

  return (
    <div className="se-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="se-modal">
        {/* Header */}
        <div className="se-header">
          <h2 className="se-title">{t.substanceEditorTitle}</h2>
          <button className="se-close-btn" onClick={onClose} title={t.closeEditor}>
            &times;
          </button>
        </div>

        {/* Toolbar */}
        <div className="se-toolbar">
          <input
            type="text"
            className="se-search"
            placeholder={t.searchSubstances}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="se-filter-group">
            <button
              className={`btn-sm ${filter === "all" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilter("all")}
            >
              {t.allSubstances}
            </button>
            <button
              className={`btn-sm ${filter === "custom" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setFilter("custom")}
            >
              {t.onlyCustom}
            </button>
          </div>
          <button className="btn-primary btn-sm" onClick={handleOpenAdd}>
            + {t.addSubstance}
          </button>
        </div>

        {successMsg && <div className="se-success">{successMsg}</div>}

        {/* Add form */}
        {showAddForm && renderForm()}

        {/* Table */}
        <div className="se-table-wrap">
          <table className="se-table">
            <thead>
              <tr>
                <th style={{ width: 70 }}>{t.code}</th>
                <th>{t.name}</th>
                <th style={{ width: 90 }}>{t.pdkMr}</th>
                <th style={{ width: 90 }}>{t.pdkSs}</th>
                <th style={{ width: 60 }}>{t.hazardClass}</th>
                <th style={{ width: 50 }}>F</th>
                <th style={{ width: 130 }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: 20, color: "#94a3b8" }}>
                    {t.noSubstancesFound}
                  </td>
                </tr>
              )}
              {filtered.map((sub) =>
                editingCode === sub.code ? (
                  <tr key={sub.code} className="se-editing-row">
                    <td colSpan={7}>{renderForm()}</td>
                  </tr>
                ) : (
                  <tr key={sub.code} className={sub.custom ? "se-custom-row" : ""}>
                    <td className="se-code-cell">
                      {sub.code}
                      {sub.custom && <span className="se-badge-custom">{t.custom}</span>}
                    </td>
                    <td>{sub.name}</td>
                    <td>{sub.pdk_mr != null ? sub.pdk_mr : "--"}</td>
                    <td>{sub.pdk_ss != null ? sub.pdk_ss : "--"}</td>
                    <td>{sub.hazard_class != null ? sub.hazard_class : "--"}</td>
                    <td>{sub.F != null ? sub.F : "1.0"}</td>
                    <td className="se-actions-cell">
                      <button
                        className="btn-secondary btn-sm"
                        onClick={() => handleOpenEdit(sub)}
                        title={t.editSubstance}
                      >
                        {t.editSubstance}
                      </button>
                      {sub.custom && (
                        <button
                          className="btn-danger btn-sm"
                          onClick={() => handleDelete(sub)}
                          title={t.deleteSubstance}
                        >
                          {t.deleteSubstance}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        </div>

        <div className="se-footer">
          <span style={{ color: "#94a3b8", fontSize: 11 }}>
            {filtered.length} / {substances.length}
          </span>
          <button className="btn-secondary" onClick={onClose}>
            {t.closeEditor}
          </button>
        </div>
      </div>
    </div>
  );
}
