import React from "react";

function fmt(val, digits = 4) {
  const n = parseFloat(val);
  return isNaN(n) ? "—" : n.toFixed(digits);
}

export default function ResultsPanel({
  result, currentPdk,
  onExportPdf, exporting,
  onExportMapPng, exportingPng,
  onExportExcel, exportingExcel,
  pdfMapType, onChangePdfMapType,
  t,
}) {
  if (!result) {
    return (
      <div className="panel-section results-empty">
        <h3 className="section-title">{t.results}</h3>
        <p style={{ color: "#94a3b8", textAlign: "center", padding: "16px 0" }}>
          {t.noResults}
        </p>
      </div>
    );
  }

  const maxC = parseFloat(result.max_c) || 0;
  const pdk  = currentPdk != null ? currentPdk : (parseFloat(result.pdk) || 0.5);
  const pdk_ratio = pdk > 0 ? maxC / pdk : null;
  const exceeds = maxC > pdk;

  return (
    <div className="panel-section">
      <h3 className="section-title">{t.results}</h3>

      <div className={`result-badge ${exceeds ? "badge-danger" : "badge-ok"}`}>
        {exceeds ? t.exceedsPdk : t.noExceedsPdk}
      </div>

      <div className="result-row">
        <span className="result-label">{t.maxConcentration}</span>
        <span className="result-value">{fmt(maxC, 5)} мг/м³</span>
      </div>

      {pdk_ratio !== null && (
        <div className="result-row">
          <span className="result-label">Cmax / ПДК</span>
          <span className={`result-value ${exceeds ? "text-danger" : "text-ok"}`}>
            {fmt(pdk_ratio, 3)}
          </span>
        </div>
      )}

      <div className="result-row">
        <span className="result-label">{t.maxAt}</span>
        <span className="result-value" style={{ fontSize: 11 }}>
          {fmt(result.max_lat, 5)}, {fmt(result.max_lon, 5)}
        </span>
      </div>

      {Array.isArray(result.source_results) && result.source_results.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <table className="result-table">
            <thead>
              <tr>
                <th>Источник</th>
                <th>{t.sourceCm}</th>
                <th>{t.sourceXm}</th>
              </tr>
            </thead>
            <tbody>
              {result.source_results.map((sr, i) => (
                <tr key={i}>
                  <td>{sr.name || "—"}</td>
                  <td>{fmt(sr.cm_mg, 4)}</td>
                  <td>{fmt(sr.xm, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* СЗЗ */}
      {result.szz && (
        <div style={{ marginTop: 12, padding: 8, background: "#FEF2F2", borderRadius: 6, border: "1px solid #FECACA" }}>
          <div style={{ fontWeight: 600, fontSize: 12, color: "#DC2626", marginBottom: 4 }}>
            Граница СЗЗ
          </div>
          <div className="result-row">
            <span className="result-label">Макс. расстояние</span>
            <span className="result-value">{fmt(result.szz.max_distance_m, 0)} м</span>
          </div>
          <div className="result-row">
            <span className="result-label">Мин. расстояние</span>
            <span className="result-value">{fmt(result.szz.min_distance_m, 0)} м</span>
          </div>
          <div className="result-row">
            <span className="result-label">Площадь превышения</span>
            <span className="result-value">{fmt(result.szz.area_ha, 2)} га</span>
          </div>
        </div>
      )}

      {/* Тип карты в PDF: изолинии или сетка ОНД с числами */}
      {onChangePdfMapType && (
        <div style={{
          marginTop: 12, padding: 8, borderRadius: 6,
          background: "#F1F5F9", border: "1px solid #E2E8F0",
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#334155", marginBottom: 6 }}>
            Тип карты рассеивания в PDF
          </div>
          <label style={{
            display: "flex", alignItems: "center", gap: 6,
            fontSize: 11, color: "#1F2937", cursor: "pointer", marginBottom: 4,
          }}>
            <input
              type="radio"
              name="pdf-map-type"
              checked={pdfMapType !== "grid"}
              onChange={() => onChangePdfMapType("isolines")}
            />
            <span><b>Изолинии в долях ПДК</b> — цветные изолинии с заливкой и подписями</span>
          </label>
          <label style={{
            display: "flex", alignItems: "center", gap: 6,
            fontSize: 11, color: "#1F2937", cursor: "pointer",
          }}>
            <input
              type="radio"
              name="pdf-map-type"
              checked={pdfMapType === "grid"}
              onChange={() => onChangePdfMapType("grid")}
            />
            <span><b>Сетка ОНД</b> — табличная карта с числами концентрации в каждой ячейке</span>
          </label>
        </div>
      )}

      <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
        <button
          className="btn-primary"
          style={{ flex: 1 }}
          onClick={onExportPdf}
          disabled={exporting}
        >
          {exporting ? t.exporting : t.exportPdf}
        </button>
        <button
          className="btn-secondary"
          style={{ flex: 1 }}
          onClick={onExportExcel}
          disabled={exportingExcel}
        >
          {exportingExcel ? "Экспорт..." : "Excel"}
        </button>
      </div>

      {onExportMapPng && (
        <button
          className="btn-secondary"
          style={{
            width: "100%", marginTop: 6, fontSize: 12,
            background: "#FEF3C7", borderColor: "#FDE68A", color: "#92400E",
          }}
          onClick={onExportMapPng}
          disabled={exportingPng}
          title="Прозрачный PNG карт рассеивания (по одному на вещество) — для наложения в CorelDraw"
        >
          {exportingPng ? "Готовим PNG..." : "🎨 Скачать карты PNG (для CorelDraw)"}
        </button>
      )}
    </div>
  );
}
