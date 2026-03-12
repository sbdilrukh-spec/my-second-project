import React from "react";

function fmt(val, digits = 4) {
  const n = parseFloat(val);
  return isNaN(n) ? "—" : n.toFixed(digits);
}

export default function ScenarioPanel({
  scenarioMode,
  onToggle,
  onSaveBaseline,
  baselineResult,
  currentResult,
  t,
}) {
  return (
    <div className="panel-section">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 className="section-title" style={{ margin: 0 }}>{t.scenarios}</h3>
        <button
          className={`btn-sm ${scenarioMode ? "btn-primary" : "btn-secondary"}`}
          onClick={onToggle}
        >
          {scenarioMode ? t.scenarioOn : t.scenarioOff}
        </button>
      </div>

      {scenarioMode && (
        <div style={{ marginTop: 8 }}>
          <button
            className="btn-secondary btn-sm"
            style={{ width: "100%", marginBottom: 8 }}
            onClick={onSaveBaseline}
            disabled={!currentResult}
          >
            {t.saveBaseline}
          </button>

          {baselineResult && currentResult && (
            <div style={{ fontSize: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{t.scenarioComparison}</div>
              <table className="result-table" style={{ fontSize: 11 }}>
                <thead>
                  <tr>
                    <th>{t.scenarioParam}</th>
                    <th>{t.scenarioBefore}</th>
                    <th>{t.scenarioAfter}</th>
                    <th>%</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Cmax, мг/м³</td>
                    <td>{fmt(baselineResult.max_c, 5)}</td>
                    <td>{fmt(currentResult.max_c, 5)}</td>
                    <td style={{
                      color: currentResult.max_c < baselineResult.max_c ? "#16A34A" : "#DC2626",
                      fontWeight: 600,
                    }}>
                      {baselineResult.max_c > 0
                        ? `${((currentResult.max_c - baselineResult.max_c) / baselineResult.max_c * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                  </tr>
                  <tr>
                    <td>Cmax/ПДК</td>
                    <td>{fmt(baselineResult.max_c / baselineResult.pdk, 3)}</td>
                    <td>{fmt(currentResult.max_c / currentResult.pdk, 3)}</td>
                    <td></td>
                  </tr>
                  {baselineResult.szz && currentResult.szz && (
                    <tr>
                      <td>СЗЗ макс, м</td>
                      <td>{fmt(baselineResult.szz.max_distance_m, 0)}</td>
                      <td>{fmt(currentResult.szz.max_distance_m, 0)}</td>
                      <td style={{
                        color: currentResult.szz.max_distance_m < baselineResult.szz.max_distance_m ? "#16A34A" : "#DC2626",
                        fontWeight: 600,
                      }}>
                        {baselineResult.szz.max_distance_m > 0
                          ? `${((currentResult.szz.max_distance_m - baselineResult.szz.max_distance_m) / baselineResult.szz.max_distance_m * 100).toFixed(1)}%`
                          : "—"}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
