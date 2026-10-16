// Номер источника — тот, что задал пользователь (0001, 6001, ...). Он идёт
// в таблицы «Радуги» (7, 8, 13), на маркеры карты и в карточки. Если номер
// не задан: число в начале названия («0001», «№154 ДСК №2») считается
// номером, иначе — порядковый номер в списке. То же правило на бэкенде
// (source_number в ond86.py).
const NAME_NUMBER = /^\s*(?:№|N|#)?\s*(\d+)(?!\d)/;

export function sourceNumber(src, index) {
  const n = src?.number != null ? String(src.number).trim() : "";
  if (n) return n;
  const m = NAME_NUMBER.exec(String(src?.name ?? ""));
  if (m) return m[1];
  return String(index + 1).padStart(2, "0");
}
