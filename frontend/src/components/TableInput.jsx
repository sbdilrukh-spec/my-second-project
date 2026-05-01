import React, { useCallback, useRef } from "react";

const COLUMNS = [
  { key: "name", label: "Название", type: "text", width: 120 },
  { key: "height", label: "H, м", type: "number", width: 65 },
  { key: "diameter", label: "D, м", type: "number", width: 65 },
  { key: "velocity", label: "w0, м/с", type: "number", width: 70 },
  { key: "temperature", label: "Tг, °C", type: "number", width: 65 },
  { key: "emission_gs", label: "M, г/с", type: "number", width: 70 },
  { key: "emission_ty", label: "т/год", type: "number", width: 70 },
];

export default function TableInput({ sources, onChange, onAdd, onRemove, t }) {
  const tableRef = useRef(null);

  const handleCellChange = useCallback((rowIdx, key, value) => {
    const col = COLUMNS.find((c) => c.key === key);
    if (col.type === "number") {
      const v = parseFloat(value);
      onChange(rowIdx, key, isNaN(v) ? null : v);
    } else {
      onChange(rowIdx, key, value);
    }
  }, [onChange]);

  const handlePaste = useCallback((e) => {
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;

    const rows = text.split(/\r?\n/).filter((r) => r.trim() !== "");
    if (rows.length === 0) return;

    // Detect if pasted data is multi-column (tab or semicolon separated)
    const delimiter = rows[0].includes("\t") ? "\t" : rows[0].includes(";") ? ";" : null;
    if (!delimiter) return;

    e.preventDefault();

    const parsed = rows.map((row) => {
      const cells = row.split(delimiter);
      const src = {};
      COLUMNS.forEach((col, i) => {
        if (i < cells.length) {
          const val = cells[i].trim();
          if (col.type === "number") {
            const n = parseFloat(val.replace(",", "."));
            src[col.key] = isNaN(n) ? null : n;
          } else {
            src[col.key] = val || `Источник`;
          }
        }
      });
      return src;
    });

    // Filter out rows that are likely headers
    const dataRows = parsed.filter((r) => {
      return r.height != null || r.diameter != null || r.emission_gs != null;
    });

    if (dataRows.length > 0) {
      onAdd(dataRows);
    }
  }, [onAdd]);

  return (
    <div className="table-input-wrapper">
      <div
        className="table-input-scroll"
        ref={tableRef}
        onPaste={handlePaste}
        tabIndex={0}
        style={{
          overflowX: "auto",
          border: "1px solid #e2e8f0",
          borderRadius: 6,
          outline: "none",
          maxHeight: 400,
          overflowY: "auto",
        }}
      >
        <table className="table-input" style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
          <thead>
            <tr>
              <th style={thStyle}>№</th>
              {COLUMNS.map((col) => (
                <th key={col.key} style={{ ...thStyle, width: col.width }}>
                  {col.label}
                </th>
              ))}
              <th style={thStyle}></th>
            </tr>
          </thead>
          <tbody>
            {sources.map((src, i) => (
              <tr key={i}>
                <td style={tdStyle}>{i + 1}</td>
                {COLUMNS.map((col) => {
                  // Поля выбросов теперь живут в src.emissions[0]; остальное — на верхнем уровне
                  const isEmissionKey = col.key === "emission_gs" || col.key === "emission_ty";
                  const val = isEmissionKey
                    ? (src.emissions?.[0]?.[col.key] ?? "")
                    : (src[col.key] ?? "");
                  return (
                  <td key={col.key} style={tdStyle}>
                    <input
                      type={col.type}
                      step="any"
                      value={val}
                      onChange={(e) => handleCellChange(i, col.key, e.target.value)}
                      style={inputStyle}
                    />
                  </td>
                  );
                })}
                <td style={tdStyle}>
                  <button
                    onClick={() => onRemove(i)}
                    style={delBtnStyle}
                    title="Удалить"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: "#64748b" }}>
        Ctrl+V — вставить данные из Excel (столбцы: Название, H, D, w0, Tг, M г/с, т/год)
      </div>
    </div>
  );
}

const thStyle = {
  padding: "6px 4px",
  background: "#2563EB",
  color: "#fff",
  fontWeight: 600,
  fontSize: 11,
  textAlign: "center",
  position: "sticky",
  top: 0,
  whiteSpace: "nowrap",
};

const tdStyle = {
  padding: "2px",
  borderBottom: "1px solid #e2e8f0",
};

const inputStyle = {
  width: "100%",
  border: "1px solid transparent",
  borderRadius: 3,
  padding: "4px 3px",
  fontSize: 12,
  textAlign: "center",
  background: "transparent",
  outline: "none",
  boxSizing: "border-box",
};

const delBtnStyle = {
  background: "none",
  border: "none",
  color: "#DC2626",
  cursor: "pointer",
  fontSize: 14,
  fontWeight: "bold",
  padding: "2px 6px",
};
