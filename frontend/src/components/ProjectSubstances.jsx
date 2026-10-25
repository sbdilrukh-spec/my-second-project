import React, { useState, useMemo } from "react";

// База веществ проекта (как в «Радуге»): одна строка на код. ПДК, класс и F,
// заданные здесь, действуют во всех источниках сразу — выбросы ссылаются на
// вещество только по коду (см. projectSubstances.js).

// Поле, которое применяет значение только по Enter / уходу фокуса —
// иначе каждый символ пересобирал бы все источники проекта.
function CommitInput({ value, onCommit, numeric = true, width = 80, invalid = false }) {
  const [draft, setDraft] = useState(null);
  const shown = draft ?? (value ?? "");
  const commit = () => {
    if (draft === null) return;
    const v = draft.trim();
    setDraft(null);
    if (!numeric) return v && onCommit(v);
    if (v === "") return onCommit(null);
    const num = parseFloat(v.replace(",", "."));
    if (Number.isFinite(num) && num > 0) onCommit(num);
  };
  return (
    <input
      type="text"
      inputMode={numeric ? "decimal" : "text"}
      value={shown}
      style={{
        width, padding: "3px 6px", fontSize: 12,
        ...(invalid ? { borderColor: "#DC2626", background: "#FEF2F2" } : null),
      }}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") { setDraft(null); e.currentTarget.blur(); }
      }}
    />
  );
}

export default function ProjectSubstances({ db, sources, reference, onAdd, onRemove, onChange, onClose, t }) {
  const [search, setSearch] = useState("");
  const [newCode, setNewCode] = useState("");

  // Сколько источников используют вещество и суммарный выброс, г/с
  const usage = useMemo(() => {
    const m = new Map();
    for (const src of sources) {
      const seen = new Set();
      for (const em of src.emissions || []) {
        const code = em?.substance?.code != null ? String(em.substance.code) : null;
        if (!code) continue;
        const u = m.get(code) || { sources: 0, gs: 0 };
        if (!seen.has(code)) { u.sources += 1; seen.add(code); }
        u.gs += Number(em.emission_gs) || 0;
        m.set(code, u);
      }
    }
    return m;
  }, [sources]);

  const rows = useMemo(() => {
    const q = search.toLowerCase().trim();
    return db
      .filter((s) => !q || String(s.code).toLowerCase().includes(q) || (s.name || "").toLowerCase().includes(q))
      .sort((a, b) => String(a.code).localeCompare(String(b.code), undefined, { numeric: true }));
  }, [db, search]);

  const addNew = () => {
    const code = newCode.trim();
    if (!code) return;
    onAdd(code);
    setNewCode("");
  };
  const newCodeRef = newCode.trim() && reference.find((s) => String(s.code) === newCode.trim());

  return (
    <div className="se-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="se-modal">
        <div className="se-header">
          <h2 className="se-title">{t.projectSubstancesTitle}</h2>
          <button className="se-close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="se-toolbar">
          <input
            type="text"
            className="se-search"
            placeholder={t.searchSubstances}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <input
            type="text"
            value={newCode}
            placeholder={t.substanceCode}
            style={{ width: 80, padding: "4px 6px", fontSize: 12 }}
            onChange={(e) => setNewCode(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addNew(); }}
          />
          <button className="btn-primary btn-sm" onClick={addNew} disabled={!newCode.trim()}>
            + {t.addSubstance}
          </button>
          {newCodeRef && <span style={{ fontSize: 11, color: "#475569" }}>{newCodeRef.name}</span>}
        </div>
        <div style={{ fontSize: 12, color: "#64748B", padding: "0 16px 8px" }}>{t.projectSubstancesHint}</div>

        <div className="se-table-wrap">
          <table className="se-table">
            <thead>
              <tr>
                <th style={{ width: 70 }}>{t.code}</th>
                <th>{t.name}</th>
                <th style={{ width: 60 }}>{t.projectSubstancesSources}</th>
                <th style={{ width: 80 }}>г/с</th>
                <th style={{ width: 100 }}>{t.pdkMr}</th>
                <th style={{ width: 100 }}>{t.pdkSs}</th>
                <th style={{ width: 60 }}>{t.hazardClass}</th>
                <th style={{ width: 60 }}>F</th>
                <th style={{ width: 36 }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={9} style={{ textAlign: "center", color: "#94A3B8" }}>{t.projectSubstancesEmpty}</td></tr>
              )}
              {rows.map((r) => {
                const code = String(r.code);
                const u = usage.get(code);
                const noPdk = !(Number(r.pdk_mr) > 0);
                return (
                  <tr key={code} style={u ? undefined : { opacity: 0.6 }}>
                    <td>{code}</td>
                    <td>
                      <CommitInput value={r.name} numeric={false} width="100%"
                        onCommit={(v) => onChange(code, "name", v)} />
                    </td>
                    <td>{u ? u.sources : "—"}</td>
                    <td>{u?.gs ? u.gs.toPrecision(4) : "—"}</td>
                    <td>
                      <CommitInput value={r.pdk_mr} invalid={noPdk}
                        onCommit={(v) => v != null && onChange(code, "pdk_mr", v)} />
                      {r.pdk_variants?.length > 1 && (
                        <div style={{ fontSize: 10, color: "#B45309", marginTop: 2 }}>
                          {t.projectSubstancesMixed}:{" "}
                          {r.pdk_variants.map((v) => (
                            <button key={v} className="btn-sm btn-secondary"
                              style={{ fontSize: 10, padding: "0 4px", marginRight: 2 }}
                              onClick={() => onChange(code, "pdk_mr", v)}>{v}</button>
                          ))}
                        </div>
                      )}
                    </td>
                    <td>
                      <CommitInput value={r.pdk_ss} onCommit={(v) => onChange(code, "pdk_ss", v)} />
                    </td>
                    <td>
                      <select
                        value={r.hazard_class ?? ""}
                        style={{ fontSize: 12, padding: "2px 4px" }}
                        onChange={(e) => onChange(code, "hazard_class", e.target.value ? Number(e.target.value) : null)}
                      >
                        <option value="">—</option>
                        {[1, 2, 3, 4].map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </td>
                    <td>
                      <CommitInput value={r.F} width={50} onCommit={(v) => onChange(code, "F", v)} />
                    </td>
                    <td>
                      {!u && (
                        <button className="btn-sm" title={t.projectSubstancesRemove}
                          style={{ color: "#DC2626", background: "#FEE2E2", border: "1px solid #FCA5A5", padding: "1px 6px" }}
                          onClick={() => onRemove(code)}>✕</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
