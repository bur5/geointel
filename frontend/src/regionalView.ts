// Regions of a country: current level by region (alerts, conflicts), how often each hazard
// struck each region, named volcanoes and the highest recorded tsunami wave.
import { geoArea, geoMercator, geoPath } from 'd3-geo';
import type { Feature, FeatureCollection, MultiPolygon } from 'geojson';
import type { Lang } from './data';
import { dangerBadge } from './danger';

export interface RegionRow {
  code: string; en: string; ru: string; population: number; level: number;
  reasons: { kind: string; hazard?: string; name?: string; alert?: string; date?: string; level: number; reason_ru?: string; reason_en?: string }[];
  volcanoes: { name: string; last_eruption: number; elevation?: number | null }[];
  tsunami_max: { height: number; year: number; place: string } | null;
}
export interface RegionalCountry {
  level_median: number; level_max: number; max_regions: { code: string; en: string; ru: string }[];
  max_population_share: number | null; population_known: boolean; regions: RegionRow[];
  hazards: Record<string, { window: [number, number]; country_years: number; regions: { code: string; years: number; p_year: number; band: number; own_estimate: boolean }[] }>;
}
export interface RegionalFile { generated_at: string; countries: Record<string, RegionalCountry> }

let regionalPromise: Promise<RegionalFile | undefined> | undefined;
export function loadRegional(): Promise<RegionalFile | undefined> {
  regionalPromise ??= fetch(import.meta.env.BASE_URL + 'data/regional.json', { cache: 'no-cache' })
    .then((r) => (r.ok ? r.json() as Promise<RegionalFile> : undefined)).catch(() => undefined);
  return regionalPromise;
}
const shapes = new Map<string, Promise<FeatureCollection<MultiPolygon> | undefined>>();
function loadShapes(iso3: string) {
  if (!shapes.has(iso3)) {
    shapes.set(iso3, fetch(import.meta.env.BASE_URL + `data/regions/${iso3}.json`, { cache: 'no-cache' })
      .then((r) => (r.ok ? r.json() as Promise<FeatureCollection<MultiPolygon>> : undefined)).catch(() => undefined));
  }
  return shapes.get(iso3)!;
}

const T = {
  ru: {
    title: 'По регионам',
    lead: 'Опасность редко одинакова по всей стране. Карта показывает текущий уровень по регионам; ниже — где чаще всего случаются стихийные бедствия.',
    most: (lvl: string) => `Большинство населения живёт в регионах с уровнем ${lvl}.`,
    worst: (lvl: string, names: string, share: string) => `Выше всего — ${names}: ${lvl}${share ? ` (${share} населения)` : ''}.`,
    even: 'Сейчас уровень по регионам одинаковый.',
    noPop: 'Данных о населении регионов нет: регионы считаются равными.',
    often: 'Где чаще всего',
    perYear: (p: string) => `${p} в год`,
    countryEst: 'оценка по стране — в самом регионе мало событий',
    volcanoes: 'Вулканы, извергавшиеся с 1900 года',
    erupted: (y: number) => `последнее извержение — ${y}`,
    tsunami: 'Самая высокая зафиксированная волна цунами',
    wave: (h: string, place: string, y: number) => `${h} м — ${place}, ${y}`,
    alert: (name: string, alert: string) => `${name}: тревога GDACS «${alert === 'Red' ? 'красная' : 'оранжевая'}»`,
    window: (a: number, b: number) => `по событиям ${a}–${b} гг.`,
    hazard: {
      major_earthquake: 'Сильные землетрясения', tsunami: 'Цунами', tropical_cyclone: 'Тропические циклоны',
      flood: 'Крупные наводнения', volcano: 'Извержения вулканов', drought: 'Засухи', wildfire: 'Лесные пожары',
    } as Record<string, string>,
    source: 'Источники: границы регионов — Natural Earth; население — GeoNames (города от 15 000 жителей); события — USGS, GDACS, NOAA NCEI; вулканы — Smithsonian GVP.',
  },
  en: {
    title: 'By region',
    lead: 'Danger is rarely the same across a country. The map shows the current level by region; below, where natural hazards strike most often.',
    most: (lvl: string) => `Most of the population lives in regions at ${lvl}.`,
    worst: (lvl: string, names: string, share: string) => `Highest in ${names}: ${lvl}${share ? ` (${share} of the population)` : ''}.`,
    even: 'The level is currently the same across regions.',
    noPop: 'No regional population data: regions are weighted equally.',
    often: 'Where most often',
    perYear: (p: string) => `${p} a year`,
    countryEst: 'country estimate — few events in the region itself',
    volcanoes: 'Volcanoes that erupted since 1900',
    erupted: (y: number) => `last eruption ${y}`,
    tsunami: 'Highest recorded tsunami wave',
    wave: (h: string, place: string, y: number) => `${h} m — ${place}, ${y}`,
    alert: (name: string, alert: string) => `${name}: GDACS ${alert.toLowerCase()} alert`,
    window: (a: number, b: number) => `from events in ${a}–${b}`,
    hazard: {
      major_earthquake: 'Strong earthquakes', tsunami: 'Tsunamis', tropical_cyclone: 'Tropical cyclones',
      flood: 'Major floods', volcano: 'Volcanic eruptions', drought: 'Droughts', wildfire: 'Wildfires',
    } as Record<string, string>,
    source: 'Sources: region borders — Natural Earth; population — GeoNames (cities of 15,000+); events — USGS, GDACS, NOAA NCEI; volcanoes — Smithsonian GVP.',
  },
};

