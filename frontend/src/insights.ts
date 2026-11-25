// Practical implications derived transparently from the snapshot: travel, business, spillover.
// Principle: country-wide verdicts come from official advisories; model signals are shown as
// specific reasons and regional notes, never as blanket bans on a whole country.
import { percent } from './data';
import type { CountryEntry, HazardDetails, Lang } from './data';

export type Level = 1 | 2 | 3 | 4;
export interface Verdict { level: Level; official: boolean; reasons: string[]; regional: string[] }

const T = {
  ru: {
    travel: ['', 'Обычные меры предосторожности', 'Повышенная осторожность', 'Пересмотрите необходимость поездки', 'Не ехать'],
    business: ['', 'Низкий риск', 'Умеренный риск', 'Высокий риск', 'Критический риск'],
    usLevel: (l: number, label: string) => `Госдепартамент США: уровень ${l} — «${label}».`,
    ukWhole: (l: number) => l >= 4 ? 'МИД Великобритании не рекомендует любые поездки в страну.' : 'МИД Великобритании рекомендует ездить в страну только при крайней необходимости.',
    ukParts: 'МИД Великобритании не рекомендует поездки в отдельные районы страны (список ниже); остальная территория — без особых ограничений.',
    ukNone: 'МИД Великобритании не вводит ограничений на поездки.',
    internalActive: 'В отдельных районах страны идёт вооружённый конфликт. Уточните, какие районы затронуты, в официальных рекомендациях.',
    interstateActive: 'Страна — сторона межгосударственного вооружённого конфликта. Само по себе это не означает опасности на её территории: ориентируйтесь на официальные рекомендации.',
    onset: (t: string, p: string) => `${t}: вероятность начала в ближайший год — ${p}.`,
    humanitarian: 'Действует гуманитарный план ООН: перебои с услугами, логистикой и безопасностью в пострадавших районах.',
    regional: (t: string, where: string, season: string) => `${t}: ${where}${season}.`,
    regionalNoPlace: 'места событий не определены',
    seasonPart: (months: string) => ` — чаще всего в ${months}`,
    soon: ' (сезон уже скоро)',
    calm: 'Существенных факторов риска по имеющимся данным не выявлено.',
    noOfficial: 'Официальных оценок нет — уровень рассчитан моделью GeoIntel.',
    interstateBusiness: 'Страна — сторона межгосударственного конфликта: риски санкций, ответных ударов, кибератак и перебоев в экспорте.',
    internalBusiness: 'Идёт внутренний вооружённый конфликт: угроза активам, персоналу и логистике в затронутых районах.',
    economic: (p: string) => `Вероятность экономического кризиса (падение ВВП или инфляция выше 40%) в ближайший год — ${p}.`,
    imf: (parts: string) => `Прогноз МВФ: ${parts}.`,
    imfGrowth: (y: string, v: string) => `рост ВВП в ${y} г. ${v}`,
    imfInfl: (y: string, v: string) => `инфляция в ${y} г. ${v}`,
    hazardBusiness: (t: string, where: string) => `${t}: возможны перебои в логистике и поставках (${where}).`,
    trade: (x: string) => `Экономика сильно зависит от внешней торговли (${x} ВВП) — чувствительна к сбоям в портах и санкциям.`,
    fuelImports: (x: string) => `Топливо — ${x} импорта: рост мировых цен на нефть быстро бьёт по экономике.`,
    foodImports: (x: string) => `Продовольствие — ${x} импорта: уязвимость к росту мировых цен на зерно.`,
    tourism: (x: string) => `Туризм — ${x} экспорта: кризисы и бедствия быстро бьют по доходам страны.`,
    remittances: (x: string) => `Денежные переводы мигрантов — ${x} ВВП: зависимость от экономик стран, где работают мигранты.`,
    election: (name: string, when: string) => `Предстоят выборы: ${name} (${when}). Возможны протесты и волатильность.`,
    oil: (x: string) => `Крупный экспортёр топлива (${x} экспорта): обострение здесь отражается на мировых ценах на нефть и газ.`,
    food: (x: string) => `Крупный экспортёр продовольствия (${x} экспорта): кризис может поднять мировые цены на еду.`,
    bigEconomy: (x: string) => `${x} мирового ВВП: проблемы здесь заметно отразятся на мировой торговле и рынках.`,
    neighboursAtWar: (names: string) => `На территории соседних стран идёт вооружённый конфликт: ${names}. Возможны беженцы, закрытие границ и рост напряжённости.`,
    exportsInstability: (names: string) => `Внутренний конфликт может затронуть соседей: ${names} — беженцы, торговля, безопасность границ.`,
    noSpillover: 'Заметных каналов влияния на другие страны по имеющимся данным не видно.',
  },
  en: {
    travel: ['', 'Exercise normal precautions', 'Exercise increased caution', 'Reconsider travel', 'Do not travel'],
    business: ['', 'Low risk', 'Moderate risk', 'High risk', 'Critical risk'],
    usLevel: (l: number, label: string) => `U.S. State Department: level ${l} — “${label}”.`,
    ukWhole: (l: number) => l >= 4 ? 'The UK FCDO advises against all travel to the country.' : 'The UK FCDO advises against all but essential travel to the country.',
    ukParts: 'The UK FCDO advises against travel to parts of the country (see below); elsewhere there are no special restrictions.',
    ukNone: 'The UK FCDO has no travel restrictions.',
    internalActive: 'Armed conflict is ongoing in parts of the country. Check official advice for the affected areas.',
    interstateActive: 'The country is a party to an interstate armed conflict. This alone does not mean danger on its territory: follow official advice.',
    onset: (t: string, p: string) => `${t}: ${p} probability of onset within a year.`,
    humanitarian: 'A UN humanitarian plan is active: disrupted services, logistics and security in affected areas.',
    regional: (t: string, where: string, season: string) => `${t}: ${where}${season}.`,
    regionalNoPlace: 'locations not determined',
    seasonPart: (months: string) => ` — most often in ${months}`,
    soon: ' (season starting soon)',
    calm: 'No significant risk factors in the available data.',
    noOfficial: 'No official advisory — level estimated by the GeoIntel model.',
    interstateBusiness: 'Party to an interstate conflict: risks of sanctions, retaliation, cyberattacks and export disruption.',
    internalBusiness: 'Internal armed conflict: threats to assets, staff and logistics in affected areas.',
    economic: (p: string) => `${p} probability of an economic crisis (GDP fall or inflation above 40%) within a year.`,
    imf: (parts: string) => `IMF projection: ${parts}.`,
    imfGrowth: (y: string, v: string) => `GDP growth in ${y} ${v}`,
    imfInfl: (y: string, v: string) => `inflation in ${y} ${v}`,
    hazardBusiness: (t: string, where: string) => `${t}: possible logistics and supply disruption (${where}).`,
    trade: (x: string) => `The economy depends heavily on trade (${x} of GDP): sensitive to port disruption and sanctions.`,
    fuelImports: (x: string) => `Fuel is ${x} of imports: higher world oil prices hit the economy quickly.`,
    foodImports: (x: string) => `Food is ${x} of imports: vulnerable to higher world grain prices.`,
    tourism: (x: string) => `Tourism is ${x} of exports: crises and disasters hit national income quickly.`,
    remittances: (x: string) => `Remittances are ${x} of GDP: dependent on the economies where migrants work.`,
    election: (name: string, when: string) => `Upcoming election: ${name} (${when}). Protests and volatility are possible.`,
    oil: (x: string) => `Major fuel exporter (${x} of exports): escalation here moves world oil and gas prices.`,
    food: (x: string) => `Major food exporter (${x} of exports): a crisis could raise world food prices.`,
    bigEconomy: (x: string) => `${x} of world GDP: problems here noticeably affect world trade and markets.`,
    neighboursAtWar: (names: string) => `Armed conflict on the territory of neighbouring countries: ${names}. Refugees, border closures and tension are possible.`,
    exportsInstability: (names: string) => `The internal conflict may affect neighbours: ${names} — refugees, trade, border security.`,
    noSpillover: 'No notable channels of impact on other countries in the available data.',
  },
};
export const levelLabel = (kind: 'travel' | 'business', level: Level, lang: Lang) => T[lang][kind][level];

