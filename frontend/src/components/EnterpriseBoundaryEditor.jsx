import { useState, useRef } from "react";

/**
 * Модальное окно редактирования контуров предприятия / карьеров.
 * Поддерживает НЕСКОЛЬКО отдельных объектов (контуров) — до maxObjects.
 * Точки активного объекта задаются вручную, кликом на карте или импортом.
 *
 * Props:
 *  - boundaries: массив контуров [ [{lat,lon}...], ... ]
 *  - activeIdx: индекс активного объекта
 *  - onActiveIdxChange(idx)
 *  - maxObjects: максимум объектов (по умолчанию 5)
 *  - onChange(newBoundaries)  — отдаёт весь массив контуров
 *  - picking: bool — режим клика на карте активен
 *  - onTogglePicking(), onFitMap(), onAfterImport(count), onClose()
 *  - t: словарь переводов
 */

// Парсит одну строку — десятичные градусы или DMS. Возвращает {lat,lon} или null.
function parseLineToPoint(rawLine) {
  const line = rawLine.trim();
  if (!line) return null;
  const matches = line.match(/-?\d+(?:[.,]\d+)?/g);
  if (!matches) return null;
  const nums = matches.map((s) => parseFloat(s.replace(",", ".")));
  const toDec = (d, m = 0, s = 0) => {
    const sign = d < 0 ? -1 : 1;
    return sign * (Math.abs(d) + (m || 0) / 60 + (s || 0) / 3600);
  };
  if (nums.length === 2) return { lat: nums[0], lon: nums[1] };
  if (nums.length === 4) return { lat: toDec(nums[0], nums[1]), lon: toDec(nums[2], nums[3]) };
  if (nums.length === 6) {
    return { lat: toDec(nums[0], nums[1], nums[2]), lon: toDec(nums[3], nums[4], nums[5]) };
  }
  return null;
}

// Разбирает текст в НЕСКОЛЬКО контуров: пустая строка = граница нового объекта.
function parseImportText(text) {
  const groups = [];
  const errors = [];
  let current = [];
  const lines = text.split(/\r?\n/);
  lines.forEach((rawLine, idx) => {
    const line = rawLine.trim();
    if (!line) {
      // Пустая строка — конец текущего объекта, начало следующего
      if (current.length) groups.push(current);
      current = [];
      return;
    }
    // Пропускаем строку-заголовок, если в самой первой строке нет цифр
    if (idx === 0 && !/\d/.test(line)) return;
    const point = parseLineToPoint(line);
    if (!point || !Number.isFinite(point.lat) || !Number.isFinite(point.lon)) {
      errors.push(`строка ${idx + 1}: не распознано`);
      return;
    }
    current.push(point);
  });
  if (current.length) groups.push(current);
  return { contours: groups, errors };
}