const LEVEL_FILL = ['', '#cfe8d6', '#f3e3a1', '#f5b971', '#e57f73', '#9b2c2c'];

function rewind(feature: Feature<MultiPolygon>): Feature<MultiPolygon> {
  // Natural Earth rings follow the GeoJSON (counter-clockwise) rule; d3 wants the opposite.
  const polys = feature.geometry.coordinates.map((poly) => poly.map((ring) => {
    const test: Feature<MultiPolygon> = { type: 'Feature', properties: {}, geometry: { type: 'MultiPolygon', coordinates: [[ring]] } };
    return geoArea(test) > 2 * Math.PI ? [...ring].reverse() : ring;
  }));
  return { ...feature, geometry: { type: 'MultiPolygon', coordinates: polys } };
}

export async function fillRegional(
  root: HTMLElement, iso3: string, lang: Lang, pct: (p: number) => string, esc: (s: string) => string,
  stillCurrent: () => boolean,
) {
  const node = root.querySelector<HTMLElement>('#regional');
  if (!node) return;
  const [file, geo] = await Promise.all([loadRegional(), loadShapes(iso3)]);
  if (!stillCurrent()) return;
  const data = file?.countries[iso3];
  const t = T[lang];
  if (!data || data.regions.length < 2) { node.remove(); return; }
  const name = (r: { en: string; ru: string }) => (lang === 'ru' ? r.ru || r.en : r.en);
  const byCode = new Map<string, RegionRow>(data.regions.map((r): [string, RegionRow] => [r.code, r]));
  const summary = [
    t.most(dangerBadge(data.level_median, lang)),
    data.level_max > data.level_median
      ? t.worst(dangerBadge(data.level_max, lang), esc(data.max_regions.map(name).join(', ')), data.max_population_share != null ? pct(data.max_population_share) : '')
      : t.even,
    data.population_known ? '' : t.noPop,
  ].filter(Boolean).map((s) => `<p>${s}</p>`).join('');
  const reasons = data.regions.filter((r) => r.reasons.length).slice(0, 8).map((r) => `<li><b>${esc(name(r))}</b>: ${r.reasons.map((x) => esc(x.kind === 'alert' ? t.alert(x.name ?? '', x.alert ?? '') : (lang === 'ru' ? x.reason_ru : x.reason_en) ?? '')).join('; ')}</li>`).join('');
  const hazards = (Object.entries(data.hazards) as [string, RegionalCountry['hazards'][string]][]).map(([key, h]) => {
    const rows = h.regions.slice(0, 4).filter((r) => r.years > 0).map((r) => {
      const reg = byCode.get(r.code);
      return `<li>${esc(reg ? name(reg) : r.code)} — ${t.perYear(pct(r.p_year))}${r.own_estimate ? '' : ` <span class="muted-text small">(${t.countryEst})</span>`}</li>`;
    }).join('');
    return rows ? `<div><h4>${esc(t.hazard[key] ?? key)}</h4><p class="muted-text small">${t.window(h.window[0], h.window[1])}</p><ul>${rows}</ul></div>` : '';
  }).join('');
  const volcanoes = data.regions.flatMap((r) => r.volcanoes.map((v) => ({ ...v, region: name(r) })))
    .sort((a, b) => b.last_eruption - a.last_eruption).slice(0, 8)
    .map((v) => `<li><b>${esc(v.name)}</b> — ${esc(v.region)}, ${t.erupted(v.last_eruption)}</li>`).join('');
  const waves = data.regions.filter((r) => r.tsunami_max).sort((a, b) => b.tsunami_max!.height - a.tsunami_max!.height).slice(0, 3)
    .map((r) => `<li>${esc(name(r))}: ${esc(t.wave(String(r.tsunami_max!.height).replace('.', lang === 'ru' ? ',' : '.'), r.tsunami_max!.place, r.tsunami_max!.year))}</li>`).join('');
  node.innerHTML = `<div class="section-head"><h2>${t.title}</h2><p>${t.lead}</p></div>
    <div class="regional-grid"><div class="regional-map">${geo ? '<svg viewBox="0 0 600 380" role="img"></svg>' : ''}</div>
    <div class="regional-summary">${summary}${reasons ? `<ul>${reasons}</ul>` : ''}</div></div>
    ${hazards ? `<h3 class="sub">${t.often}</h3><div class="regional-hazards">${hazards}</div>` : ''}
    ${volcanoes ? `<h3 class="sub">${t.volcanoes}</h3><ul>${volcanoes}</ul>` : ''}
    ${waves ? `<h3 class="sub">${t.tsunami}</h3><ul>${waves}</ul>` : ''}
    <p class="muted-text small">${t.source}</p>`;
  const svg = node.querySelector('svg');
  if (svg && geo) {
    const features = geo.features.map(rewind);
    const collection = { type: 'FeatureCollection', features } as FeatureCollection<MultiPolygon>;
    const projection = geoMercator().fitExtent([[8, 8], [592, 372]], collection);
    const path = geoPath(projection);
    svg.innerHTML = features.map((f) => {
      const row = byCode.get(String(f.properties?.code ?? ''));
      const level = row?.level ?? 1;
      const label = `${row ? name(row) : ''}: ${level}`;
      return `<path d="${path(f) ?? ''}" fill="${LEVEL_FILL[level]}" stroke="#fff" stroke-width="0.6"><title>${esc(label)}</title></path>`;
    }).join('');
  }
}