const pct = (x: number, lang: Lang) => percent(x / 100, lang);
const hazardOrder = ['tropical_cyclone', 'flood', 'major_earthquake', 'tsunami', 'volcano', 'wildfire', 'drought'];

/** Regional notes: where each hazard hits and in which months (never a whole-country ban). */
export function regionalNotes(
  country: CountryEntry, hazards: HazardDetails | undefined, label: (key: string) => string,
  lang: Lang, monthNames: string[], now = new Date(),
): string[] {
  const t = T[lang];
  const data = hazards?.countries[country.iso3];
  if (!data) return [];
  const next = [0, 1, 2].map((k) => (now.getUTCMonth() + k) % 12);
  return hazardOrder.flatMap((type) => {
    const h = data[type];
    if (!h || h.count < 2) return [];
    const where = (h.regions ?? []).slice(0, 4).map((r) => (lang === 'ru' ? r.ru : r.en)).join(', ') || t.regionalNoPlace;
    const total = h.months.reduce((a, b) => a + b, 0);
    const peak = h.months.map((n, m) => [n, m] as const).filter(([n]) => total >= 4 && n / total >= 0.15).map(([, m]) => m);
    const soon = peak.some((m) => next.includes(m)) ? t.soon : '';
    const season = peak.length && peak.length <= 6 ? t.seasonPart(peak.map((m) => monthNames[m]).join(', ')) + soon : '';
    return [t.regional(label(type), where, season)];
  });
}

