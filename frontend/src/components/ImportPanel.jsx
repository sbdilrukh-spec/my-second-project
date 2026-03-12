import React, { useRef, useState } from "react";
import axios from "axios";

export default function ImportPanel({ onImport, t }) {
  const fileRef = useRef(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setImporting(true);
    setImportResult(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post("/api/import", formData);
      const data = res.data;

      if (data.sources && data.sources.length > 0) {
        onImport(data.sources);
      }

      setImportResult({
        total: data.total,
        valid: data.valid_count,
        errors: data.errors || [],
      });
    } catch (err) {
      setImportResult({
        total: 0,
        valid: 0,
        errors: [err?.response?.data?.detail || "Ошибка импорта"],
      });
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  };

  const handleDownloadTemplate = () => {
    const a = document.createElement("a");
    a.href = "/api/import/template";
    a.download = "template_sources.csv";
    a.click();
  };

  return (
    <div className="panel-section">
      <h3 className="section-title">{t.importTitle}</h3>

      <div style={{ display: "flex", gap: 6 }}>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx"
          style={{ display: "none" }}
          onChange={handleImport}
        />
        <button
          className="btn-secondary btn-sm"
          style={{ flex: 1 }}
          onClick={() => fileRef.current?.click()}
          disabled={importing}
        >
          {importing ? t.importing : t.importFile}
        </button>
        <button
          className="btn-secondary btn-sm"
          style={{ flex: 1 }}
          onClick={handleDownloadTemplate}
        >
          {t.downloadTemplate}
        </button>
      </div>

      {importResult && (
        <div style={{
          marginTop: 8,
          padding: 8,
          background: importResult.valid > 0 ? "#F0FDF4" : "#FEF2F2",
          borderRadius: 6,
          fontSize: 12,
          border: `1px solid ${importResult.valid > 0 ? "#BBF7D0" : "#FECACA"}`,
        }}>
          <div>
            {t.importResult}: {importResult.valid} / {importResult.total}
          </div>
          {importResult.errors.length > 0 && (
            <div style={{ color: "#DC2626", marginTop: 4, fontSize: 11 }}>
              {importResult.errors.slice(0, 5).map((err, i) => (
                <div key={i}>{err}</div>
              ))}
              {importResult.errors.length > 5 && (
                <div>...и ещё {importResult.errors.length - 5} ошибок</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
