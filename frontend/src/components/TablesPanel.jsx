import React, { useState } from "react";

export default function TablesPanel({ tables, t }) {
  const [activeTab, setActiveTab] = useState("pdv");

  if (!tables) return null;

  const currentTables = activeTab === "pdv" ? tables.pdv : tables.ovos;
  if (!currentTables) return null;

  return (
    <div className="panel-section">
      <h3 className="section-title">{t.tablesTitle}</h3>

      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        <button
          className={`btn-sm ${activeTab === "pdv" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveTab("pdv")}
        >
          {t.tablesPdv}
        </button>
        <button
          className={`btn-sm ${activeTab === "ovos" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setActiveTab("ovos")}
        >
          {t.tablesOvos}
        </button>
      </div>

      {Object.entries(currentTables).map(([key, table]) => (
        <TableBlock key={key} table={table} />
      ))}
    </div>
  );
}

function TableBlock({ table }) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div style={{ marginBottom: 8 }}>
      <div
        style={{
          cursor: "pointer",
          padding: "6px 8px",
          background: "#f1f5f9",
          borderRadius: 4,
          fontSize: 12,
          fontWeight: 600,
          display: "flex",
          justifyContent: "space-between",
        }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span>{table.title}</span>
        <span>{collapsed ? "▸" : "▾"}</span>
      </div>

      {!collapsed && (
        <div style={{ overflowX: "auto", marginTop: 4 }}>
          <table className="result-table" style={{ fontSize: 11 }}>
            <thead>
              <tr>
                {table.columns.map((col, i) => (
                  <th key={i}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, ri) => (
                <tr key={ri}>
                  {Object.values(row).map((val, ci) => (
                    <td key={ci}>{val ?? "—"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