export function travelVerdict(
  country: CountryEntry, label: (key: string) => string, lang: Lang,
  hazards?: HazardDetails, monthNames: string[] = [], now = new Date(),
): Verdict {
  const t = T[lang];
  const reasons: string[] = [];
  const us = country.advisory?.level;
  const uk = country.advisory_uk;
  if (us) reasons.push(t.usLevel(us, t.travel[us]));
  if (uk) reasons.push(uk.level >= 3 ? t.ukWhole(uk.level) : uk.partial ? t.ukParts : t.ukNone);
  let model: Level = 1;
  if (country.risks.internal_armed_conflict?.active) { reasons.push(t.internalActive); model = 3; }
  if (country.risks.interstate_conflict?.active) reasons.push(t.interstateActive);
  if (country.risks.humanitarian_crisis?.active) { reasons.push(t.humanitarian); model = Math.max(model, 3) as Level; }
  const officialLevels = [us, uk?.level].filter((x): x is Level => !!x);
  const official = officialLevels.length > 0;
  if (!official) reasons.push(t.noOfficial);
  if (!reasons.length) reasons.push(t.calm);
  return {
    level: official ? (Math.max(...officialLevels) as Level) : model,
    official,
    reasons,
    regional: regionalNotes(country, hazards, label, lang, monthNames, now),
  };
}

