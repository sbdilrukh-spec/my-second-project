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
    // Достаём настоящий текст ошибки, чтобы пользователь увидел причину,
    // а не голую "Ошибка генерации PDF".
    if (err.response?.data instanceof Blob) {
      const text = await err.response.data.text();
      try {
        const json = JSON.parse(text);
        const detail = json.detail || text;
        const wrapped = new Error(detail);
        wrapped.response = { status: err.response.status, data: json };
        throw wrapped;
      } catch (parseErr) {
        if (parseErr instanceof Error && parseErr.message && parseErr !== err) {
          throw parseErr;
        }
        throw new Error(text || err.message);
      }
    }
    throw err;
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