export default function EnterpriseBoundaryEditor({
  boundaries, activeIdx, onActiveIdxChange, maxObjects = 5,
  onChange, picking, onTogglePicking, onFitMap, onAfterImport, onClose, t,
}) {
  const [importText, setImportText] = useState("");
  const [importError, setImportError] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [importPreview, setImportPreview] = useState(null); // { contours, errors }
  const fileInputRef = useRef(null);

  // Всегда работаем хотя бы с одним объектом в UI (для редактирования пустого)
  const objects = (boundaries && boundaries.length) ? boundaries : [[]];
  const active = Math.min(Math.max(activeIdx || 0, 0), objects.length - 1);
  const activeContour = objects[active] || [];
  const totalPoints = objects.reduce((n, c) => n + (c?.length || 0), 0);

  // Заменяет активный контур новым набором точек и отдаёт весь массив наверх
  const commitActive = (nextContour) => {
    const next = objects.map((c, i) => (i === active ? nextContour : c));
    onChange(next);
  };

  const handleAddRow = () => commitActive([...activeContour, { lat: 0, lon: 0 }]);

  const handleEditPoint = (index, key, value) => {
    const v = value === "" ? 0 : parseFloat(value);
    const next = activeContour.map((p, i) =>
      i === index ? { ...p, [key]: Number.isFinite(v) ? v : 0 } : p
    );
    commitActive(next);
  };

  const handleDeleteRow = (index) => commitActive(activeContour.filter((_, i) => i !== index));

  const handleAddObject = () => {
    if (objects.length >= maxObjects) return;
    onChange([...objects.filter((c) => c.length), []]);
    onActiveIdxChange(objects.filter((c) => c.length).length);
  };

  const handleDeleteObject = () => {
    const next = objects.filter((_, i) => i !== active);
    onChange(next);
    onActiveIdxChange(Math.max(0, active - 1));
  };

  const handleClearAll = () => {
    if (totalPoints === 0) return;
    if (window.confirm(t.boundaryClearConfirm)) {
      onChange([]);
      onActiveIdxChange(0);
    }
  };

  // Шаг 1: распознать текст (в несколько объектов) и показать превью
  const handleParseImport = () => {
    setImportError(null);
    const { contours, errors } = parseImportText(importText);
    const totalPts = contours.reduce((n, c) => n + c.length, 0);
    if (!totalPts) {
      setImportError(errors.length ? errors.slice(0, 3).join("; ") : "Нет точек");
      setImportPreview(null);
      return;
    }
    setImportPreview({ contours, errors });
  };

  // Шаг 2: подтвердить — добавить распознанные объекты (до maxObjects)
  const handleConfirmImport = () => {
    if (!importPreview?.contours?.length) return;
    const incoming = importPreview.contours;
    const existing = objects.filter((c) => c.length);
    const merged = [...existing, ...incoming].slice(0, maxObjects);
    const addedPts = incoming.reduce((n, c) => n + c.length, 0);
    const skippedObjects = existing.length + incoming.length - merged.length;

    onChange(merged);
    onActiveIdxChange(Math.min(existing.length, merged.length - 1));
    setImportText("");
    setImportPreview(null);
    setImportError(null);
    setShowImport(false);
    if (skippedObjects > 0) {
      setImportError(`Достигнут максимум ${maxObjects} объектов — лишние (${skippedObjects}) пропущены.`);
    }
    if (onAfterImport) onAfterImport(addedPts);
    if (onFitMap) onFitMap();
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
      setImportText(text);
      setShowImport(true);
      const { contours, errors } = parseImportText(text);
      const totalPts = contours.reduce((n, c) => n + c.length, 0);
      if (!totalPts) {
        setImportError(errors.length ? errors.slice(0, 3).join("; ") : "Файл пуст");
        setImportPreview(null);
        return;
      }
      setImportError(null);
      setImportPreview({ contours, errors });
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

        {/* Переключатель объектов (контуров) */}
        <div style={{
          display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center",
          marginBottom: 8, padding: 6, background: "#F8FAFC",
          borderRadius: 6, border: "1px solid #E2E8F0",
        }}>
          <span style={{ fontSize: 11, color: "#64748b", fontWeight: 600, marginRight: 2 }}>
            Объекты:
          </span>
          {objects.map((c, i) => (
            <button
              key={i}
              className="btn-sm"
              onClick={() => onActiveIdxChange(i)}
              style={{
                padding: "2px 8px", fontSize: 11, borderRadius: 5,
                border: i === active ? "1px solid #1E40AF" : "1px solid #CBD5E1",
                background: i === active ? "#1E40AF" : "#fff",
                color: i === active ? "#fff" : "#334155", fontWeight: 600,
              }}
              title={`Объект ${i + 1}: ${c.length} точек`}
            >
              {i + 1} <span style={{ opacity: 0.7 }}>({c.length})</span>
            </button>
          ))}
          {objects.length < maxObjects && (
            <button
              className="btn-sm"
              onClick={handleAddObject}
              style={{
                padding: "2px 8px", fontSize: 11, borderRadius: 5,
                border: "1px dashed #94A3B8", background: "#fff", color: "#475569",
              }}
              title="Добавить новый объект (контур)"
            >
              + объект
            </button>
          )}
          {objects.length > 1 && (
            <button
              className="btn-sm"
              onClick={handleDeleteObject}
              style={{
                padding: "2px 8px", fontSize: 11, borderRadius: 5, marginLeft: "auto",
                border: "1px solid #FCA5A5", background: "#FEE2E2", color: "#DC2626",
              }}
              title={`Удалить объект ${active + 1}`}
            >
              🗑 объект {active + 1}
            </button>
          )}
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
          {totalPoints > 0 && onFitMap && (
            <button
              className="btn-secondary btn-sm"
              onClick={onFitMap}
              style={{ background: "#ECFDF5", color: "#047857", borderColor: "#A7F3D0" }}
              title="Закрыть это окно и показать контуры на карте"
            >
              🎯 На карте
            </button>
          )}
          <button
            className="btn-secondary btn-sm"
            style={{ marginLeft: "auto", color: "#DC2626", borderColor: "#FCA5A5" }}
            onClick={handleClearAll}
            disabled={totalPoints === 0}
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
            {t.pickBoundaryHint} <b>Точки добавляются в объект {active + 1}.</b>
          </div>
        )}

        {/* CSV / текстовый импорт */}
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
              <br />
              <span style={{ color: "#1E40AF", fontWeight: 600 }}>
                Пустая строка = новый объект (до {maxObjects}).
              </span>
            </div>
            <textarea
              value={importText}
              onChange={(e) => {
                setImportText(e.target.value);
                if (importPreview) setImportPreview(null);
                if (importError) setImportError(null);
              }}
              rows={8}
              placeholder={"40.084, 65.379\n40.085, 65.380\n\n40.100, 65.400\n40.101, 65.401"}
              style={{
                width: "100%", fontFamily: "monospace", fontSize: 11,
                padding: 6, border: "1px solid #CBD5E1", borderRadius: 4,
                resize: "vertical",
              }}
            />
            {importError && (
              <div style={{ color: "#DC2626", fontSize: 11, marginTop: 4 }}>{importError}</div>
            )}

            {/* Превью распознанных объектов */}
            {importPreview && (
              <div style={{
                marginTop: 8, padding: 8, borderRadius: 6,
                background: "#ECFDF5", border: "1px solid #A7F3D0",
              }}>
                <div style={{ fontSize: 12, color: "#047857", fontWeight: 600, marginBottom: 4 }}>
                  ✓ Объектов: {importPreview.contours.length} · точек:{" "}
                  {importPreview.contours.reduce((n, c) => n + c.length, 0)}
                  {importPreview.errors.length > 0 && (
                    <span style={{ color: "#B45309", fontWeight: 500 }}>
                      {" "}(пропущено строк: {importPreview.errors.length})
                    </span>
                  )}
                </div>
                <div style={{
                  maxHeight: 100, overflow: "auto",
                  fontFamily: "monospace", fontSize: 10, color: "#334155",
                  background: "#fff", padding: 4, borderRadius: 4, border: "1px solid #D1FAE5",
                }}>
                  {importPreview.contours.map((c, ci) => (
                    <div key={ci} style={{ marginBottom: 4 }}>
                      <div style={{ color: "#1E40AF", fontWeight: 700 }}>Объект {ci + 1} ({c.length} т.):</div>
                      {c.slice(0, 4).map((p, i) => (
                        <div key={i}>&nbsp;&nbsp;{p.lat.toFixed(6)}, {p.lon.toFixed(6)}</div>
                      ))}
                      {c.length > 4 && <div style={{ color: "#94a3b8" }}>&nbsp;&nbsp;… и ещё {c.length - 4}</div>}
                    </div>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
                  <button className="btn-primary btn-sm" onClick={handleConfirmImport}>
                    ✓ Добавить объектов: {importPreview.contours.length}
                  </button>
                  <button className="btn-secondary btn-sm" onClick={handleCancelImport}>
                    {t.cancel}
                  </button>
                </div>
              </div>
            )}

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

        {/* Таблица точек активного объекта */}
        <div style={{ fontSize: 11, color: "#475569", margin: "0 0 4px", fontWeight: 600 }}>
          Точки объекта {active + 1}:
        </div>
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
              {activeContour.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ textAlign: "center", padding: 20, color: "#94a3b8" }}>
                    {t.noBoundaryPoints}
                  </td>
                </tr>
              )}
              {activeContour.map((p, i) => (
                <tr key={i}>
                  <td style={{ textAlign: "center", color: "#64748b", fontWeight: 600 }}>{i + 1}</td>
                  <td>
                    <input
                      type="number" step="0.000001" value={p.lat}
                      onChange={(e) => handleEditPoint(i, "lat", e.target.value)}
                      style={{ width: "100%", fontSize: 12 }}
                    />
                  </td>
                  <td>
                    <input
                      type="number" step="0.000001" value={p.lon}
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
          Объектов: <b>{objects.filter((c) => c.length).length}</b> ·{" "}
          {t.boundaryPointsCount}: <b>{totalPoints}</b>
          {activeContour.length >= 3 && <> · объект {active + 1} {t.boundaryReady}</>}
        </div>
      </div>
    </div>
  );
}
