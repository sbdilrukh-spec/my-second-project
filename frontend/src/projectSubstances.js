// База веществ проекта (как в «Радуге»): одна запись на код вещества.
// Источники ссылаются на вещество по коду; ПДК, класс и F берутся только
// отсюда — resolveSources() подставляет их во все выбросы перед расчётом,
// экспортом и сохранением. Копии внутри выбросов остаются лишь для
// совместимости со старыми файлами и бэкендом.

const FIELDS = ["code", "name", "pdk_mr", "pdk_ss", "hazard_class", "F"];

export function substanceKey(sub) {
  return sub && sub.code != null && sub.code !== "" ? String(sub.code) : null;
}

function pick(sub) {
  const out = {};
  for (const f of FIELDS) out[f] = sub?.[f] ?? null;
  out.code = String(out.code);
  return out;
}

// Записи для кодов, которые есть в выбросах, но отсутствуют в базе.
// Если в источниках у вещества разные ПДК — берём самое частое значение,
// а все варианты кладём в pdk_variants: окно базы попросит выбрать одно.
export function collectMissing(sources, db, reference) {
  const known = new Set(db.map((s) => String(s.code)));
  const groups = new Map();
  for (const src of sources) {
    for (const em of src.emissions || []) {
      const code = substanceKey(em?.substance);
      if (!code || known.has(code)) continue;
      if (!groups.has(code)) groups.set(code, { sub: em.substance, pdks: new Map() });
      const pdk = Number(em.pdk ?? em.substance.pdk_mr);
      if (pdk > 0) groups.get(code).pdks.set(pdk, (groups.get(code).pdks.get(pdk) || 0) + 1);
    }
  }
  const added = [];
  for (const [code, { sub, pdks }] of groups) {
    const ref = reference.find((s) => String(s.code) === code);
    const entry = pick({ ...ref, ...Object.fromEntries(Object.entries(sub).filter(([, v]) => v != null)) });
    const ranked = [...pdks.entries()].sort((a, b) => b[1] - a[1]).map(([v]) => v);
    if (ranked.length > 0) entry.pdk_mr = ranked[0];
    if (ranked.length > 1) entry.pdk_variants = [...ranked].sort((a, b) => a - b);
    added.push(entry);
  }
  return added;
}

// Запись базы для введённого кода: из справочника, иначе пустая (ПДК заполнить).
export function entryForCode(code, reference) {
  const ref = reference.find((s) => String(s.code) === String(code));
  return ref ? pick(ref) : { ...pick({ code }), name: String(code) };
}

export function resolveSources(sources, dbMap) {
  return sources.map((src) => {
    if (!Array.isArray(src.emissions)) return src;
    let changed = false;
    const ems = src.emissions.map((em) => {
      const entry = dbMap.get(substanceKey(em?.substance));
      if (!entry) return em;
      changed = true;
      return { ...em, substance: pick(entry), pdk: entry.pdk_mr ?? em.pdk };
    });
    return changed ? { ...src, emissions: ems } : src;
  });
}

// Коды веществ, которые используются в выбросах, но без ПДК м.р. в базе.
export function missingPdkCodes(sources, dbMap) {
  const out = new Set();
  for (const src of sources) {
    for (const em of src.emissions || []) {
      const entry = dbMap.get(substanceKey(em?.substance));
      if (entry && !(Number(entry.pdk_mr) > 0)) out.add(entry.code);
    }
  }
  return [...out];
}
