// Practical implications derived transparently from the snapshot: travel, business, spillover.
import { percent } from './data';
import type { CountryEntry, HazardDetails, Lang, Snapshot } from './data';

export type Level = 1 | 2 | 3 | 4;
export interface Verdict { level: Level; official: boolean; reasons: string[] }

const T = {
  ru: {
    travel: ['', 'Обычные меры предосторожности', 'Повышенная осторожность', 'Пересмотрите необходимость поездки', 'Не ехать'],
    business: ['', 'Низкий риск', 'Умеренный риск', 'Высокий риск', 'Критический риск'],
    activeConflict: (t: string) => `Сейчас идёт: ${t.toLowerCase()}.`,
    onset: (t: string, p: string) => `${t}: вероятность начала в ближайший год — ${p}.`,
    humanitarian: 'Действует гуманитарный план ООН: перебои с услугами, логистикой и безопасностью.',
    economic: (p: string) => `Вероятность экономического кризиса (падение ВВП или инфляция выше 40%) в ближайший год — ${p}.`,
    seasonSoon: (t: string, months: string) => `Ближайшие месяцы (${months}) — сезон: ${t.toLowerCase()}.`,
    hazardYear: (t: string, p: string) => `${t}: вероятность в течение года — ${p}; возможны перебои в транспорте и поставках.`,
    officialSource: 'Официальная оценка Госдепартамента США',
    modelSource: 'Оценка GeoIntel по данным модели (официальной оценки нет)',
    trade: (x: string) => `Экономика сильно зависит от внешней торговли (${x} ВВП) — чувствительна к сбоям в портах и санкциям.`,
    fuelImports: (x: string) => `Топливо — ${x} импорта: рост мировых цен на нефть быстро бьёт по экономике.`,
    foodImports: (x: string) => `Продовольствие — ${x} импорта: уязвимость к росту мировых цен на зерно.`,
    tourism: (x: string) => `Туризм — ${x} экспорта: кризисы и бедствия быстро бьют по доходам страны.`,
    remittances: (x: string) => `Денежные переводы мигрантов — ${x} ВВП: зависимость от экономик стран, где работают мигранты.`,
    calm: 'Существенных факторов риска по имеющимся данным не выявлено.',
    oil: (x: string) => `Крупный экспортёр топлива (${x} экспорта): обострение здесь отражается на мировых ценах на нефть и газ.`,
    food: (x: string) => `Крупный экспортёр продовольствия (${x} экспорта): кризис может поднять мировые цены на еду.`,
    bigEconomy: (x: string) => `${x} мирового ВВП: проблемы здесь заметно отразятся на мировой торговле и рынках.`,
    neighboursAtWar: (names: string) => `У соседей идёт вооружённый конфликт: ${names}. Возможны беженцы, закрытие границ и рост напряжённости.`,
    exportsInstability: (names: string) => `Конфликт может затронуть соседние страны: ${names} — беженцы, торговля, безопасность границ.`,
    noSpillover: 'Заметных каналов влияния на другие страны по имеющимся данным не видно.',
  },
  en: {
    travel: ['', 'Exercise normal precautions', 'Exercise increased caution', 'Reconsider travel', 'Do not travel'],
    business: ['', 'Low risk', 'Moderate risk', 'High risk', 'Critical risk'],
    activeConflict: (t: string) => `Ongoing now: ${t.toLowerCase()}.`,
    onset: (t: string, p: string) => `${t}: ${p} probability of onset within a year.`,
    humanitarian: 'A UN humanitarian plan is active: disrupted services, logistics and security.',
    economic: (p: string) => `${p} probability of an economic crisis (GDP fall or inflation above 40%) within a year.`,
    seasonSoon: (t: string, months: string) => `The coming months (${months}) are the season for: ${t.toLowerCase()}.`,
    hazardYear: (t: string, p: string) => `${t}: ${p} within a year; transport and supply disruption possible.`,
    officialSource: 'Official U.S. Department of State assessment',
    modelSource: 'GeoIntel model-based assessment (no official advisory)',
    trade: (x: string) => `The economy depends heavily on trade (${x} of GDP): sensitive to port disruption and sanctions.`,
    fuelImports: (x: string) => `Fuel is ${x} of imports: higher world oil prices hit the economy quickly.`,
    foodImports: (x: string) => `Food is ${x} of imports: vulnerable to higher world grain prices.`,
    tourism: (x: string) => `Tourism is ${x} of exports: crises and disasters hit national income quickly.`,
    remittances: (x: string) => `Remittances are ${x} of GDP: dependent on the economies where migrants work.`,
    calm: 'No significant risk factors in the available data.',
    oil: (x: string) => `Major fuel exporter (${x} of exports): escalation here moves world oil and gas prices.`,
    food: (x: string) => `Major food exporter (${x} of exports): a crisis could raise world food prices.`,
    bigEconomy: (x: string) => `${x} of world GDP: problems here noticeably affect world trade and markets.`,
    neighboursAtWar: (names: string) => `Armed conflict in neighbouring countries: ${names}. Refugees, border closures and tension are possible.`,
    exportsInstability: (names: string) => `The conflict may affect neighbours: ${names} — refugees, trade, border security.`,
    noSpillover: 'No notable channels of impact on other countries in the available data.',
  },
};
export const levelLabel = (kind: 'travel' | 'business', level: Level, lang: Lang) => T[lang][kind][level];

const pct = (x: number, lang: Lang) => percent(x / 100, lang);
const conflictKeys = ['internal_armed_conflict', 'interstate_conflict'];
const hazardKeys = ['tropical_cyclone', 'flood', 'major_earthquake', 'wildfire', 'volcano', 'tsunami', 'drought'];

