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
  const res = await axios.post(`${BASE}/export/pdf`, payload, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "ond86_report.pdf";
  a.click();
  window.URL.revokeObjectURL(url);
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
