import axios from "axios";

const BASE = "/api";

export async function fetchCities() {
  const res = await axios.get(`${BASE}/cities`);
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