function upcomingSeason(country: CountryEntry, hazards: HazardDetails | undefined, now: Date) {
  const data = hazards?.countries[country.iso3];
  if (!data) return [] as { type: string; months: number[] }[];
  const next = [0, 1, 2].map((k) => (now.getUTCMonth() + k) % 12);
  return ['tropical_cyclone', 'flood', 'wildfire'].flatMap((type) => {
    const months = data[type]?.months;
    if (!months || (data[type]?.count ?? 0) < 3) return [];
    const total = months.reduce((a, b) => a + b, 0);
    const share = next.reduce((a, m) => a + months[m], 0) / total;
    return share >= 0.4 ? [{ type, months: next }] : [];
  });
}

export function travelVerdict(
  country: CountryEntry, snapshot: Snapshot, label: (key: string) => string, lang: Lang,
  hazards?: HazardDetails, monthNames: string[] = [], now = new Date(),
): Verdict {
  const t = T[lang];
  const reasons: string[] = [];
  let model: Level = 1;
  for (const key of conflictKeys) {
    const r = country.risks[key];
    if (!r) continue;
    if (r.active) { reasons.push(t.activeConflict(label(key))); model = 4; }
    else if (r.horizons['1y'].p >= 0.1) { reasons.push(t.onset(label(key), percent(r.horizons['1y'].p, lang))); model = Math.max(model, 3) as Level; }
  }
  if (country.risks.humanitarian_crisis?.active) { reasons.push(t.humanitarian); model = Math.max(model, 3) as Level; }
  for (const season of upcomingSeason(country, hazards, now)) {
    reasons.push(t.seasonSoon(label(season.type), season.months.map((m) => monthNames[m]).join(', ')));
    model = Math.max(model, 2) as Level;
  }
  const quake = country.risks.major_earthquake?.horizons['1m'].p ?? 0;
  if (quake >= 0.05) { reasons.push(t.hazardYear(label('major_earthquake'), percent(country.risks.major_earthquake.horizons['1y'].p, lang))); model = Math.max(model, 2) as Level; }
  const official = country.advisory?.level;
  if (!reasons.length) reasons.push(t.calm);
  void snapshot;
  return { level: (official ?? model) as Level, official: !!official, reasons };
}

export function businessVerdict(country: CountryEntry, label: (key: string) => string, lang: Lang): Verdict {
  const t = T[lang];
  const reasons: string[] = [];
  let level: Level = 1;
  const raise = (to: Level) => { level = Math.max(level, to) as Level; };
  for (const key of conflictKeys) {
    const r = country.risks[key];
    if (!r) continue;
    if (r.active) { reasons.push(t.activeConflict(label(key))); raise(4); }
    else if (r.horizons['1y'].p >= 0.1) { reasons.push(t.onset(label(key), percent(r.horizons['1y'].p, lang))); raise(3); }
  }
  if (country.risks.humanitarian_crisis?.active) { reasons.push(t.humanitarian); raise(3); }
  const econ = country.risks.economic_crisis?.horizons['1y'].p;
  if (econ !== undefined && econ >= 0.12) { reasons.push(t.economic(percent(econ, lang))); raise(econ >= 0.25 ? 3 : 2); }
  for (const key of ['tropical_cyclone', 'flood', 'major_earthquake']) {
    const p = country.risks[key]?.horizons['1y'].p ?? 0;
    if (p >= 0.5) { reasons.push(t.hazardYear(label(key), percent(p, lang))); raise(2); }
  }
  const pr = country.profile ?? {};
  const v = (k: string) => pr[k]?.value;
  if ((v('trade_gdp') ?? 0) > 100) reasons.push(t.trade(pct(v('trade_gdp')!, lang)));
  if ((v('fuel_imports_share') ?? 0) > 20) reasons.push(t.fuelImports(pct(v('fuel_imports_share')!, lang)));
  if ((v('food_imports_share') ?? 0) > 20) reasons.push(t.foodImports(pct(v('food_imports_share')!, lang)));
  if ((v('tourism_exports_share') ?? 0) > 20) reasons.push(t.tourism(pct(v('tourism_exports_share')!, lang)));
  if ((v('remittances_gdp') ?? 0) > 10) reasons.push(t.remittances(pct(v('remittances_gdp')!, lang)));
  if (!reasons.length) reasons.push(t.calm);
  return { level, official: false, reasons };
}

export function spillover(
  country: CountryEntry, neighbours: CountryEntry[], name: (c: CountryEntry) => string, lang: Lang,
): string[] {
  const t = T[lang];
  const lines: string[] = [];
  const pr = country.profile ?? {};
  const v = (k: string) => pr[k]?.value ?? 0;
  if (v('fuel_exports_share') > 40 || v('oil_rents_gdp') > 10) lines.push(t.oil(pct(Math.max(v('fuel_exports_share'), 0), lang)));
  if (v('food_exports_share') > 30) lines.push(t.food(pct(v('food_exports_share'), lang)));
  if (v('world_gdp_share') >= 1) lines.push(t.bigEconomy(pct(v('world_gdp_share'), lang)));
  const atWar = neighbours.filter((n) => conflictKeys.some((k) => n.risks[k]?.active));
  if (atWar.length) lines.push(t.neighboursAtWar(atWar.map(name).join(', ')));
  if (conflictKeys.some((k) => country.risks[k]?.active) && neighbours.length) {
    lines.push(t.exportsInstability(neighbours.map(name).join(', ')));
  }
  if (!lines.length) lines.push(t.noSpillover);
  return lines;
}

export const hazardTypes = hazardKeys;
