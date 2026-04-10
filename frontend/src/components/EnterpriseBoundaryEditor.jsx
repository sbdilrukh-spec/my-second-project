import { useState, useRef } from "react";

/**
 * Модальное окно редактирования контура (полигона) предприятия / карьера.
 * Точки задаются вручную, кликом на карте или импортом из CSV.
 *
 * Props:
 *  - boundary: массив { lat, lon }
 *  - onChange(newBoundary)
 *  - picking: bool — режим клика на карте активен
 *  - onTogglePicking()
 *  - onClose()
 *  - t: словарь переводов
 */
// Парсит одну строку — поддерживает десятичные градусы и DMS (градусы/минуты/секунды).
// Возвращает { lat, lon } или null если не распознано.
function parseLineToPoint(rawLine) {
  const line = rawLine.trim();
  if (!line) return null;
  // Достаём все числа, включая отрицательные и с дробной частью.
  // Запятая в десятичной части тоже допускается.
  const matches = line.match(/-?\d+(?:[.,]\d+)?/g);
  if (!matches) return null;
  const nums = matches.map((s) => parseFloat(s.replace(",", ".")));

  // Хелпер: соединить градусы/минуты/секунды в десятичные градусы,
  // знак берётся от градусов (минуты/секунды всегда положительные).
  const toDec = (d, m = 0, s = 0) => {
    const sign = d < 0 ? -1 : 1;
    return sign * (Math.abs(d) + (m || 0) / 60 + (s || 0) / 3600);
  };

  if (nums.length === 2) {
    // Десятичные градусы: lat, lon
    return { lat: nums[0], lon: nums[1] };
  }
  if (nums.length === 4) {
    // Градусы и минуты: lat_d lat_m lon_d lon_m
    return { lat: toDec(nums[0], nums[1]), lon: toDec(nums[2], nums[3]) };
  }
  if (nums.length === 6) {
    // Полный DMS: lat_d lat_m lat_s lon_d lon_m lon_s
    return {
      lat: toDec(nums[0], nums[1], nums[2]),
      lon: toDec(nums[3], nums[4], nums[5]),
    };
  }
  return null;
}

function parseImportText(text) {
  const points = [];
  const errors = [];
  const lines = text.split(/\r?\n/);
  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();
    if (!line) return;
    // Пропускаем заголовок если в первой строке нет цифр
    if (idx === 0 && !/\d/.test(line)) return;
    const point = parseLineToPoint(line);
    if (!point) {
      errors.push(`строка ${idx + 1}: не распознано`);
      return;
    }
    if (!Number.isFinite(point.lat) || !Number.isFinite(point.lon)) {
      errors.push(`строка ${idx + 1}: не число`);
      return;
    }
    points.push(point);
  });
  return { points, errors };
}

