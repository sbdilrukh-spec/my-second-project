import React from "react";

export default function AddSourceModal({ visible, onClose, onConfirm, t }) {
  if (!visible) return null;
  const overlayStyle = {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(0,0,0,0.4)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2000,
  };
  const boxStyle = {
    width: 360,
    background: "#fff",
    borderRadius: 8,
    padding: 16,
    boxShadow: "0 8px 24px rgba(0,0,0,0.2)",
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={boxStyle} onClick={(e) => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>{t.addSourceTypeTitle || "Тип источника"}</div>
        <div style={{ fontSize: 13, color: "#475569", marginBottom: 14 }}>
          {t.addSourceTypeHelp || "Выберите трубный источник для точечной эмиссии или площадной источник для равномерного распределения по площади."}
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="radio" name="srcType" value="stack" defaultChecked />
            <div>
              <div style={{ fontWeight: 600 }}>{t.typeStack || "Трубный источник"}</div>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                {t.typeStackHelp || "Один точечный источник с высотой, скоростью и температурой выброса."}
              </div>
            </div>
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start", marginTop: 10 }}>
            <input type="radio" name="srcType" value="area" />
            <div>
              <div style={{ fontWeight: 600 }}>{t.typeArea || "Площадной источник"}</div>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                {t.typeAreaHelp || "Источник распределяется по площади и при расчёте разворачивается в сетку точечных источников."}
              </div>
            </div>
          </label>
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn-secondary btn-sm" onClick={onClose}>{t.cancel || "Отмена"}</button>
          <button className="btn-primary btn-sm" onClick={() => {
            const val = document.querySelector('input[name="srcType"]:checked')?.value || "stack";
            onConfirm(val);
          }}>{t.addSource || "Добавить"}</button>
        </div>
      </div>
    </div>
  );
}
