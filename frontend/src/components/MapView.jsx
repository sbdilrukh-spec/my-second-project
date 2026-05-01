import React, { useEffect, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  ImageOverlay,
  Marker,
  Popup,
  Polygon,
  useMapEvents,
  useMap,
} from "react-leaflet";
import L from "leaflet";

// Fix default marker icons
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// ─── Цвет тепловой карты ─────────────────────────────────────────────────────
function heatColor(t) {
  if (t < 0.25) return [59, 130, 246];
  if (t < 0.5)  return [34, 197, 94];
  if (t < 0.75) return [234, 179, 8];
  return [220, 38, 38];
}

// ─── Heatmap (canvas) ─────────────────────────────────────────────────────────
function CanvasHeatmap({ points, maxC }) {
  const map = useMap();

  useEffect(() => {
    if (!points || points.length === 0 || !maxC) return;

    const container = map.getContainer();
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:400;";
    container.appendChild(canvas);

    function draw() {
      const size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, size.x, size.y);

      for (const p of points) {
        const px = map.latLngToContainerPoint([p.lat, p.lon]);
        const ratio = Math.min(p.c / maxC, 1);
        if (ratio < 0.02) continue;
        const r = Math.max(10, 30 * ratio);
        const [R, G, B] = heatColor(ratio);
        const alpha = 0.15 + ratio * 0.55;
        const grad = ctx.createRadialGradient(px.x, px.y, 0, px.x, px.y, r);
        grad.addColorStop(0, `rgba(${R},${G},${B},${alpha})`);
        grad.addColorStop(1, `rgba(${R},${G},${B},0)`);
        ctx.beginPath();
        ctx.fillStyle = grad;
        ctx.arc(px.x, px.y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    draw();
    map.on("zoom zoomend moveend viewreset", draw);
    return () => {
      map.off("zoom zoomend moveend viewreset", draw);
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    };
  }, [points, maxC, map]);

  return null;
}

// ─── Grid Overlay (ОНД-86 стиль) ─────────────────────────────────────────────
function GridOverlay({ points, maxC, gridStep, originLat, originLon, xLength, yLength, sourceOffsetX, sourceOffsetY }) {
  const map = useMap();

  useEffect(() => {
    if (!points || points.length === 0 || !maxC || !gridStep) return;

    const container = map.getContainer();
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:400;";
    container.appendChild(canvas);

    // Вычислить размер ячейки в пикселях при текущем зуме
    function getCellPx() {
      const stepDeg = gridStep / 111000;
      const p1 = map.latLngToContainerPoint([originLat, originLon]);
      const p2 = map.latLngToContainerPoint([originLat + stepDeg, originLon]);
      return Math.max(4, Math.abs(p2.y - p1.y));
    }

    // Смещение точки от начала координат (нижний левый угол) в метрах
    function offsetM(lat, lon) {
      const lat_rad = originLat * Math.PI / 180;
      const dx = Math.round((lon - originLon) * 111000 * Math.cos(lat_rad) / gridStep) * gridStep;
      const dy = Math.round((lat - originLat) * 111000 / gridStep) * gridStep;
      return { dx, dy };
    }

    function draw() {
      const size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;

      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, size.x, size.y);

      const cellPx = getCellPx();
      const showText = cellPx >= 22;
      const fontSize = Math.max(6, Math.min(11, cellPx / 6));
      const half = cellPx / 2;

      // Собираем данные для осей
      const xAxis = {};  // dx → screen x
      const yAxis = {};  // dy → screen y
      let minScreenX = Infinity, maxScreenY = -Infinity;

      // ── Ячейки ──────────────────────────────────────────────────────────────
      for (const p of points) {
        const px = map.latLngToContainerPoint([p.lat, p.lon]);
        const { dx, dy } = offsetM(p.lat, p.lon);
        const ratio = maxC > 0 ? p.c / maxC : 0;
        const isMax = maxC > 0 && Math.abs(p.c - maxC) < maxC * 0.0001;

        // Цвет фона ячейки
        if (isMax) {
          ctx.fillStyle = "rgba(220,38,38,0.45)";
        } else if (ratio > 0.7) {
          ctx.fillStyle = "rgba(255,120,0,0.35)";
        } else if (ratio > 0.3) {
          ctx.fillStyle = "rgba(255,220,0,0.35)";
        } else if (ratio > 0.05) {
          ctx.fillStyle = "rgba(255,255,120,0.25)";
        } else {
          ctx.fillStyle = "rgba(255,255,255,0.08)";
        }

        ctx.fillRect(px.x - half, px.y - half, cellPx, cellPx);

        // Рамка ячейки
        ctx.strokeStyle = "rgba(0,0,0,0.30)";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(px.x - half, px.y - half, cellPx, cellPx);

        // Значение в ячейке
        if (showText && p.c > 0) {
          ctx.font = `${isMax ? "bold " : ""}${fontSize}px monospace`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          if (isMax) {
            // Белый текст с чёрной обводкой — читается на красном фоне
            ctx.lineWidth = 3;
            ctx.strokeStyle = "#000";
            ctx.strokeText(p.c.toFixed(4), px.x, px.y);
            ctx.fillStyle = "#fff";
            ctx.fillText(p.c.toFixed(4), px.x, px.y);
          } else {
            ctx.fillStyle = ratio > 0.6 ? "#7C2D12" : "#111111";
            ctx.fillText(p.c.toFixed(4), px.x, px.y);
          }
        }

        // Собираем для осей (координаты от начала: 0, 500, 1000, ...)
        const xKey = Math.round(dx);
        const yKey = Math.round(dy);
        if (xKey >= 0) xAxis[xKey] = px.x;
        if (yKey >= 0) yAxis[yKey] = px.y;
        if (px.x < minScreenX) minScreenX = px.x;
        if (px.y > maxScreenY) maxScreenY = px.y;
      }

      // ── Оси (жёлтые метки) ──────────────────────────────────────────────────
      if (cellPx >= 14) {
        const labelH = Math.min(cellPx * 0.55, 16);
        const labelW = Math.max(cellPx * 0.9, 36);
        const axFontSize = Math.max(6, Math.min(10, cellPx / 7));

        // Прореживание: показываем метки не чаще чем каждые ~50px на экране
        const allXKeys = Object.keys(xAxis).map(Number).sort((a, b) => a - b);
        const allYKeys = Object.keys(yAxis).map(Number).sort((a, b) => a - b);

        // Вычисляем шаг прореживания
        const minLabelGap = 50; // минимум пикселей между метками
        let xStepLabels = gridStep;
        while (xStepLabels * cellPx / gridStep < minLabelGap && xStepLabels < gridStep * 20) {
          xStepLabels += gridStep;
        }
        // Округляем шаг меток до красивых значений (100, 200, 500, 1000...)
        const niceSteps = [100, 200, 500, 1000, 2000, 5000];
        for (const ns of niceSteps) {
          if (ns >= xStepLabels) { xStepLabels = ns; break; }
        }

        const filteredX = allXKeys.filter((v) => v % xStepLabels === 0);
        const filteredY = allYKeys.filter((v) => v % xStepLabels === 0);

        // X-ось (снизу) — показываем расстояние от источника
        for (const dx of filteredX) {
          const screenX = xAxis[dx];
          if (screenX == null) continue;
          const screenY = maxScreenY + half + 2;
          const label = String(dx);
          ctx.fillStyle = "rgba(255,220,0,0.95)";
          ctx.fillRect(screenX - labelW / 2, screenY, labelW, labelH);
          ctx.strokeStyle = "#333";
          ctx.lineWidth = 0.5;
          ctx.strokeRect(screenX - labelW / 2, screenY, labelW, labelH);
          ctx.fillStyle = "#000";
          ctx.font = `${axFontSize}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(label, screenX, screenY + labelH / 2);
        }
        // подпись X→
        ctx.fillStyle = "#000";
        ctx.font = `bold ${axFontSize + 1}px sans-serif`;
        ctx.textAlign = "right";
        ctx.fillText("X, м →", size.x - 6, maxScreenY + half + labelH / 2 + 2);

        // Y-ось (слева) — показываем расстояние от источника
        const axisLabelW = Math.max(Math.min(cellPx * 0.85, 40), 36);
        for (const dy of filteredY) {
          const screenY = yAxis[dy];
          if (screenY == null) continue;
          const screenX = minScreenX - half - 2;
          const label = String(dy);
          ctx.fillStyle = "rgba(255,220,0,0.95)";
          ctx.fillRect(screenX - axisLabelW, screenY - labelH / 2, axisLabelW, labelH);
          ctx.strokeStyle = "#333";
          ctx.lineWidth = 0.5;
          ctx.strokeRect(screenX - axisLabelW, screenY - labelH / 2, axisLabelW, labelH);
          ctx.fillStyle = "#000";
          ctx.font = `${axFontSize}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(label, screenX - axisLabelW / 2, screenY);
        }
        // подпись ↑Y
        ctx.fillStyle = "#000";
        ctx.font = `bold ${axFontSize + 1}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText("↑ Y, м", minScreenX - half - axisLabelW / 2 - 2, 14);
      }
    }

    draw();
    map.on("zoom zoomend moveend viewreset", draw);
    return () => {
      map.off("zoom zoomend moveend viewreset", draw);
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    };
  }, [points, maxC, gridStep, originLat, originLon, xLength, yLength, sourceOffsetX, sourceOffsetY, map]);

  return null;
}

// ─── Изолинии (Marching Squares) ─────────────────────────────────────────────
function IsolineOverlay({ points, maxC, pdk }) {
  const map = useMap();

  useEffect(() => {
    if (!points || points.length === 0 || !pdk || !maxC) return;

    // Собираем уникальные lat/lon
    const latSet = new Set();
    const lonSet = new Set();
    points.forEach(p => {
      latSet.add(Math.round(p.lat * 100000) / 100000);
      lonSet.add(Math.round(p.lon * 100000) / 100000);
    });

    const lats = Array.from(latSet).sort((a, b) => b - a); // убывание (верх → низ)
    const lons = Array.from(lonSet).sort((a, b) => a - b); // возрастание
    const rows = lats.length;
    const cols = lons.length;
    if (rows < 2 || cols < 2) return;

    // Строим 2D-сетку концентраций (отсутствующие = 0)
    const cMap = {};
    points.forEach(p => {
      const la = Math.round(p.lat * 100000) / 100000;
      const lo = Math.round(p.lon * 100000) / 100000;
      cMap[`${la},${lo}`] = p.c;
    });
    const grid = Array.from({ length: rows }, (_, r) =>
      Array.from({ length: cols }, (_, c) => cMap[`${lats[r]},${lons[c]}`] || 0)
    );

    // Уровни изолиний
    const levels = [
      { value: pdk * 0.5, color: "#3B82F6", label: "0.5 ПДК", width: 1.5 },
      { value: pdk,       color: "#EAB308", label: "1.0 ПДК", width: 2.5 },
      { value: pdk * 2,   color: "#F97316", label: "2.0 ПДК", width: 2 },
      { value: pdk * 5,   color: "#DC2626", label: "5.0 ПДК", width: 2 },
    ].filter(l => l.value <= maxC * 1.1);

    const container = map.getContainer();
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:absolute;top:0;left:0;pointer-events:none;z-index:401;";
    container.appendChild(canvas);

    function getSegments(level) {
      const segs = [];
      for (let r = 0; r < rows - 1; r++) {
        for (let c = 0; c < cols - 1; c++) {
          const v00 = grid[r][c];
          const v10 = grid[r][c + 1];
          const v11 = grid[r + 1][c + 1];
          const v01 = grid[r + 1][c];
          const b = [v00, v10, v11, v01].map(v => v >= level ? 1 : 0);
          const idx = (b[0] << 3) | (b[1] << 2) | (b[2] << 1) | b[3];
          if (idx === 0 || idx === 15) continue;

          function t(va, vb) {
            return Math.abs(vb - va) < 1e-12 ? 0.5 : Math.max(0, Math.min(1, (level - va) / (vb - va)));
          }
          const tT = t(v00, v10), tR = t(v10, v11), tB = t(v01, v11), tL = t(v00, v01);

          const top    = [lats[r],     lons[c] + tT * (lons[c + 1] - lons[c])];
          const right  = [lats[r] + tR * (lats[r + 1] - lats[r]), lons[c + 1]];
          const bottom = [lats[r + 1], lons[c] + tB * (lons[c + 1] - lons[c])];
          const left   = [lats[r] + tL * (lats[r + 1] - lats[r]), lons[c]];

          const edges = { top, right, bottom, left };
          const cases = {
            1: [["left","bottom"]], 2: [["bottom","right"]], 3: [["left","right"]],
            4: [["top","right"]], 5: [["top","right"],["left","bottom"]], 6: [["top","bottom"]],
            7: [["top","left"]], 8: [["top","left"]], 9: [["top","bottom"]],
            10: [["top","left"],["bottom","right"]], 11: [["top","right"]],
            12: [["left","right"]], 13: [["bottom","right"]], 14: [["left","bottom"]],
          };
          (cases[idx] || []).forEach(([a, b]) => segs.push([edges[a], edges[b]]));
        }
      }
      return segs;
    }

    function draw() {
      const size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, size.x, size.y);

      for (const lv of levels) {
        const segs = getSegments(lv.value);
        if (segs.length === 0) continue;

        ctx.strokeStyle = lv.color;
        ctx.lineWidth = lv.width;
        ctx.setLineDash([]);

        for (const [[la, lo], [lb, lob]] of segs) {
          const pa = map.latLngToContainerPoint([la, lo]);
          const pb = map.latLngToContainerPoint([lb, lob]);
          ctx.beginPath();
          ctx.moveTo(pa.x, pa.y);
          ctx.lineTo(pb.x, pb.y);
          ctx.stroke();
        }

        // Подпись на середине первого сегмента
        const mid = segs[Math.floor(segs.length / 2)];
        const pm = map.latLngToContainerPoint(mid[0]);
        ctx.font = "bold 11px sans-serif";
        ctx.lineWidth = 3;
        ctx.strokeStyle = "white";
        ctx.strokeText(lv.label, pm.x + 4, pm.y - 4);
        ctx.fillStyle = lv.color;
        ctx.fillText(lv.label, pm.x + 4, pm.y - 4);
      }

      // Легенда
      if (levels.length > 0) {
        const lx = size.x - 110, ly0 = 10;
        ctx.fillStyle = "rgba(255,255,255,0.92)";
        ctx.strokeStyle = "#ccc";
        ctx.lineWidth = 1;
        ctx.fillRect(lx - 4, ly0 - 4, 108, levels.length * 20 + 8);
        ctx.strokeRect(lx - 4, ly0 - 4, 108, levels.length * 20 + 8);
        levels.forEach((lv, i) => {
          const y = ly0 + i * 20 + 8;
          ctx.strokeStyle = lv.color;
          ctx.lineWidth = lv.width;
          ctx.beginPath();
          ctx.moveTo(lx, y);
          ctx.lineTo(lx + 28, y);
          ctx.stroke();
          ctx.fillStyle = "#1E293B";
          ctx.font = "11px sans-serif";
          ctx.textAlign = "left";
          ctx.textBaseline = "middle";
          ctx.fillText(lv.label, lx + 34, y);
        });
      }
    }

    draw();
    map.on("zoom zoomend moveend viewreset", draw);
    return () => {
      map.off("zoom zoomend moveend viewreset", draw);
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    };
  }, [points, maxC, pdk, map]);

  return null;
}

// ─── Роза ветров ─────────────────────────────────────────────────────────────
function WindRose({ windDirection, windSpeed }) {
  const size = 90;
  const center = size / 2;
  const r = 32;

  // windDirection — откуда дует (метео), стрелка показывает КУДА дует
  const arrowAngle = (windDirection || 0); // откуда дует — стрелка указывает ОТКУДА
  const arrowRad = (arrowAngle - 90) * Math.PI / 180;
  const toRad = (arrowAngle + 90) * Math.PI / 180; // куда дует

  const labels = [
    { text: "С", angle: -90 },
    { text: "В", angle: 0 },
    { text: "Ю", angle: 90 },
    { text: "З", angle: 180 },
  ];

  return (
    <div style={{
      position: "absolute", top: 56, left: 10, zIndex: 1000,
      background: "rgba(255,255,255,0.93)", borderRadius: 8,
      padding: 4, boxShadow: "0 2px 6px rgba(0,0,0,0.25)",
      width: size, height: size + 18, textAlign: "center",
    }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Круг */}
        <circle cx={center} cy={center} r={r + 4} fill="none" stroke="#CBD5E1" strokeWidth="1" />
        <circle cx={center} cy={center} r={r - 8} fill="none" stroke="#E2E8F0" strokeWidth="0.5" />

        {/* Засечки и буквы */}
        {labels.map((l) => {
          const rad = l.angle * Math.PI / 180;
          const x1 = center + Math.cos(rad) * (r - 2);
          const y1 = center + Math.sin(rad) * (r - 2);
          const x2 = center + Math.cos(rad) * (r + 4);
          const y2 = center + Math.sin(rad) * (r + 4);
          const tx = center + Math.cos(rad) * (r + 12);
          const ty = center + Math.sin(rad) * (r + 12);
          return (
            <g key={l.text}>
              <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="#333" strokeWidth="1.5" />
              <text x={tx} y={ty} textAnchor="middle" dominantBaseline="central"
                fontSize="10" fontWeight="bold" fill="#1E293B">{l.text}</text>
            </g>
          );
        })}

        {/* Стрелка — откуда дует */}
        <line
          x1={center + Math.cos(toRad) * (r - 10)}
          y1={center + Math.sin(toRad) * (r - 10)}
          x2={center + Math.cos(arrowRad) * (r - 10)}
          y2={center + Math.sin(arrowRad) * (r - 10)}
          stroke="#DC2626" strokeWidth="2.5"
        />
        {/* Наконечник стрелки (куда дует) */}
        {(() => {
          const tipX = center + Math.cos(toRad) * (r - 10);
          const tipY = center + Math.sin(toRad) * (r - 10);
          const a1 = toRad - 0.4;
          const a2 = toRad + 0.4;
          const sz = 8;
          return (
            <polygon
              points={`${tipX},${tipY} ${tipX - Math.cos(a1) * sz},${tipY - Math.sin(a1) * sz} ${tipX - Math.cos(a2) * sz},${tipY - Math.sin(a2) * sz}`}
              fill="#DC2626"
            />
          );
        })()}

        {/* Центр */}
        <circle cx={center} cy={center} r="3" fill="#1E293B" />
      </svg>
      <div style={{ fontSize: 9, color: "#64748b", marginTop: -2 }}>
        {windSpeed} м/с | {windDirection}°
      </div>
    </div>
  );
}

// ─── Заголовок карты ─────────────────────────────────────────────────────────
function MapTitle({ enterprise, substance, gridXLength, gridYLength }) {
  const name = enterprise?.name || "";
  const subName = substance?.name || "";
  const scale = gridXLength ? `Область: ${gridXLength} x ${gridYLength} м` : "";

  if (!name && !subName) return null;

  return (
    <div style={{
      position: "absolute", top: 10, left: "50%", transform: "translateX(-50%)",
      zIndex: 999, background: "rgba(255,255,255,0.93)",
      borderRadius: 8, padding: "6px 16px",
      boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
      textAlign: "center", maxWidth: "60%",
    }}>
      {name && (
        <div style={{ fontSize: 13, fontWeight: 700, color: "#1E293B" }}>
          Уровень загрязнения атмосферы выбросами
        </div>
      )}
      {name && (
        <div style={{ fontSize: 12, fontWeight: 600, color: "#1E293B" }}>
          {name}
        </div>
      )}
      {subName && (
        <div style={{ fontSize: 11, color: "#64748b" }}>
          Вещество: {subName}
        </div>
      )}
      {scale && (
        <div style={{ fontSize: 10, color: "#94a3b8" }}>{scale}</div>
      )}
    </div>
  );
}

// ─── Кнопки переключения режима ───────────────────────────────────────────────
function ViewToggle({ mode, onChange }) {
  const btnBase = {
    padding: "6px 12px", borderRadius: 6, border: "2px solid #2563EB",
    cursor: "pointer", fontSize: 12, fontWeight: 600,
    transition: "all 0.15s",
  };
  return (
    <div style={{
      position: "absolute", top: 10, right: 50, zIndex: 1000,
      display: "flex", gap: 4, background: "rgba(255,255,255,0.92)",
      borderRadius: 8, padding: "4px", boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
    }}>
      <button
        style={{ ...btnBase, background: mode === "heatmap" ? "#2563EB" : "#fff", color: mode === "heatmap" ? "#fff" : "#2563EB" }}
        onClick={() => onChange("heatmap")}
      >
        🔥 Heatmap
      </button>
      <button
        style={{ ...btnBase, background: mode === "grid" ? "#2563EB" : "#fff", color: mode === "grid" ? "#fff" : "#2563EB" }}
        onClick={() => onChange("grid")}
      >
        ⊞ Сетка ОНД
      </button>
      <button
        style={{ ...btnBase, background: mode === "isolines" ? "#2563EB" : "#fff", color: mode === "isolines" ? "#fff" : "#2563EB" }}
        onClick={() => onChange("isolines")}
      >
        ∿ Изолинии
      </button>
    </div>
  );
}

// ─── Клики на карту ───────────────────────────────────────────────────────────
function ClickHandler({ pickingIndex, onPick, pickingEnterprise, onEnterprisePick }) {
  useMapEvents({
    click(e) {
      if (pickingEnterprise) {
        onEnterprisePick(e.latlng.lat, e.latlng.lng);
        return;
      }
      if (pickingIndex !== null) onPick(pickingIndex, e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

// ─── Центрирование при смене города ──────────────────────────────────────────
function RecenterMap({ center }) {
  const map = useMap();
  const prev = useRef(null);
  useEffect(() => {
    if (!center) return;
    const key = `${center[0]},${center[1]}`;
    if (key !== prev.current) { prev.current = key; map.setView(center, map.getZoom()); }
  }, [center, map]);
  return null;
}

// ─── Тайловые слои ────────────────────────────────────────────────────────────
const TILES = {
  osm: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri",
  },
};

// ─── Главный компонент карты ──────────────────────────────────────────────────
export default function MapView({
  sources, result, pickingIndex, onPick,
  pickingEnterprise, onEnterprisePick,
  onSourceMove, cityCenter,
  viewMode, onViewModeChange, gridStep, gridXLength, gridYLength,
  sourceOffsetX, sourceOffsetY, currentPdk,
  meteo, enterprise, substance,
}) {
  const [mapType, setMapType] = useState("satellite");
  const [bgImage, setBgImage] = useState(null);
  const [bgBounds, setBgBounds] = useState(null);
  const fileInputRef = useRef(null);
  const defaultCenter = cityCenter || [41.2995, 69.2401];

  const gridCenter = sources.length > 0 ? {
    lat: sources.reduce((s, src) => s + (src.lat || 0), 0) / sources.length,
    lon: sources.reduce((s, src) => s + (src.lon || 0), 0) / sources.length,
  } : null;

  // Начало координат (нижний левый угол) — вычисляется от центроида источников
  const gridOrigin = gridCenter ? {
    lat: gridCenter.lat - (sourceOffsetY || 3500) / 111000,
    lon: gridCenter.lon - (sourceOffsetX || 3500) / (111000 * Math.cos(gridCenter.lat * Math.PI / 180)),
  } : null;

  function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setBgImage(ev.target.result);
      const origin = gridOrigin || { lat: defaultCenter[0] - 0.03, lon: defaultCenter[1] - 0.03 };
      const dLat = (gridYLength || 7000) / 111000;
      const dLon = (gridXLength || 7000) / (111000 * Math.cos((origin.lat + dLat / 2) * Math.PI / 180));
      setBgBounds([
        [origin.lat, origin.lon],
        [origin.lat + dLat, origin.lon + dLon],
      ]);
      setMapType("none");
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  }

  return (
    <MapContainer
      center={defaultCenter}
      zoom={13}
      style={{ height: "100%", width: "100%" }}
    >
      {mapType !== "none" && (
        <TileLayer
          url={TILES[mapType].url}
          attribution={TILES[mapType].attribution}
          crossOrigin="anonymous"
        />
      )}
      {bgImage && bgBounds && (
        <ImageOverlay url={bgImage} bounds={bgBounds} opacity={1} />
      )}

      <RecenterMap center={cityCenter} />
      <ClickHandler
        pickingIndex={pickingIndex}
        onPick={onPick}
        pickingEnterprise={pickingEnterprise}
        onEnterprisePick={onEnterprisePick}
      />

      {/* Контур (полигон) предприятия / карьера */}
      {enterprise?.boundary?.length >= 3 && (
        <Polygon
          positions={enterprise.boundary.map((p) => [p.lat, p.lon])}
          pathOptions={{
            color: "#F97316",
            weight: 3,
            fillColor: "#F97316",
            fillOpacity: 0.18,
          }}
        >
          <Popup>
            <b>🏭 {enterprise.name || "Площадка предприятия"}</b><br />
            Точек контура: {enterprise.boundary.length}
          </Popup>
        </Polygon>
      )}

      {/* Маркеры источников */}
      {sources.map((src, i) => (
        <Marker
          key={i}
          position={[src.lat || 41.3, src.lon || 69.24]}
          draggable
          eventHandlers={{ dragend(e) { const ll = e.target.getLatLng(); onSourceMove(i, ll.lat, ll.lng); } }}
          icon={L.divIcon({
            html: `<div style="background:#7C2D12;color:#fff;border-radius:50%;
              width:24px;height:24px;display:flex;align-items:center;justify-content:center;
              font-size:12px;font-weight:bold;border:2px solid #fff;
              box-shadow:0 2px 6px rgba(0,0,0,0.5);font-family:sans-serif;">${i + 1}</div>`,
            className: "",
            iconAnchor: [12, 12],
          })}
        >
          <Popup>
            <b>{src.name}</b><br />
            H={src.height}м D={src.diameter}м<br />
            w₀={src.velocity}м/с T={src.temperature}°C
          </Popup>
        </Marker>
      ))}

      {/* Heatmap */}
      {viewMode === "heatmap" && result?.points?.length > 0 && (
        <CanvasHeatmap points={result.points} maxC={result.max_c || 1} />
      )}

      {/* Сетка ОНД-86 */}
      {viewMode === "grid" && result?.points?.length > 0 && gridOrigin && (
        <GridOverlay
          points={result.points}
          maxC={result.max_c || 1}
          gridStep={gridStep || 500}
          originLat={gridOrigin.lat}
          originLon={gridOrigin.lon}
          xLength={gridXLength || 7000}
          yLength={gridYLength || 7000}
          sourceOffsetX={sourceOffsetX || 3500}
          sourceOffsetY={sourceOffsetY || 3500}
        />
      )}


      {/* Граница СЗЗ */}
      {result?.szz?.boundary?.length > 2 && (
        <Polygon
          positions={result.szz.boundary.map((p) => [p.lat, p.lon])}
          pathOptions={{
            color: "#DC2626",
            weight: 2,
            fillColor: "#DC2626",
            fillOpacity: 0.08,
            dashArray: "6,4",
          }}
        >
          <Popup>
            <b>Граница СЗЗ</b><br />
            Макс. расстояние: {result.szz.max_distance_m} м<br />
            Мин. расстояние: {result.szz.min_distance_m} м<br />
            Площадь превышения: {result.szz.area_ha} га
          </Popup>
        </Polygon>
      )}

      {/* Изолинии */}
      {viewMode === "isolines" && result?.points?.length > 0 && (
        <IsolineOverlay
          points={result.points}
          maxC={result.max_c || 1}
          pdk={currentPdk || result.pdk || 0.5}
        />
      )}

      {/* Кнопки переключения */}
      {result && <ViewToggle mode={viewMode} onChange={onViewModeChange} />}

      {/* Роза ветров */}
      {result && meteo && (
        <WindRose windDirection={meteo.wind_direction} windSpeed={meteo.wind_speed} />
      )}

      {/* Заголовок */}
      {result && viewMode === "grid" && (
        <MapTitle enterprise={enterprise} substance={substance} gridXLength={gridXLength} gridYLength={gridYLength} />
      )}

      {/* Тип карты + загрузка подложки */}
      <div style={{
        position: "absolute", bottom: 30, left: 10, zIndex: 1000,
        display: "flex", gap: 4, background: "rgba(255,255,255,0.92)",
        borderRadius: 8, padding: 4, boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
        flexWrap: "wrap", maxWidth: 320,
      }}>
        {[["osm", "🗺 OSM"], ["satellite", "🛰 Спутник"], ["none", "⬜ Без карты"]].map(([type, label]) => (
          <button key={type} onClick={() => setMapType(type)} style={{
            padding: "4px 10px", borderRadius: 5, border: "1px solid #CBD5E1",
            background: mapType === type ? "#1E40AF" : "#fff",
            color: mapType === type ? "#fff" : "#333",
            cursor: "pointer", fontSize: 11, fontWeight: 600,
          }}>
            {label}
          </button>
        ))}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          style={{ display: "none" }}
          onChange={handleFileUpload}
        />
        <button onClick={() => fileInputRef.current?.click()} style={{
          padding: "4px 10px", borderRadius: 5, border: "1px solid #CBD5E1",
          background: bgImage ? "#059669" : "#fff",
          color: bgImage ? "#fff" : "#333",
          cursor: "pointer", fontSize: 11, fontWeight: 600,
        }}>
          📁 Подложка
        </button>
        {bgImage && (
          <button onClick={() => { setBgImage(null); setBgBounds(null); }} style={{
            padding: "4px 8px", borderRadius: 5, border: "1px solid #FCA5A5",
            background: "#FEE2E2", color: "#DC2626",
            cursor: "pointer", fontSize: 11, fontWeight: 600,
          }}>
            ✕
          </button>
        )}
      </div>

      {/* Подсказка выбора источника */}
      {pickingIndex !== null && (
        <div style={{
          position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
          zIndex: 1000, background: "#1E40AF", color: "#fff",
          padding: "8px 18px", borderRadius: 8, fontSize: 13,
          pointerEvents: "none", whiteSpace: "nowrap",
          boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        }}>
          📍 Кликните для размещения источника {pickingIndex + 1}
        </div>
      )}

      {/* Подсказка выбора точек контура предприятия */}
      {pickingEnterprise && (
        <div style={{
          position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
          zIndex: 1000, background: "#F97316", color: "#fff",
          padding: "8px 18px", borderRadius: 8, fontSize: 13,
          pointerEvents: "none", whiteSpace: "nowrap",
          boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        }}>
          🏭 Кликайте по карте — точки добавляются в контур
          {enterprise?.boundary?.length > 0 && ` (${enterprise.boundary.length})`}
        </div>
      )}
    </MapContainer>
  );
}