export default function EnterpriseBoundaryEditor({
  boundary, onChange, picking, onTogglePicking, onClose, t,
}) {
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState(null);
  const [showImport, setShowImport] = useState(false);
  // Превью разобранных точек, ждёт подтверждения пользователя
  const [importPreview, setImportPreview] = useState(null);
  const fileInputRef = useRef(null);

  const handleAddRow = () => {
    onChange([...boundary, { lat: 0, lon: 0 }]);
  };

  const handleEditPoint = (index, key, value) => {
    const v = value === "" ? 0 : parseFloat(value);
    const next = boundary.map((p, i) => (i === index ? { ...p, [key]: Number.isFinite(v) ? v : 0 } : p));
    onChange(next);
  };

  const handleDeleteRow = (index) => {
    onChange(boundary.filter((_, i) => i !== index));
  };

  const handleClearAll = () => {
    if (!boundary.length) return;
    if (window.confirm(t.boundaryClearConfirm)) onChange([]);
  };

  // Шаг 1: распознать текст и показать превью (без записи в boundary)
  const handleParseImport = () => {
    setImportError(null);
    const { points, errors } = parseImportText(importText);
    if (!points.length) {
      setImportError(errors.length ? errors.slice(0, 3).join("; ") : "Нет точек");
      setImportPreview(null);
      return;
    }
    setImportPreview({ points, errors });
  };

  // Шаг 2: подтвердить и записать в boundary
  const handleConfirmImport = () => {
    if (!importPreview?.points?.length) return;
    onChange([...boundary, ...importPreview.points]);
    setImportText("");
    setImportPreview(null);
    setImportError(null);
    setShowImport(false);
  };

  const handleCancelImport = () => {
    setImportPreview(null);
    setImportError(null);
  };

  const handleFileImport = (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = String(ev.target.result || "");
      // Файл загружаем сразу в textarea, чтобы пользователь увидел содержимое
      // и подтвердил импорт через ту же кнопку
      setImportText(text);
      setShowImport(true);
      const { points, errors } = parseImportText(text);
      if (!points.length) {
        setImportError(errors.length ? errors.slice(0, 3).join("; ") : "Файл пуст");
        setImportPreview(null);
        return;
      }
      setImportError(null);
      setImportPreview({ points, errors });
    };
    reader.readAsText(file);
  };

  return (
    <div
      className="se-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={picking ? { background: "rgba(0,0,0,0.05)", pointerEvents: "none" } : undefined}
    >
      <div
        className="se-modal"
        style={picking ? {
          pointerEvents: "auto",
          maxWidth: 360, marginLeft: "auto", marginRight: 16,
          maxHeight: "70vh",
        } : undefined}
      >
        {/* Header */}
        <div className="se-header">
          <h2 className="se-title">🏭 {t.enterpriseBoundaryTitle}</h2>
          <button className="se-close-btn" onClick={onClose} title={t.closeEditor}>
            &times;
          </button>
        </div>

        {/* Toolbar */}
        <div className="se-toolbar" style={{ flexWrap: "wrap", gap: 6 }}>
          <button className="btn-primary btn-sm" onClick={handleAddRow}>
            + {t.addBoundaryPoint}
          </button>
          <button
            className={`btn-sm ${picking ? "btn-primary" : "btn-secondary"}`}
            onClick={onTogglePicking}
            title={t.pickBoundaryHint}
          >
            {picking ? `📍 ${t.pickingActive}` : `📍 ${t.pickBoundaryOnMap}`}
          </button>
          <button className="btn-secondary btn-sm" onClick={() => setShowImport((v) => !v)}>
            📥 {t.importCsv}
          </button>
          <button
            className="btn-secondary btn-sm"
            style={{ marginLeft: "auto", color: "#DC2626", borderColor: "#FCA5A5" }}
            onClick={handleClearAll}
            disabled={!boundary.length}
          >
            🗑 {t.clearAll}
          </button>
        </div>

        {picking && (
          <div style={{
            background: "#ECFDF5", color: "#047857",
            padding: "6px 10px", borderRadius: 6, fontSize: 12,
            margin: "0 0 8px", border: "1px solid #A7F3D0",
          }}>
            {t.pickBoundaryHint}
          </div>
        )}

        {/* CSV import block */}
        {showImport && (
          <div style={{
            background: "#F8FAFC", padding: 10, borderRadius: 6,
            border: "1px solid #E2E8F0", marginBottom: 8,
          }}>
            <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6 }}>
              {t.importCsvHint}
              <br />
              <span style={{ color: "#475569" }}>
                Поддерживается: <b>десятичные градусы</b> (40.084, 65.379) и <b>DMS</b> (40° 02' 51.04" 66° 50' 09.77").
              </span>
            </div>
            <textarea
              value={importText}
              onChange={(e) => {
                setImportText(e.target.value);
                // Сбрасываем превью при изменении текста — нужно заново распознать
                if (importPreview) setImportPreview(null);
                if (importError) setImportError(null);
              }}
              rows={6}
              placeholder={"40.084123, 65.379456\n40° 02' 51.04\" 66° 50' 09.77\"\n..."}
              style={{
                width: "100%", fontFamily: "monospace", fontSize: 11,
                padding: 6, border: "1px solid #CBD5E1", borderRadius: 4,
                resize: "vertical",
              }}
            />
            {importError && (
              <div style={{ color: "#DC2626", fontSize: 11, marginTop: 4 }}>{importError}</div>
            )}

            {/* Превью распознанных точек + подтверждение */}
            {importPreview && (
              <div style={{
                marginTop: 8, padding: 8, borderRadius: 6,
                background: "#ECFDF5", border: "1px solid #A7F3D0",
              }}>
                <div style={{ fontSize: 12, color: "#047857", fontWeight: 600, marginBottom: 4 }}>
                  ✓ Распознано точек: {importPreview.points.length}
                  {importPreview.errors.length > 0 && (
                    <span style={{ color: "#B45309", fontWeight: 500 }}>
                      {" "}(пропущено: {importPreview.errors.length})
                    </span>
                  )}
                </div>
                <div style={{
                  maxHeight: 90, overflow: "auto",
                  fontFamily: "monospace", fontSize: 10, color: "#334155",
                  background: "#fff", padding: 4, borderRadius: 4, border: "1px solid #D1FAE5",
                }}>
                  {importPreview.points.slice(0, 6).map((p, i) => (
                    <div key={i}>
                      {i + 1}. {p.lat.toFixed(6)}, {p.lon.toFixed(6)}
                    </div>
                  ))}
                  {importPreview.points.length > 6 && (
                    <div style={{ color: "#94a3b8" }}>… и ещё {importPreview.points.length - 6}</div>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <button className="btn-primary btn-sm" onClick={handleConfirmImport}>
                    ✓ Подтвердить ({importPreview.points.length})
                  </button>
                  <button className="btn-secondary btn-sm" onClick={handleCancelImport}>
                    {t.cancel}
                  </button>
                </div>
              </div>
            )}

            {/* Кнопки распознавания / загрузки файла */}
            {!importPreview && (
              <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                <button className="btn-primary btn-sm" onClick={handleParseImport} disabled={!importText.trim()}>
                  🔍 Распознать
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,.txt"
                  style={{ display: "none" }}
                  onChange={handleFileImport}
                />
                <button className="btn-secondary btn-sm" onClick={() => fileInputRef.current?.click()}>
                  📁 {t.importFromFile}
                </button>
                <button
                  className="btn-secondary btn-sm"
                  style={{ marginLeft: "auto" }}
                  onClick={() => {
                    setShowImport(false);
                    setImportError(null);
                    setImportText("");
                    setImportPreview(null);
                  }}
                >
                  {t.cancel}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Table */}
        <div className="se-table-wrap">
          <table className="se-table">
            <thead>
              <tr>
                <th style={{ width: 50 }}>#</th>
                <th>{t.lat}</th>
                <th>{t.lon}</th>
                <th style={{ width: 60 }}></th>
              </tr>
            </thead>
            <tbody>
              {boundary.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ textAlign: "center", padding: 20, color: "#94a3b8" }}>
                    {t.noBoundaryPoints}
                  </td>
                </tr>
              )}
              {boundary.map((p, i) => (
                <tr key={i}>
                  <td style={{ textAlign: "center", color: "#64748b", fontWeight: 600 }}>{i + 1}</td>
                  <td>
                    <input
                      type="number"
                      step="0.000001"
                      value={p.lat}
                      onChange={(e) => handleEditPoint(i, "lat", e.target.value)}
                      style={{ width: "100%", fontSize: 12 }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.000001"
                      value={p.lon}
                      onChange={(e) => handleEditPoint(i, "lon", e.target.value)}
                      style={{ width: "100%", fontSize: 12 }}
                    />
                  </td>
                  <td style={{ textAlign: "center" }}>
                    <button
                      className="btn-sm"
                      onClick={() => handleDeleteRow(i)}
                      style={{
                        color: "#DC2626", background: "#FEE2E2",
                        border: "1px solid #FCA5A5", fontSize: 11, padding: "2px 6px",
                      }}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{
          marginTop: 8, padding: "6px 10px", borderRadius: 6,
          background: "#F1F5F9", fontSize: 11, color: "#475569",
        }}>
          {t.boundaryPointsCount}: <b>{boundary.length}</b>
          {boundary.length >= 3 && <> · {t.boundaryReady}</>}
        </div>
      </div>
    </div>
  );
}