export function businessVerdict(
  country: CountryEntry, label: (key: string) => string, lang: Lang,
  hazards?: HazardDetails, now = new Date(),
): Verdict {
  const t = T[lang];
  const reasons: string[] = [];
  let level: Level = 1;
  const raise = (to: Level) => { level = Math.max(level, to) as Level; };
  const internal = country.risks.internal_armed_conflict;
  const humanitarian = country.risks.humanitarian_crisis?.active;
  if (internal?.active) { reasons.push(t.internalBusiness); raise(humanitarian ? 4 : 3); }
  else if (internal && internal.horizons['1y'].p >= 0.1) { reasons.push(t.onset(label('internal_armed_conflict'), percent(internal.horizons['1y'].p, lang))); raise(2); }
  if (country.risks.interstate_conflict?.active) { reasons.push(t.interstateBusiness); raise(2); }
  if (humanitarian) { reasons.push(t.humanitarian); raise(3); }
  const econ = country.risks.economic_crisis?.horizons['1y'].p;
  if (econ !== undefined && econ >= 0.12) { reasons.push(t.economic(percent(econ, lang))); raise(econ >= 0.25 ? 3 : 2); }
  const o = country.outlook;
  if (o?.projects_crisis?.length) {
    const parts = o.projects_crisis.flatMap((y) => [
      o.growth?.[y] !== undefined && o.growth[y] < -3 ? t.imfGrowth(y, pct(o.growth[y], lang)) : '',
      o.inflation?.[y] !== undefined && o.inflation[y] > 40 ? t.imfInfl(y, pct(o.inflation[y], lang)) : '',
    ]).filter(Boolean);
    reasons.push(t.imf(parts.join('; ')));
    raise(3);
  }
  const data = hazards?.countries[country.iso3];
  for (const key of ['tropical_cyclone', 'flood', 'major_earthquake']) {
    const p = country.risks[key]?.horizons['1y'].p ?? 0;
    if (p >= 0.5) {
      const where = (data?.[key]?.regions ?? []).slice(0, 3).map((r) => (lang === 'ru' ? r.ru : r.en)).join(', ');
      reasons.push(t.hazardBusiness(label(key), where || percent(p, lang)));
    }
  }
  const soon = (country.elections ?? []).find((e) => {
    const days = (new Date(e.date).getTime() - now.getTime()) / 864e5;
    return days >= -7 && days <= 180;
  });
  if (soon) reasons.push(t.election((lang === 'ru' ? soon.name_ru : null) ?? soon.name_en, soon.date.slice(0, soon.precision === 'day' ? 10 : soon.precision === 'month' ? 7 : 4)));
  const pr = country.profile ?? {};
  const v = (k: string) => pr[k]?.value;
  if ((v('trade_gdp') ?? 0) > 100) reasons.push(t.trade(pct(v('trade_gdp')!, lang)));
  if ((v('fuel_imports_share') ?? 0) > 20) reasons.push(t.fuelImports(pct(v('fuel_imports_share')!, lang)));
  if ((v('food_imports_share') ?? 0) > 20) reasons.push(t.foodImports(pct(v('food_imports_share')!, lang)));
  if ((v('tourism_exports_share') ?? 0) > 20) reasons.push(t.tourism(pct(v('tourism_exports_share')!, lang)));
  if ((v('remittances_gdp') ?? 0) > 10) reasons.push(t.remittances(pct(v('remittances_gdp')!, lang)));
  if (!reasons.length) reasons.push(t.calm);
  return { level, official: false, reasons, regional: [] };
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
  const atWar = neighbours.filter((n) => n.risks.internal_armed_conflict?.active);
  if (atWar.length) lines.push(t.neighboursAtWar(atWar.map(name).join(', ')));
  if (country.risks.internal_armed_conflict?.active && neighbours.length) {
    lines.push(t.exportsInstability(neighbours.map(name).join(', ')));
  }
  if (!lines.length) lines.push(t.noSpillover);
  return lines;
}

// --------------------------------------------------------------------------------------
// Relocation: for people moving for a few months, for 1–5 years, or for longer.

export interface RelocationScenario { title: string; role: string; horizons: Record<string, { p: number }> }
export interface RelocationPart { horizon: 'short' | 'mid' | 'long'; level: Level; reasons: string[] }

