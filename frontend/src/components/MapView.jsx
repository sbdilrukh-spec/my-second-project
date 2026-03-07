import React, { useEffect, useRef, useState } from "react";
import {
  MapContainer,
  TileLayer,
  ImageOverlay,
  Marker,
  Popup,
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
function GridOverlay({ points, maxC, gridStep, centerLat, centerLon }) {
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
      const p1 = map.latLngToContainerPoint([centerLat, centerLon]);
      const p2 = map.latLngToContainerPoint([centerLat + stepDeg, centerLon]);
      return Math.max(4, Math.abs(p2.y - p1.y));
    }

    // Смещение точки от центра сетки в метрах
    function offsetM(lat, lon) {
      const lat_rad = centerLat * Math.PI / 180;
      const dx = Math.round((lon - centerLon) * 111000 * Math.cos(lat_rad) / gridStep) * gridStep;
      const dy = Math.round((lat - centerLat) * 111000 / gridStep) * gridStep;
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
          ctx.fillStyle = isMax ? "#CC0000" : (ratio > 0.6 ? "#7C2D12" : "#111111");
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(p.c.toFixed(4), px.x, px.y);
        }

        // Собираем для осей
        const xKey = Math.round(dx);
        const yKey = Math.round(dy);
        if (!xAxis[xKey]) xAxis[xKey] = px.x;
        if (!yAxis[yKey]) yAxis[yKey] = px.y;
        if (px.x < minScreenX) minScreenX = px.x;
        if (px.y > maxScreenY) maxScreenY = px.y;
      }

      // ── Оси (жёлтые метки) ──────────────────────────────────────────────────
      if (cellPx >= 14) {
        const labelH = Math.min(cellPx * 0.55, 16);
        const labelW = cellPx * 0.9;
        const axFontSize = Math.max(6, Math.min(10, cellPx / 7));

        // X-ось (снизу)
        for (const [dxStr, screenX] of Object.entries(xAxis)) {
          const screenY = maxScreenY + half + 2;
          ctx.fillStyle = "rgba(255,220,0,0.95)";
          ctx.fillRect(screenX - labelW / 2, screenY, labelW, labelH);
          ctx.strokeStyle = "#333";
          ctx.lineWidth = 0.5;
          ctx.strokeRect(screenX - labelW / 2, screenY, labelW, labelH);
          ctx.fillStyle = "#000";
          ctx.font = `${axFontSize}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(dxStr, screenX, screenY + labelH / 2);
        }
        // подпись X→
        ctx.fillStyle = "#000";
        ctx.font = `bold ${axFontSize + 1}px sans-serif`;
        ctx.textAlign = "right";
        ctx.fillText("X, м→", size.x - 6, maxScreenY + half + labelH / 2 + 2);

        // Y-ось (слева)
        const axisLabelW = Math.min(cellPx * 0.85, 40);
        for (const [dyStr, screenY] of Object.entries(yAxis)) {
          const screenX = minScreenX - half - 2;
          ctx.fillStyle = "rgba(255,220,0,0.95)";
          ctx.fillRect(screenX - axisLabelW, screenY - labelH / 2, axisLabelW, labelH);
          ctx.strokeStyle = "#333";
          ctx.lineWidth = 0.5;
          ctx.strokeRect(screenX - axisLabelW, screenY - labelH / 2, axisLabelW, labelH);
          ctx.fillStyle = "#000";
          ctx.font = `${axFontSize}px sans-serif`;
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(dyStr, screenX - axisLabelW / 2, screenY);
        }
        // подпись ↑Y
        ctx.fillStyle = "#000";
        ctx.font = `bold ${axFontSize + 1}px sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText("↑Y, м", minScreenX - half - axisLabelW / 2 - 2, 14);
      }
    }

    draw();
    map.on("zoom zoomend moveend viewreset", draw);
    return () => {
      map.off("zoom zoomend moveend viewreset", draw);
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    };
  }, [points, maxC, gridStep, centerLat, centerLon, map]);

  return null;
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
    </div>
  );
}

// ─── Клики на карту ───────────────────────────────────────────────────────────
function ClickHandler({ pickingIndex, onPick }) {
  useMapEvents({
    click(e) {
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
  sources, result, pickingIndex, onPick, onSourceMove, cityCenter,
  viewMode, onViewModeChange, gridStep, gridRadius,
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

  function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setBgImage(ev.target.result);
      const center = gridCenter || { lat: defaultCenter[0], lon: defaultCenter[1] };
      const radiusM = gridRadius || 3000;
      const dLat = radiusM / 111000;
      const dLon = radiusM / (111000 * Math.cos(center.lat * Math.PI / 180));
      setBgBounds([
        [center.lat - dLat, center.lon - dLon],
        [center.lat + dLat, center.lon + dLon],
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
        <TileLayer url={TILES[mapType].url} attribution={TILES[mapType].attribution} />
      )}
      {bgImage && bgBounds && (
        <ImageOverlay url={bgImage} bounds={bgBounds} opacity={1} />
      )}

      <RecenterMap center={cityCenter} />
      <ClickHandler pickingIndex={pickingIndex} onPick={onPick} />

      {/* Маркеры источников */}
      {sources.map((src, i) => (
        <Marker
          key={i}
          position={[src.lat || 41.3, src.lon || 69.24]}
          draggable
          eventHandlers={{ dragend(e) { const ll = e.target.getLatLng(); onSourceMove(i, ll.lat, ll.lng); } }}
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
      {viewMode === "grid" && result?.points?.length > 0 && gridCenter && (
        <GridOverlay
          points={result.points}
          maxC={result.max_c || 1}
          gridStep={gridStep || 100}
          centerLat={gridCenter.lat}
          centerLon={gridCenter.lon}
        />
      )}

      {/* Маркер максимума */}
      {result && (
        <Marker
          position={[result.max_lat, result.max_lon]}
          icon={L.divIcon({
            html: `<div style="background:#DC2626;color:#fff;border-radius:50%;width:28px;height:28px;
              display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:bold;
              border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.5)">★</div>`,
            className: "",
            iconAnchor: [14, 14],
          })}
        >
          <Popup>
            <b>Максимум концентрации</b><br />
            C = {result.max_c.toFixed(4)} мг/м³<br />
            {result.exceeds_pdk
              ? `⚠ Превышение ПДК в ${(result.max_c / result.pdk).toFixed(2)} раза`
              : "✓ ПДК не превышена"}
          </Popup>
        </Marker>
      )}

      {/* Кнопки переключения */}
      {result && <ViewToggle mode={viewMode} onChange={onViewModeChange} />}

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
    </MapContainer>
  );
}
