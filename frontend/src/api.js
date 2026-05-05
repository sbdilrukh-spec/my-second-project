import axios from "axios";

const BASE = "/api";

export async function fetchCities() {
  const res = await axios.get(`${BASE}/cities`);
  return res.data;
}

export async function fetchSubstances() {
  const res = await axios.get(`${BASE}/substances`);
  return res.data;
}

export async function addSubstance(substance) {
  const res = await axios.post(`${BASE}/substances`, substance);
  return res.data;
}

export async function updateSubstance(code, substance) {
  const res = await axios.put(`${BASE}/substances/${encodeURIComponent(code)}`, substance);
  return res.data;
}

export async function deleteSubstance(code) {
  const res = await axios.delete(`${BASE}/substances/${encodeURIComponent(code)}`);
  return res.data;
}

export async function restoreDefaultSubstances() {
  const res = await axios.post(`${BASE}/substances/restore-defaults`);
  return res.data;
}

export async function fetchWeather(lat, lon) {
  const res = await axios.get(`${BASE}/weather`, { params: { lat, lon } });
  return res.data;
}

export async function fetchTables(payload) {
  const res = await axios.post(`${BASE}/tables`, payload);
  return res.data;
}

export async function calculate(payload) {
  const res = await axios.post(`${BASE}/calculate`, payload);
  return res.data;
}

export async function exportPdf(payload) {
  try {
    const res = await axios.post(`${BASE}/export/pdf`, payload, {
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "ond86_report.pdf";
    a.click();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    // При ошибке axios возвращает тело как Blob (потому что мы запросили blob).
    // Достаём настоящий текст ошибки, чтобы пользователь увидел причину.
    const status = err.response?.status;
    let bodyText = "";
    if (err.response?.data instanceof Blob) {
      try {
        bodyText = await err.response.data.text();
      } catch { /* ignore */ }
    }

    // Пустое тело = backend упал без ответа (OOM, kill, обрыв сети).
    if (!bodyText || bodyText.trim().length === 0) {
      const w = new Error(
        status
          ? `сервер вернул ${status} с пустым ответом (возможно, не хватило памяти на Render free-tier — попробуйте ещё раз через минуту)`
          : "нет ответа от сервера (потеря соединения или таймаут)"
      );
      w.response = { status, data: null };
      throw w;
    }

    // Пробуем разобрать как JSON и вытащить detail.
    let detail = bodyText;
    let parsedJson = null;
    try {
      parsedJson = JSON.parse(bodyText);
      detail = parsedJson.detail || bodyText;
    } catch {
      // Не JSON — возвращаем сырой текст (обрезаем длинные HTML-страницы).
      if (detail.length > 400) detail = detail.slice(0, 400) + "…";
    }
    const wrapped = new Error(detail);
    wrapped.response = { status, data: parsedJson };
    throw wrapped;
  }
}

// Скачивает ZIP с прозрачными PNG-картами рассеивания (одна на каждое вещество).
// Используется для наложения в CorelDraw на свою подложку.
export async function exportMapPng(payload) {
  try {
    const res = await axios.post(`${BASE}/export/map-png`, payload, {
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/zip" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "karty-rasseivaniya.zip";
    a.click();
    window.URL.revokeObjectURL(url);
  } catch (err) {
    let bodyText = "";
    if (err.response?.data instanceof Blob) {
      try { bodyText = await err.response.data.text(); } catch { /* ignore */ }
    }
    if (!bodyText || bodyText.trim().length === 0) {
      throw new Error(err.response?.status
        ? `сервер вернул ${err.response.status} с пустым ответом`
        : "нет ответа от сервера");
    }
    let detail = bodyText;
    try {
      const json = JSON.parse(bodyText);
      detail = json.detail || bodyText;
    } catch { /* not json */ }
    throw new Error(detail);
  }
}

export async function exportExcel(payload) {
  const res = await axios.post(`${BASE}/export/excel`, payload, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(
    new Blob([res.data], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "ond86_tables.xlsx";
  a.click();
  window.URL.revokeObjectURL(url);
}