const R = {
  ru: {
    levels: ['', 'Подходит для переезда', 'Можно, с планом Б', 'Серьёзные риски', 'Не рекомендуется'],
    horizon: { short: 'На несколько месяцев (до года)', mid: 'На 1–5 лет', long: 'На 5 лет и больше' },
    activeWar: 'Сейчас в стране идёт вооружённый конфликт.',
    activeHumanitarian: 'Действует гуманитарный план ООН: перебои с услугами и безопасностью.',
    risk: (name: string, p: string, h: string) => `${name}: ${p} ${h}.`,
    within: { short: 'в течение года', mid: 'за 5 лет', long: 'за 10 лет' },
    scenario: (title: string, role: string, p: string, h: string) => `Сценарий «${title}» (${role}): ${p} ${h}.`,
    roles: { party: 'страна — сторона', frontline: 'страна на передовой', ally: 'союзник сторон', economic: 'экономическая связь' } as Record<string, string>,
    calm: 'Существенных рисков на этом горизонте по имеющимся данным не видно.',
    note: 'Долгий срок — это не только войны: учитываются перевороты, политические и экономические кризисы и стихийные бедствия. Для визы, налогов и стоимости жизни нужны отдельные источники.',
  },
  en: {
    levels: ['', 'Suitable for a move', 'Possible, with a plan B', 'Serious risks', 'Not advised'],
    horizon: { short: 'For a few months (up to a year)', mid: 'For 1–5 years', long: 'For 5 years or more' },
    activeWar: 'An armed conflict is under way in the country.',
    activeHumanitarian: 'A UN humanitarian plan is active: disrupted services and security.',
    risk: (name: string, p: string, h: string) => `${name}: ${p} ${h}.`,
    within: { short: 'within a year', mid: 'within 5 years', long: 'within 10 years' },
    scenario: (title: string, role: string, p: string, h: string) => `Scenario "${title}" (${role}): ${p} ${h}.`,
    roles: { party: 'the country is a party', frontline: 'front-line country', ally: 'ally of the parties', economic: 'economic link' } as Record<string, string>,
    calm: 'No significant risks at this horizon in the available data.',
    note: 'A long stay is not only about war: coups, political and economic crises and natural hazards are included. Visas, taxes and living costs need separate sources.',
  },
};

const RELOCATION_RISKS: [string, number[]][] = [
  // risk type, thresholds for levels 2 / 3 / 4 at the given horizon
  ['interstate_conflict', [0.05, 0.15, 0.4]],
  ['internal_armed_conflict', [0.05, 0.2, 0.5]],
  ['coup_attempt', [0.05, 0.2, 0.5]],
  ['political_crisis', [0.1, 0.3, 0.6]],
  ['economic_crisis', [0.1, 0.3, 0.6]],
  ['major_earthquake', [0.3, 0.7, 1.1]],
  ['tropical_cyclone', [0.5, 0.9, 1.1]],
];
const HORIZON_KEY = { short: '1y', mid: '5y', long: '10y' } as const;

export const relocationLevelLabel = (level: Level, lang: Lang) => R[lang].levels[level];
export const relocationNote = (lang: Lang) => R[lang].note;
export const relocationHorizon = (h: 'short' | 'mid' | 'long', lang: Lang) => R[lang].horizon[h];

export function relocationVerdict(
  country: CountryEntry, scenarios: RelocationScenario[], label: (key: string) => string, lang: Lang,
): RelocationPart[] {
  const t = R[lang];
  return (['short', 'mid', 'long'] as const).map((horizon) => {
    const hk = HORIZON_KEY[horizon];
    const reasons: string[] = [];
    let level: Level = 1;
    const raise = (to: Level) => { level = Math.max(level, to) as Level; };
    if (country.risks.internal_armed_conflict?.active) { reasons.push(t.activeWar); raise(horizon === 'long' ? 3 : 4); }
    if (country.risks.humanitarian_crisis?.active) { reasons.push(t.activeHumanitarian); raise(3); }
    for (const [key, limits] of RELOCATION_RISKS) {
      const risk = country.risks[key];
      if (!risk || risk.active) continue;
      const p = risk.horizons[hk]?.p;
      if (p === undefined) continue;
      const lvl = (limits.filter((x) => p >= x).length + 1) as Level;
      if (lvl > 1) { raise(lvl); reasons.push(t.risk(label(key), percent(p, lang), t.within[horizon])); }
    }
    for (const s of scenarios) {
      if (!['party', 'frontline'].includes(s.role)) continue;
      const p = s.horizons[hk]?.p;
      if (p === undefined || p < 0.05) continue;
      raise(p >= 0.3 ? 3 : 2);
      reasons.push(t.scenario(s.title, t.roles[s.role] ?? s.role, percent(p, lang), t.within[horizon]));
    }
    if (!reasons.length) reasons.push(t.calm);
    return { horizon, level, reasons: reasons.slice(0, 6) };
  });
}
