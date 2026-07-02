import React, { useState } from "react";

const STORAGE_KEY = "ond86_enterprise";

const DEFAULT_ENTERPRISE = {
  name: "",
  address: "",
  inn: "",
  projectNumber: "",
  client: "",
  developer: "",
  boundary: [], // массив точек [{lat, lon}, ...] первого контура (обратная совместимость)
  boundaries: [], // массив контуров-объектов [[{lat,lon}...], ...], до 5
};

export default function EnterpriseCard({ enterprise, onChange, t }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div className="panel-section">
      <div
        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <h3 className="section-title" style={{ margin: 0 }}>{t.enterprise}</h3>
        <span style={{ color: "#64748b", fontSize: 14 }}>{collapsed ? "▸" : "▾"}</span>
      </div>

      {!collapsed && (
        <div style={{ marginTop: 8 }}>
          <div className="field-row">
            <label>{t.enterpriseName} *</label>
            <input
              type="text"
              value={enterprise.name}
              onChange={(e) => onChange({ ...enterprise, name: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.enterpriseAddress}</label>
            <input
              type="text"
              value={enterprise.address}
              onChange={(e) => onChange({ ...enterprise, address: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.enterpriseInn}</label>
            <input
              type="text"
              value={enterprise.inn}
              onChange={(e) => onChange({ ...enterprise, inn: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.projectNumber}</label>
            <input
              type="text"
              value={enterprise.projectNumber}
              onChange={(e) => onChange({ ...enterprise, projectNumber: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.enterpriseClient}</label>
            <input
              type="text"
              value={enterprise.client}
              onChange={(e) => onChange({ ...enterprise, client: e.target.value })}
            />
          </div>
          <div className="field-row">
            <label>{t.enterpriseDeveloper}</label>
            <input
              type="text"
              value={enterprise.developer}
              onChange={(e) => onChange({ ...enterprise, developer: e.target.value })}
            />
          </div>
          {(() => {
            const objs = (enterprise.boundaries && enterprise.boundaries.length)
              ? enterprise.boundaries
              : (enterprise.boundary?.length ? [enterprise.boundary] : []);
            const total = objs.reduce((n, c) => n + (c?.length || 0), 0);
            if (total === 0) return null;
            return (
              <div style={{ fontSize: 11, color: "#047857", marginTop: 6 }}>
                ✓ {objs.length > 1 ? `Объектов: ${objs.length} · ` : ""}{t.boundaryPointsCount}: {total}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

export { DEFAULT_ENTERPRISE, STORAGE_KEY };
