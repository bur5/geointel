import './style.css';
import { band, changesSince, loadAccuracy, loadBacktest, loadRealBacktest, loadHazards, loadLinks, loadScenarios, loadSignals, loadSnapshot, percent, readVisit, writeVisit } from './data';
import type {
  AccuracyFile, BacktestFile, RealBacktestFile, Change, CountryEntry, EventTypeEntry, HazardDetails, HazardSummary, HorizonKey, Lang, LinksFile, Probability, Risk,
  ScenarioFile, SignalsFile,
  Snapshot, VisitMemory,
} from './data';
import { countryScenarios, linksSection, migrationClass, migrationPage, migrationSection, roleClass, scenariosPage, vt } from './views';
import type { ViewContext } from './views';
import { countrySignals, factorClass, signalsPage, st } from './signalsView';
import { accuracyPage } from './accuracyView';
import { lensesPage, surveyAnswer } from './lensesView';
import type { ChainEvent } from './chains';
import { dictionaries } from './i18n';
import { drawCountryMap, drawMap, neighboursOf } from './map';
import { businessVerdict, levelLabel, relocationHorizon, relocationLevelLabel, relocationNote, relocationVerdict, spillover, travelVerdict } from './insights';
import { alertCard } from './alerts';
import { fillRegional } from './regionalView';
import { humanitarianCard } from './humanitarian';
import { ask, assistantPanel, clearChat } from './assistant';
import { trainedSection, type TrainedFile } from './trainedView';
import { explain } from './explain';
import { applyTheme, currentTheme, nextTheme, picker, pins, searchBox, themeButton, togglePicker, togglePin, wireSearch } from './ui';
import { dangerBadge, dangerCard, dangerName, trendChip } from './danger';
import { BLOCS, REGIONS, groupName, groupNote, groupsOf } from './groups';
import type { Group } from './groups';
import type { Level, Verdict } from './insights';

const pages = [
  ['overview', 'navOverview'],
  ['scenarios', 'navScenarios'],
  ['signals', 'navSignals'],
  ['accuracy', 'navAccuracy'],
  ['lenses', 'navLenses'],
  ['country', 'navCountry'],
  ['migration', 'navMigration'],
  ['changes', 'navChanges'],
  ['assistant', 'navAssistant'],
  ['method', 'navMethod'],
] as const;
type Page = typeof pages[number][0];

const root = document.querySelector<HTMLElement>('#app')!;
const stored = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const store = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* ignore */ } };

let lang: Lang = (new URLSearchParams(location.search).get('lang') ?? stored('geointel.lang')) === 'en' ? 'en' : 'ru';
let eventType = stored('geointel.type') ?? 'view_danger';
let theme = currentTheme();
applyTheme(theme);
let horizon: HorizonKey = (stored('geointel.horizon') as HorizonKey | null) ?? '1y';
let selected = stored('geointel.country') ?? 'UKR';
let lens: 'countries' | 'regions' | 'blocs' = (stored('geointel.lens') as 'regions' | 'blocs' | null) ?? 'countries';
let selectedGroup = stored('geointel.group') ?? 'eu';
let snapshot: Snapshot | undefined;
let previousVisit: VisitMemory | undefined;
let loadError = false;
let updateMapSelection: ((key: string) => void) | undefined;
let hazardsData: HazardDetails | undefined;
let scenariosData: ScenarioFile | undefined;
let linksData: LinksFile | undefined;
let signalsData: SignalsFile | undefined;
let backtestData: BacktestFile | undefined;
let realBacktestData: RealBacktestFile | undefined;
let accuracyData: AccuracyFile | undefined;
let trainedData: TrainedFile | undefined;
let btCase = stored('geointel.btcase') ?? 'ukraine_2022';
let currentScenario = stored('geointel.scenario') ?? 'russia_nato';
let chainEvent: ChainEvent = (stored('geointel.chain') as ChainEvent | null) ?? 'conflict';
let migMode: 'hosted' | 'abroad' = stored('geointel.migmode') === 'abroad' ? 'abroad' : 'hosted';
const VIEWS = ['view_danger', 'view_travel', 'view_business', 'view_political'] as const;
const isView = (key: string) => (VIEWS as readonly string[]).includes(key);
const levelClass = (level: Level) => (['', 'low', 'elevated', 'high', 'critical'] as const)[level];

const t = () => dictionaries[lang];
const escape = (value: string) => value.replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]!));
const currentPage = (): Page => pages.find(([key]) => '#' + key === location.hash)?.[0] ?? 'overview';
const formatDate = (value: string, withTime = true) => new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', {
  day: 'numeric', month: 'long', year: 'numeric',
  ...(withTime ? { hour: '2-digit', minute: '2-digit', timeZoneName: 'short' } : {}),
}).format(new Date(value));
const pct = (p: number) => percent(p, lang);

let regionNames: Intl.DisplayNames | undefined;
function countryName(country: CountryEntry | undefined, fallback = ''): string {
  if (!country) return fallback;
  try {
    regionNames ??= new Intl.DisplayNames([lang], { type: 'region' });
    return regionNames.of(country.iso2) ?? country.name;
  } catch {
    return country.name;
  }
}

const byIso = () => new Map((snapshot?.countries ?? []).map((c) => [c.iso3, c]));
function shapeToIso(): Map<string, string> {
  const map = new Map<string, string>();
  for (const c of snapshot?.countries ?? []) if (c.numeric) map.set(c.numeric, c.iso3);
  map.set('name:Kosovo', 'XKX');
  return map;
}
const typeEntry = (key: string) => snapshot?.event_types.find((e) => e.key === key);
const typeLabel = (entry: EventTypeEntry | undefined) => entry ? (lang === 'ru' ? entry.label_ru : entry.label_en) : '';
const horizonLabel = (key: string) => {
  const h = snapshot?.horizons.find((item) => item.key === key);
  return h ? (lang === 'ru' ? h.label_ru : h.label_en) : key;
};
const isConflict = (key: string) => key.endsWith('conflict');
const nameOf = (iso3: string) => countryName(byIso().get(iso3), iso3);
const viewContext = (): ViewContext => ({ lang, esc: escape, name: nameOf, pct });
const horizonLabels = () => Object.fromEntries((snapshot?.horizons ?? []).map((h) => [h.key, lang === 'ru' ? h.label_ru : h.label_en])) as Record<HorizonKey, string>;
const neighbourCodes = (iso3: string) => {
  const country = byIso().get(iso3);
  return country ? neighbourCountries(country).map((c) => c.iso3) : [];
};
const labelOf = (key: string) => typeLabel(typeEntry(key));
// Advice must never contradict the danger level: verdicts are floored by it (capped at 4).
const dangerOf = (c: CountryEntry) => signalsData?.countries[c.iso3]?.danger;
const floorLevel = (level: number, c: CountryEntry) => Math.max(level, Math.min(4, dangerOf(c)?.level ?? 1)) as 1 | 2 | 3 | 4;
const travelOf = (c: CountryEntry) => { const v = travelVerdict(c, labelOf, lang, hazardsData, t().months); return { ...v, level: floorLevel(v.level, c) }; };
const businessOf = (c: CountryEntry) => { const v = businessVerdict(c, labelOf, lang, hazardsData); return { ...v, level: floorLevel(v.level, c) }; };
const viewVerdict = (c: CountryEntry): Verdict => (eventType === 'view_travel' ? travelOf(c) : businessOf(c));
const viewKind = () => (eventType === 'view_travel' ? 'travel' : 'business') as 'travel' | 'business';
const dangerLevelOf = (c: CountryEntry) => dangerOf(c)?.level ?? 0;
const relocBadge = (level: Level) =>
  `<span class="level level-${levelClass(level)}" title="${escape(relocationHorizon('mid', lang))}"><b>${level}</b>${escape(relocationLevelLabel(level, lang))}</span>`;
const levelBadge = (kind: 'travel' | 'business', level: Level) =>
  `<span class="level level-${levelClass(level)}"><b>${level}</b>${escape(levelLabel(kind, level, lang))}</span>`;
function neighbourCountries(country: CountryEntry): CountryEntry[] {
  const shapes = shapeToIso();
  const key = country.numeric ?? (country.iso3 === 'XKX' ? 'name:Kosovo' : '');
  const map = byIso();
  return neighboursOf(key).map((k) => map.get(shapes.get(k) ?? '')).filter((c): c is CountryEntry => !!c);
}
const questionText = (key: string, risk: Risk) =>
  risk.question === 'active_at_end' ? t().qActive : isConflict(key) ? t().qOnsetConflict : t().qEvent;
const confidenceText = (value: Risk['confidence']) => ({
  low: t().confidenceLow, medium: t().confidenceMedium, high: t().confidenceHigh,
}[value]);
const ongoingTag = () => `<span class="pill-active">${t().ongoing}</span>`;
const notice = (headline: string, description = '', role = 'status') =>
  `<div class="notice" role="${role}"><strong>${headline}</strong>${description ? `<p>${description}</p>` : ''}</div>`;

/** Mean onset probability across countries (world reference for comparisons). */
function worldAverage(type: string, h: HorizonKey): number | undefined {
  const values = (snapshot?.countries ?? [])
    .map((c) => c.risks[type])
    .filter((r): r is Risk => !!r && r.question === 'onset_within')
    .map((r) => r.horizons[h].p);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : undefined;
}

function comparison(type: string, h: HorizonKey, p: number): string {
  const avg = worldAverage(type, h);
  if (!avg) return '';
  const ratio = p / avg;
  const fmt = (x: number) => (x >= 10 ? x.toFixed(0) : x.toFixed(1).replace(/\.0$/, '')).replace('.', lang === 'ru' ? ',' : '.');
  if (ratio >= 1.5) return t().timesHigher(fmt(ratio));
  if (ratio <= 0.67) return t().timesLower(fmt(1 / ratio));
  return t().aboutAverage;
}

function rangeBar(v: Probability, cls: string) {
  const left = v.low * 100, width = Math.max((v.high - v.low) * 100, 0.6), dot = v.p * 100;
  return `<span class="bar" aria-hidden="true"><span class="bar-range ${cls}" style="left:${left}%;width:${width}%"></span><span class="bar-dot" style="left:${dot}%"></span></span>`;
}

function value(risk: Risk, h: HorizonKey, size: 'lg' | 'sm' = 'sm') {
  const v = risk.horizons[h];
  const cls = risk.question === 'active_at_end' ? 'active' : band(v.p);
  return `<div class="value value-${size}"><span class="num">${pct(v.p)}</span>${rangeBar(v, cls)}<span class="range">${pct(v.low)} – ${pct(v.high)}</span></div>`;
}

function summarySentences(country: CountryEntry | undefined, h: HorizonKey): string {
  if (!country || !snapshot) return '';
  const lines: string[] = [];
  const items = snapshot.event_types
    .filter((e) => e.available && country.risks[e.key])
    .map((e) => ({ e, r: country.risks[e.key] }));
  for (const { e, r } of items.filter((x) => x.r.question === 'active_at_end')) {
    lines.push(t().summaryActive(typeLabel(e), pct(r.horizons[h].p), t().horizonAccusative[h]));
  }
  const elevated = items
    .filter(({ e, r }) => r.question === 'onset_within' && r.horizons[h].p >= (worldAverage(e.key, h) ?? 1) * 1.5)
    .sort((a, b) => b.r.horizons[h].p - a.r.horizons[h].p);
  for (const { e, r } of elevated) {
    lines.push(t().summaryOnset(typeLabel(e), pct(r.horizons[h].p), t().horizonGenitive[h], comparison(e.key, h, r.horizons[h].p)));
  }
  if (!lines.length) lines.push(t().summaryCalm);
  return lines.map((line) => `<p>${escape(line)}</p>`).join('') + `<p class="caveat">${t().summaryCaveat}</p>`;
}

const dangerNote = () => (lang === 'ru'
  ? 'Уровень опасности 1–5: насколько опасно в стране сейчас (войны, конфликты, перевороты, кризисы; бедствия — по регионам) с учётом рекомендаций МИД.'
  : 'Danger level 1–5: how dangerous the country is now (wars, conflicts, coups, crises; hazards by region), with foreign-ministry advice.');

function pickGroups() {
  const groups = [['conflict', t().groupConflict], ['natural', t().groupNatural], ['society', t().groupSociety]] as const;
  const views = { label: escape(t().groupViews), items: [
    { key: 'view_danger', label: lang === 'ru' ? 'Уровень опасности' : 'Danger level' },
    { key: 'view_travel', label: escape(t().viewTravel) },
    { key: 'view_business', label: escape(t().viewBusiness) },
  ] };
  return [views, ...groups.map(([group, label]) => ({
    label: escape(label),
    items: (snapshot?.event_types ?? []).filter((e) => (e.group ?? 'conflict') === group).map((e) => ({
      key: e.key === 'political_crisis' && !e.modeled ? 'view_political' : e.key, label: escape(typeLabel(e)),
      disabled: !e.available && !(e.key === 'political_crisis' && !e.modeled),
      note: e.key === 'political_crisis' && !e.modeled ? (lang === 'ru' ? 'сейчас' : 'now') : !e.modeled ? escape(t().notModeled) : !e.available ? escape(t().unavailable) : undefined,
    })),
  }))].filter((g) => g.items.length);
}

function horizonSwitch() {
  return `<div class="segmented" role="group" aria-label="${t().horizon}">${(snapshot?.horizons ?? []).map((h) =>
    `<button type="button" data-horizon="${h.key}" aria-pressed="${h.key === horizon}">${escape(lang === 'ru' ? h.label_ru : h.label_en)}</button>`).join('')}</div>`;
}

function countryOptions() {
  return (snapshot?.countries ?? [])
    .map((c) => [c.iso3, countryName(c)] as const)
    .sort((a, b) => a[1].localeCompare(b[1], lang))
    .map(([iso3, label]) => `<option value="${iso3}"${iso3 === selected ? ' selected' : ''}>${escape(label)}</option>`).join('');
}

function stats() {
  if (!snapshot) return '';
  const active = snapshot.countries.filter((c) =>
    Object.entries(c.risks).some(([key, r]) => isConflict(key) && r.active)).length;
  const visitChanges = previousVisit ? changesSince(previousVisit, snapshot).length : null;
  return `<dl class="stats">
    <div><dt>${t().statCountries}</dt><dd>${snapshot.countries.length}</dd></div>
    <div><dt>${t().statActive}</dt><dd>${active}</dd></div>
    <div><dt>${visitChanges === null ? t().statChangesFirst : t().statChanges}</dt><dd>${visitChanges ?? '—'}</dd></div>
  </dl>`;
}

function legend() {
  if (eventType === 'view_political') {
    return `<div class="legend"><span class="legend-key"><i class="swatch-active"></i>${lang === 'ru' ? 'Событие кризиса, сообщают 2+ издания' : 'Crisis event, 2+ outlets'}</span><span class="legend-key"><i class="sw-minimal"></i>${lang === 'ru' ? 'Не обнаружено или не подтверждено (это не гарантия)' : 'None detected or unconfirmed (not a guarantee)'}</span></div>`;
  }
  if (eventType === 'view_danger') {
    return `<div class="legend">${[1, 2, 3, 4, 5].map((l) => `<span class="legend-key"><i class="sw-d${l}"></i>${l} — ${escape(dangerName(l, lang))}</span>`).join('')}<span class="legend-key"><i class="swatch-none"></i>${t().legendNoData}</span></div>`;
  }
  if (isView(eventType)) {
    const kind = viewKind();
    return `<div class="legend">${([1, 2, 3, 4] as Level[]).map((l) => `<span class="legend-key"><i class="sw-${levelClass(l)}"></i>${l} — ${escape(levelLabel(kind, l, lang))}</span>`).join('')}</div>`;
  }
  const steps = [['minimal', '0'], ['low', '1%'], ['elevated', '5%'], ['high', '20%'], ['critical', '50%']];
  return `<div class="legend">
    <div class="legend-scale"><span class="legend-title">${t().legendProbability}</span>
      <div class="ramp">${steps.map(([cls, label]) => `<span class="${cls}"><i></i><small>${label}</small></span>`).join('')}<span class="ramp-end"><small>100%</small></span></div></div>
    ${(snapshot?.countries ?? []).some((c) => c.risks[eventType]?.active) ? `<span class="legend-key"><i class="swatch-active"></i>${t().legendActive}</span>` : ''}
    <span class="legend-key"><i class="swatch-none"></i>${t().legendNoData}</span>
  </div>`;
}

function mapBlock() {
  return `<section class="map-card" aria-label="${escape(isView(eventType) ? t().groupViews : typeLabel(typeEntry(eventType)))}">
    <div class="toolbar">
      ${picker(t().eventType, eventType, pickGroups())}
      ${isView(eventType) ? `<p class="toolbar-note">${eventType === 'view_political' ? politicalNote() : eventType === 'view_danger' ? dangerNote() : eventType === 'view_travel' ? t().viewTravelNote : t().viewBusinessNote}</p>` : `<div class="toolbar-group"><span>${t().horizon}</span>${horizonSwitch()}</div>`}
    </div>
    <div class="map-stage" id="map"><svg viewBox="0 0 900 440" role="img" tabindex="0" aria-label="${escape(typeLabel(typeEntry(eventType)))}">
      <defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="#8f1d2c"/><line x1="0" y1="0" x2="0" y2="6" stroke="#f0c7cc" stroke-width="2.2"/></pattern></defs><g></g></svg>
      <div class="tooltip" hidden></div>
      <div class="map-controls"><button data-map="in" aria-label="${t().zoomIn}">+</button><button data-map="out" aria-label="${t().zoomOut}">−</button><button data-map="reset" aria-label="${t().zoomReset}">⟲</button></div>
    </div>
    ${legend()}
  </section>`;
}

const groupsForLens = () => (lens === 'blocs' ? BLOCS : REGIONS);
const currentGroup = (): Group | undefined => groupsForLens().find((g) => g.key === selectedGroup) ?? groupsForLens()[0];

function lensSwitch() {
  const items = [['countries', t().lensCountries], ['regions', t().lensRegions], ['blocs', t().lensBlocs]] as const;
  return `<div class="lens"><span>${t().lensTitle}</span><div class="segmented" role="group">${items.map(([key, label]) =>
    `<button type="button" data-lens="${key}" aria-pressed="${key === lens}">${label}</button>`).join('')}</div></div>`;
}

/** Group aggregate: probability that at least one member sees the event (independence assumed). */
function groupStats(g: Group) {
  const members = (snapshot?.countries ?? []).filter((c) => g.members.includes(c.iso3));
  const withRisk = members.filter((c) => c.risks[eventType]);
  const active = withRisk.filter((c) => c.risks[eventType].active);
  const any = 1 - withRisk.reduce((acc, c) => acc * (1 - c.risks[eventType].horizons[horizon].p), 1);
  const top = [...withRisk].sort((a, b) => b.risks[eventType].horizons[horizon].p - a.risks[eventType].horizons[horizon].p);
  return { members, withRisk, active, any, top };
}

function groupPanel() {
  const g = currentGroup();
  if (!g || isView(eventType)) return briefPanel();
  const st = groupStats(g);
  const note = groupNote(g, lang);
  return `<aside class="brief" id="country-panel">
    <label class="select compact"><span>${lens === 'blocs' ? (lang === 'ru' ? 'Блок' : 'Bloc') : (lang === 'ru' ? 'Регион' : 'Region')}</span><select data-field="group">${groupsForLens().map((x) =>
      `<option value="${x.key}"${x.key === g.key ? ' selected' : ''}>${escape(groupName(x, lang))}</option>`).join('')}</select></label>
    <h2>${escape(groupName(g, lang))}</h2>
    <p class="muted-text">${t().groupMembers(st.members.length)}${note ? ' ' + escape(note) : ''}</p>
    <div class="group-any"><span>${t().groupAny(escape(typeLabel(typeEntry(eventType)).toLowerCase()), escape(horizonLabel(horizon).toLowerCase()))}</span><strong>${pct(st.any)}</strong></div>
    ${st.active.length ? `<p class="muted-text">${t().groupActive}: ${st.active.map((c) => escape(countryName(c))).join(', ')}</p>` : ''}
    <ul class="brief-list">${st.top.slice(0, 8).map((c) => `<li><button type="button" class="link" data-select="${c.iso3}">${escape(countryName(c))}</button>${c.risks[eventType].active ? ongoingTag() : ''}${value(c.risks[eventType], horizon)}</li>`).join('')}</ul>
    <p class="caveat">${t().groupCaveat}</p>
  </aside>`;
}

function groupGrid() {
  return `<section class="section"><div class="section-head"><h2>${lens === 'blocs' ? t().blocsTitle : t().regionsTitle}</h2>
    <p>${escape(typeLabel(typeEntry(eventType)))}, ${escape(horizonLabel(horizon).toLowerCase())}. ${t().groupCaveat}</p></div>
    <div class="group-grid">${groupsForLens().map((g) => {
      const st = groupStats(g);
      return `<button type="button" class="group-card${g.key === selectedGroup ? ' is-selected' : ''}" data-group="${g.key}">
        <span class="g-name">${escape(groupName(g, lang))}</span><span class="g-any ${band(st.any)}">${pct(st.any)}</span>
        <span class="g-meta">${t().groupMembers(st.members.length)}${st.active.length ? ' · ' + t().groupActive.toLowerCase() + ': ' + st.active.length : ''}</span>
        <span class="g-top">${st.top.slice(0, 3).map((c) => escape(countryName(c))).join(', ')}</span></button>`;
    }).join('')}</div></section>`;
}

function briefPanel() {
  const country = byIso().get(selected);
  const rows = (snapshot?.event_types ?? []).filter((e) => e.available && country?.risks[e.key]).map((e) => {
    const r = country!.risks[e.key];
    return `<li><div class="brief-row-head"><span>${escape(typeLabel(e))}</span>${r.active ? ongoingTag() : ''}</div>${value(r, horizon)}</li>`;
  }).join('');
  return `<aside class="brief" id="country-panel" aria-labelledby="brief-heading">
    <label class="select compact"><span>${t().selectCountry}</span><select data-field="country">${countryOptions()}</select></label>
    <h2 id="brief-heading">${escape(countryName(country, selected))}</h2>
    ${country ? `<div class="brief-verdicts"><div><span>${t().forTravel}</span>${levelBadge('travel', travelOf(country).level)}</div>
      <div><span>${t().forBusiness}</span>${levelBadge('business', businessOf(country).level)}</div>
      <div><span>${t().forRelocation}</span>${relocBadge(relocationParts(country)[1].level)}</div></div>` : ''}
    <div class="brief-summary">${summarySentences(country, horizon)}</div>
    <ul class="brief-list">${rows}</ul>
    <a class="button" href="#country">${t().openCountry}</a>
  </aside>`;
}

const politicalNote = () => (lang === 'ru'
  ? 'Политический кризис — сейчас: страны, где за 60 дней сообщалось о досрочном уходе главы государства или правительства, досрочных выборах, импичменте, чрезвычайном или военном положении по политическим причинам или попытке переворота. Это обнаружение уже случившегося, не прогноз.'
  : 'Political crisis — now: countries where in the last 60 days the media reported an early exit of the head of state or government, an early election, impeachment, political emergency rule or martial law, or a coup attempt. Detection of what already happened, not a forecast.');

function politicalList() {
  const data = signalsData?.political_crisis ?? {};
  const rows = Object.entries(data).sort((a, b) => Number(b[1].confirmed) - Number(a[1].confirmed) || (b[1].events[0]?.date ?? '').localeCompare(a[1].events[0]?.date ?? ''));
  const entry = typeEntry('political_crisis');
  const head = `<div class="section-head"><h2>${lang === 'ru' ? 'Политический кризис: события за 60 дней' : 'Political crisis: events in the last 60 days'}</h2>
    <p>${lang === 'ru' ? 'Вероятности политического кризиса пока не считаем: для всех стран нет истории таких событий за 2000–2025 годы нужного качества. Ниже — то, что уже произошло, по сообщениям СМИ (заголовки разобраны ИИ, страна и цитата проверены правилом).' : 'We do not compute political crisis probabilities yet: there is no history of such events for all countries for 2000–2025 of sufficient quality. Below is what already happened, as reported by the media (headlines classified by AI, country and quote checked by rule).'}</p></div>`;
  const def = entry ? `<details><summary>${t().definition}</summary><p>${escape(lang === 'ru' ? entry.resolution_ru : entry.resolution_en)}</p></details>` : '';
  if (!rows.length) return `<section class="section">${head}${def}<p class="muted-text">${lang === 'ru' ? 'За 60 дней событий не обнаружено. Новостной поток мог пропустить события: это не гарантия.' : 'No events detected in 60 days. The news feed can miss events: this is not a guarantee.'}</p></section>`;
  return `<section class="section">${head}${def}<ul class="political-list">${rows.map(([iso3, p]) => `<li><button type="button" class="link" data-select="${iso3}">${escape(countryName(byIso().get(iso3) ?? { iso3, name: iso3 } as CountryEntry))}</button>
    <span class="muted-text small">${p.confirmed ? (lang === 'ru' ? `${p.outlets} изданий` : `${p.outlets} outlets`) : (lang === 'ru' ? 'одно издание, не подтверждено' : 'one outlet, unconfirmed')}</span>
    <ul class="plain small">${p.events.map((e) => `<li>${escape(e.date)} — <a href="${escape(e.url)}" target="_blank" rel="noopener">${escape(lang === 'ru' ? e.summary_ru : e.summary_en)}</a></li>`).join('')}</ul></li>`).join('')}</ul></section>`;
}

function ranking() {
  if (eventType === 'view_political') return politicalList();
  if (eventType === 'view_danger') {
    return `<div class="legend">${[1, 2, 3, 4, 5].map((l) => `<span class="legend-key"><i class="sw-d${l}"></i>${l} — ${escape(dangerName(l, lang))}</span>`).join('')}<span class="legend-key"><i class="swatch-none"></i>${t().legendNoData}</span></div>`;
  }
  if (isView(eventType)) {
    const kind = viewKind();
    const rows = (snapshot?.countries ?? []).map((c) => ({ c, v: viewVerdict(c) }))
      .sort((a, b) => b.v.level - a.v.level || countryName(a.c).localeCompare(countryName(b.c), lang))
      .filter((x) => x.v.level >= 3).slice(0, 40);
    return `<section class="section"><div class="section-head"><h2>${kind === 'travel' ? t().rankTravel : t().rankBusiness}</h2></div>
      <ol class="ranking">${rows.map(({ c, v }) => `<li><button type="button" data-select="${c.iso3}">
        <span class="rank-name">${escape(countryName(c))}</span>${levelBadge(kind, v.level)}</button></li>`).join('')}</ol></section>`;
  }
  const rows = (snapshot?.countries ?? [])
    .filter((c) => c.risks[eventType])
    .map((c) => ({ c, r: c.risks[eventType] }))
    .sort((a, b) => b.r.horizons[horizon].p - a.r.horizons[horizon].p)
    .slice(0, 20);
  return `<section class="section"><div class="section-head"><h2>${t().rankingTitle}</h2>
      <p>${escape(typeLabel(typeEntry(eventType)))}, ${escape(horizonLabel(horizon).toLowerCase())}. ${t().rankingHint}</p></div>
    <ol class="ranking">${rows.map(({ c, r }) => `<li><button type="button" data-select="${c.iso3}">
      <span class="rank-name">${escape(countryName(c))}${r.active ? ongoingTag() : ''}</span>${value(r, horizon)}</button></li>`).join('')}</ol></section>`;
}

function pinnedStrip() {
  const list = pins().map((iso) => byIso().get(iso)).filter((c): c is CountryEntry => !!c);
  const title = lang === 'ru' ? 'Мои страны' : 'My countries';
  if (!list.length) {
    return `<section class="pinned empty"><h2>${title}</h2><p class="muted-text">${lang === 'ru' ? 'Добавьте страны кнопкой «☆ В мои страны» на странице страны — здесь будет их уровень опасности и что изменилось.' : 'Add countries with the "☆ My countries" button on a country page to see their danger level and changes here.'}</p></section>`;
  }
  return `<section class="pinned"><h2>${title}</h2><div class="pinned-row">${list.map((c) => {
    const d = dangerOf(c);
    return `<button type="button" class="pin-card" data-select="${c.iso3}"><span class="pin-name">${escape(countryName(c))}</span>
      ${d ? dangerBadge(d.level, lang) + trendChip(d, lang) : '<span class="muted-text small">…</span>'}</button>`;
  }).join('')}</div></section>`;
}

function overview() {
  const grouped = lens !== 'countries' && !isView(eventType);
  return `<section class="hero"><h1>${t().heroTitle}</h1><p>${t().heroLead}</p>${stats()}</section>
    ${pinnedStrip()}
    ${lensSwitch()}
    <div class="explorer">${mapBlock()}${grouped ? groupPanel() : briefPanel()}</div>
    ${grouped ? groupGrid() : ranking()}`;
}

function pinButton(iso3: string) {
  const on = pins().includes(iso3);
  const label = lang === 'ru' ? (on ? '★ В моих странах' : '☆ В мои страны') : (on ? '★ In my countries' : '☆ My countries');
  return `<button type="button" class="pin-button" data-pin="${iso3}" aria-pressed="${on}">${label}</button>`;
}

function countryHero(country: CountryEntry) {
  const d = dangerOf(country);
  const reloc = relocationParts(country)[1];
  const tile = (title: string, badge: string) => `<div class="hero-tile"><span>${title}</span>${badge}</div>`;
  return `<div class="country-hero">
    <div class="hero-level">${d ? `<span class="hero-caption">${lang === 'ru' ? 'Уровень опасности' : 'Danger level'}</span>${dangerBadge(d.level, lang)}${trendChip(d, lang)}` : ''}</div>
    ${tile(t().forTravel, levelBadge('travel', travelOf(country).level))}
    ${tile(t().forBusiness, levelBadge('business', businessOf(country).level))}
    ${tile(t().forRelocation, relocBadge(reloc.level))}
  </div>`;
}

function sectionNav() {
  const items = lang === 'ru'
    ? [['alert-card', 'Что это значит'], ['assistant', 'Спросить ИИ'], ['regional', 'Регионы'], ['country-signals', 'Признаки'], ['country-scenarios', 'Сценарии'], ['country-links', 'Связи'], ['hazards', 'Бедствия'], ['country-migration', 'Миграция'], ['all-risks', 'Все риски']]
    : [['alert-card', 'What it means'], ['assistant', 'Ask AI'], ['regional', 'Regions'], ['country-signals', 'Signs'], ['country-scenarios', 'Scenarios'], ['country-links', 'Links'], ['hazards', 'Hazards'], ['country-migration', 'Migration'], ['all-risks', 'All risks']];
  return `<nav class="section-nav" aria-label="${lang === 'ru' ? 'Разделы страницы' : 'Page sections'}">${items.map(([id, label]) => `<a href="#${id}" data-jump="${id}">${label}</a>`).join('')}</nav>`;
}

const medianCache = new Map<string, number | null>();
function typeMedian(key: string, h: HorizonKey): number | null {
  const id = `${snapshot?.generated_at}|${key}|${h}`;
  if (!medianCache.has(id)) {
    const values = (snapshot?.countries ?? []).map((c) => c.risks[key]?.horizons[h]?.p).filter((v): v is number => typeof v === 'number').sort((a, b) => a - b);
    medianCache.set(id, values.length ? values[Math.floor(values.length / 2)] : null);
  }
  return medianCache.get(id)!;
}

function explainBlock(entry: EventTypeEntry, risk: CountryEntry['risks'][string]) {
  const h = (snapshot?.horizons ?? []).find((x) => x.key === '1y');
  const cell = risk.horizons['1y'];
  if (!h || !cell) return '';
  const lines = explain({
    key: entry.key, sphere: (entry.group ?? 'conflict') as 'conflict' | 'natural' | 'society', p: cell.p,
    horizonLabel: lang === 'ru' ? h.label_ru : h.label_en, median: typeMedian(entry.key, '1y'),
    p10: risk.horizons['10y']?.p ?? null, active: !!risk.active, lang,
  });
  return `<details class="explain"><summary>${lang === 'ru' ? 'Как понимать эти цифры' : 'How to read these numbers'}</summary><ul>${lines.map((l) => `<li>${escape(l)}</li>`).join('')}</ul></details>`;
}

function viewsNote(country: CountryEntry, risk: CountryEntry['risks'][string]) {
  const v = country.external?.views;
  if (!v) return '';
  const pct = (p: number) => (p * 100 < 1 ? (p * 100).toFixed(1) : Math.round(p * 100).toString()) + '%';
  const own = risk.own_horizons?.['1y'];
  if (lang === 'ru') {
    const head = `ViEWS (Уппсала, PRIO): вероятность месяца с 25+ погибшими в боях — ${pct(v.p1m)} в этом месяце, ${pct(v.p12m)} за 12 месяцев (диапазон ${pct(v.p12m_low)}–${pct(v.p12m_high)}).`;
    const tail = risk.model === 'views_blend'
      ? ` Цифры выше — смесь: 70% ViEWS и 30% нашей модели${own ? ` (наша модель отдельно: ${pct(own.p)} за год)` : ''}.`
      : v.skipped === 'interstate_war'
        ? ' ViEWS считает все бои на территории страны, включая войну с другим государством, поэтому для внутреннего конфликта здесь не используется; цифры выше — по нашей модели.'
        : ' Конфликт уже идёт, поэтому цифры выше — по нашей модели продолжения; ViEWS показан для сравнения.';
    return `<p class="basis views-note">${escape(head + tail)}</p>`;
  }
  const head = `ViEWS (Uppsala, PRIO): probability of a month with 25+ battle deaths — ${pct(v.p1m)} this month, ${pct(v.p12m)} over 12 months (range ${pct(v.p12m_low)}–${pct(v.p12m_high)}).`;
  const tail = risk.model === 'views_blend'
    ? ` The figures above blend 70% ViEWS with 30% our model${own ? ` (our model alone: ${pct(own.p)} per year)` : ''}.`
    : v.skipped === 'interstate_war'
      ? ' ViEWS counts all fighting on the territory, including a war with another state, so it is not used for internal conflict here; the figures above are our model.'
      : ' The conflict is already active, so the figures above are our continuation model; ViEWS is shown for comparison.';
  return `<p class="basis views-note">${escape(head + tail)}</p>`;
}

function countryPage() {
  const country = byIso().get(selected);
  const horizons = snapshot?.horizons ?? [];
  const block = (entry: EventTypeEntry) => {
    const risk = country?.risks[entry.key]!;
    return `<article class="risk-block"><div class="risk-head"><h3>${escape(typeLabel(entry))}</h3>${risk.active ? ongoingTag() : ''}</div>
      <p class="question">${escape(questionText(entry.key, risk))}</p>
      <div class="horizon-grid">${horizons.map((h) => `<div><span class="h-label">${escape(lang === 'ru' ? h.label_ru : h.label_en)}</span>${value(risk, h.key, 'lg')}</div>`).join('')}</div>
      ${explainBlock(entry, risk)}
      <p class="basis">${escape(t().basis(risk.basis.exposure_years, risk.basis.event_years, risk.basis.last_event_year))} ${t().confidence}: ${confidenceText(risk.confidence)}.</p>
      ${entry.key === 'internal_armed_conflict' ? viewsNote(country!, risk) : ''}
      <details><summary>${t().definition}</summary><p>${escape(lang === 'ru' ? entry.resolution_ru : entry.resolution_en)}</p></details>
    </article>`;
  };
  const types = snapshot?.event_types ?? [];
  const groups = [['conflict', t().groupConflict], ['natural', t().groupNatural], ['society', t().groupSociety]] as const;
  const blocks = groups.map(([group, label]) => {
    const inGroup = types.filter((e) => (e.group ?? 'conflict') === group);
    const ready = inGroup.filter((e) => e.available && country?.risks[e.key]);
    const missing = inGroup.filter((e) => !(e.available && country?.risks[e.key]));
    if (!inGroup.length) return '';
    return `<div class="risk-group"><h3 class="group-title">${escape(label)}</h3>${ready.map(block).join('')}
      ${missing.length ? `<p class="missing">${missing.map((e) => `${escape(typeLabel(e))} — ${!e.modeled ? t().inProgress : t().unavailable}`).join(' · ')}</p>` : ''}</div>`;
  }).join('');
  return `<section class="page-head country-head">
      <label class="select compact"><span>${t().searchCountry}</span><select data-field="country">${countryOptions()}</select></label>
      <div class="country-title"><h1>${escape(countryName(country, selected))}</h1>${country ? pinButton(country.iso3) : ''}</div>
      ${country ? countryHero(country) : ''}
      <div class="lead-summary"><h2>${t().summaryTitle}</h2>${summarySentences(country, '1y')}</div>
    </section>
    ${country ? sectionNav() : ''}
    ${country ? implications(country) : ''}
    <section class="section">${assistantPanel(lang, countryName(country, selected), escape, true)}</section>
    <section class="section" id="regional" aria-live="polite"></section>
    <section class="section" id="country-signals">${countrySignals(viewContext(), signalsData, country)}</section>
    <section class="section" id="country-scenarios">${countryScenarios(viewContext(), scenariosData, selected)}</section>
    <section class="section" id="country-links">${linksSection(viewContext(), selected, chainEvent, neighbourCodes(selected), linksData)}</section>
    <section class="section hazards" id="hazards" aria-live="polite"><div class="section-head"><h2>${t().hazardsTitle}</h2><p>${t().hazardsLead}</p></div>
      <div class="loading-inline">${t().hazardsLoading}</div></section>
    <section class="section" id="country-migration">${migrationSection(viewContext(), selected, linksData)}</section>
    <section class="section" id="all-risks"><div class="section-head"><h2>${t().allRisks}</h2><p>${t().intervalText}</p></div><div class="risk-blocks">${blocks}</div></section>`;
}

function verdictCard(title: string, kind: 'travel' | 'business', v: Verdict, extra = '') {
  return `<article class="verdict"><h3>${title}</h3>${levelBadge(kind, v.level)}
    <ul>${v.reasons.map((r) => `<li>${escape(r)}</li>`).join('')}</ul>${extra}</article>`;
}

function countryAlert(country: CountryEntry) {
  const entry = signalsData?.countries[country.iso3];
  if (!entry) return '';
  if (entry.danger) return dangerCard(entry.danger, lang, labelOf, (p) => percent(p, lang), escape);
  const risk = entry.alert?.risk ? labelOf(entry.alert.risk) : '';
  return alertCard(entry.alert, lang, (p) => percent(p, lang), escape, risk ? `${t().alertBy}: ${risk}` : '');
}

function relocationParts(country: CountryEntry) {
  const scen = (scenariosData?.scenarios ?? []).flatMap((s) => s.affected.filter((a) => a.iso3 === country.iso3)
    .map((a) => ({ title: lang === 'ru' ? s.title_ru : s.title_en, role: a.role, horizons: s.horizons as Record<string, { p: number }> })));
  return relocationVerdict(country, scen, labelOf, lang).map((p) => (p.horizon === 'short' ? { ...p, level: floorLevel(p.level, country) } : p));
}

function relocationCard(country: CountryEntry) {
  const parts = relocationParts(country);
  return `<article class="verdict relocation"><h3>${t().forRelocation}</h3>${parts.map((p) => `<div class="reloc-part"><h4 class="sub">${escape(relocationHorizon(p.horizon, lang))}</h4>
    <span class="level level-${levelClass(p.level)}"><b>${p.level}</b>${escape(relocationLevelLabel(p.level, lang))}</span><ul>${p.reasons.map((r) => `<li>${escape(r)}</li>`).join('')}</ul></div>`).join('')}
    ${relocationPolicy(country.iso3)}
    <p class="muted-text small">${escape(relocationNote(lang))}</p></article>`;
}

function relocationPolicy(iso3: string) {
  const p = linksData?.countries[iso3]?.migration?.policy;
  if (!p || !p.entries.length) return '';
  const word = p.d365 > 0 ? (lang === 'ru' ? 'ужесточение' : 'tightening') : p.d365 < 0 ? (lang === 'ru' ? 'смягчение' : 'easing') : (lang === 'ru' ? 'изменения в обе стороны' : 'changes both ways');
  const text = lang === 'ru'
    ? `Правила въезда и проживания для иностранцев: за 12 месяцев сообщалось о ${word === 'изменения в обе стороны' ? 'изменениях в обе стороны' : word === 'ужесточение' ? 'ужесточении' : 'смягчении'} (подробнее в разделе «Миграция»).`
    : `Entry and residence rules for foreigners: ${word} reported over 12 months (see Migration).`;
  return `<p class="small">${escape(text)}</p>`;
}

function implications(country: CountryEntry) {
  const travel = travelOf(country);
  const advisory = country.advisory;
  const uk = country.advisory_uk;
  const links = [advisory?.url ? `<a href="${escape(advisory.url)}" rel="noreferrer">travel.state.gov</a>` : '',
    uk?.url ? `<a href="${escape(uk.url)}" rel="noreferrer">gov.uk</a>` : ''].filter(Boolean).join(' · ');
  const travelExtra = `${travel.regional.length ? `<h4 class="sub">${t().regionalTitle}</h4><ul>${travel.regional.map((r) => `<li>${escape(r)}</li>`).join('')}</ul>` : ''}
    <p class="source-line">${travel.official ? t().officialSource : t().modelSource}${links ? ' · ' + links : ''}</p>
    ${uk?.restrictions?.length ? `<details><summary>${t().ukRestrictions}</summary><p lang="en" class="restr">${uk.restrictions.map(escape).join('<br>')}</p></details>` : ''}
    ${advisory?.summary ? `<details><summary>${t().officialText}</summary><p lang="en">${escape(advisory.summary)}</p></details>` : ''}`;
  const lines = spillover(country, neighbourCountries(country), (c) => countryName(c), lang);
  return `<section class="section"><div class="section-head"><h2>${t().implicationsTitle}</h2><p>${t().implicationsLead}</p></div>
    ${countryAlert(country)}
    ${humanitarianCard(country.humanitarian_severity, lang, escape)}
    <div class="verdicts">${verdictCard(t().forTravel, 'travel', travel, travelExtra)}${verdictCard(t().forBusiness, 'business', businessOf(country))}${relocationCard(country)}
      <article class="verdict"><h3>${t().forOthers}</h3><ul>${lines.map((l) => `<li>${escape(l)}</li>`).join('')}</ul>
      ${groupsOf(country.iso3).filter((g) => g.kind === 'bloc').length ? `<h4 class="sub">${t().memberOf}</h4><p class="muted-text">${groupsOf(country.iso3).filter((g) => g.kind === 'bloc').map((g) => escape(groupName(g, lang)) + (groupNote(g, lang) ? ` — ${escape(groupNote(g, lang)!)}` : '')).join('<br>')}</p>` : ''}</article></div></section>
    ${contextSection(country)}`;
}

const macro = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1)).replace('.', lang === 'ru' ? ',' : '.') + '%';

function sparkline(values: number[]) {
  const max = Math.max(...values, 1e-9), min = Math.min(...values, 0);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 200},${40 - ((v - min) / (max - min || 1)) * 36}`).join(' ');
  return `<svg class="spark" viewBox="0 0 200 42" aria-hidden="true"><polyline points="${pts}"/></svg>`;
}

function contextSection(country: CountryEntry) {
  const items: string[] = [];
  const elections = (country.elections ?? []).filter((e) => new Date(e.date).getTime() > Date.now() - 7 * 864e5).slice(0, 4);
  if (elections.length) {
    items.push(`<article class="ctx"><h3>${t().ctxElections}</h3><ul>${elections.map((e) => `<li><strong>${escape(formatElectionDate(e.date, e.precision))}</strong> — ${escape((lang === 'ru' ? e.name_ru : null) ?? e.name_en)}</li>`).join('')}</ul></article>`);
  }
  const o = country.outlook;
  if (o?.growth || o?.inflation) {
    const years = Object.keys({ ...(o.growth ?? {}), ...(o.inflation ?? {}) }).sort();
    items.push(`<article class="ctx"><h3>${t().ctxImf}</h3><table class="mini"><thead><tr><th></th>${years.map((y) => `<th>${y}</th>`).join('')}</tr></thead><tbody>
      <tr><th>${t().ctxGrowth}</th>${years.map((y) => `<td>${o.growth?.[y] !== undefined ? macro(o.growth[y]) : '—'}</td>`).join('')}</tr>
      <tr><th>${t().ctxInflation}</th>${years.map((y) => `<td>${o.inflation?.[y] !== undefined ? macro(o.inflation[y]) : '—'}</td>`).join('')}</tr>
      ${o.debt ? `<tr><th>${t().ctxDebt}</th>${years.map((y) => `<td>${o.debt?.[y] !== undefined ? macro(o.debt[y]) : '—'}</td>`).join('')}</tr>` : ''}</tbody></table>
      <p class="muted-text small">${t().ctxImfNote}</p></article>`);
  }
  if (country.democracy) {
    const v = country.democracy.value;
    items.push(`<article class="ctx"><h3>${t().ctxDemocracy}</h3><p class="big">${v.toFixed(2).replace('.', lang === 'ru' ? ',' : '.')}<small> / 1</small></p>
      <p class="muted-text small">${t().ctxDemocracyNote(country.democracy.year, v)}</p></article>`);
  }
  if (country.gpr && country.gpr.ratio_12m !== null) {
    items.push(`<article class="ctx"><h3>${t().ctxGpr}</h3>${sparkline(country.gpr.values)}
      <p class="muted-text small">${t().ctxGprNote(country.gpr.ratio_12m.toFixed(1).replace('.', lang === 'ru' ? ',' : '.'), country.gpr.latest_month)}</p></article>`);
  }
  return items.length ? `<section class="section"><div class="section-head"><h2>${t().ctxTitle}</h2><p>${t().ctxLead}</p></div><div class="ctx-grid">${items.join('')}</div></section>` : '';
}

function formatElectionDate(value: string, precision: 'day' | 'month' | 'year') {
  const d = new Date(value);
  if (precision === 'year') return String(d.getUTCFullYear());
  return new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', precision === 'month'
    ? { month: 'long', year: 'numeric', timeZone: 'UTC' } : { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' }).format(d);
}

function seasonChart(months: number[]) {
  const max = Math.max(...months, 1);
  return `<div class="season" role="img" aria-label="${escape(t().hazardSeason)}">${months.map((n, i) =>
    `<span><i style="height:${Math.max((n / max) * 100, n ? 8 : 2)}%"${n ? '' : ' class="zero"'}></i><small>${t().months[i]}</small></span>`).join('')}</div>`;
}

function hazardCard(type: string, h: HazardSummary) {
  const entry = typeEntry(type);
  const events = h.events.slice(0, 6).map((e) => `<li><span class="dot ${e.alert === 'Red' ? 'red' : 'orange'}"></span>
    <span class="ev-name">${escape(e.name || typeLabel(entry))}</span>
    <span class="ev-meta">${e.month ? t().months[e.month - 1] + ' ' : ''}${e.year}${(lang === 'ru' ? e.region_ru : e.region_en) ? ' · ' + escape((lang === 'ru' ? e.region_ru : e.region_en)!) : ''}${e.severity ? ' · ' + escape(e.severity) : ''}</span></li>`).join('');
  const regions = (h.regions ?? []).slice(0, 6).map((r) => `${escape(lang === 'ru' ? r.ru : r.en)} (${r.n})`).join(', ');
  return `<article class="hazard-card"><div class="hazard-head"><h3>${escape(typeLabel(entry))}</h3>
      <p>${escape(t().hazardCount(h.count, h.red, h.first_year, h.last_year))}</p>
      ${regions ? `<p class="where"><strong>${t().hazardWhere}:</strong> ${regions}</p>` : ''}</div>
    <div class="hazard-cols"><div><h4>${t().hazardSeason}</h4>${seasonChart(h.months)}</div>
      <div><h4>${t().hazardEvents}</h4><ul class="events">${events}</ul></div></div>
    <p class="impact"><strong>${t().hazardImpactTitle}.</strong> ${escape(t().impacts[type] ?? '')}</p></article>`;
}

async function fillHazards(iso3: string) {
  const details = await loadHazards();
  const node = root.querySelector<HTMLElement>('#hazards');
  if (!node || currentPage() !== 'country' || selected !== iso3) return;
  const head = node.querySelector('.section-head')?.outerHTML ?? '';
  const data = details?.countries[iso3];
  const order = ['major_earthquake', 'tsunami', 'tropical_cyclone', 'flood', 'volcano', 'drought', 'wildfire'];
  const kinds = order.filter((k) => data?.[k]?.count);
  if (!data || !kinds.length) {
    node.innerHTML = head + `<p class="muted-text">${t().hazardsNone}</p><p class="muted-text small">${t().tornadoNote}</p>`;
    return;
  }
  const points = kinds.flatMap((k) => data[k].events
    .filter((e) => e.lat !== null && e.lon !== null)
    .map((e) => ({ lat: e.lat!, lon: e.lon!, cls: (e.alert === 'Red' ? 'red' : 'orange') + ' hz-' + k,
      title: `${typeLabel(typeEntry(k))}: ${e.name} (${e.year})${e.severity ? ', ' + e.severity : ''}` })));
  node.innerHTML = head + `<div class="hazard-layout"><div class="country-map"><svg viewBox="0 0 600 340" role="img" aria-label="${escape(t().hazardsTitle)}"></svg>
      <div class="cm-legend"><span><i class="red"></i>${t().alertRed}</span><span><i class="orange"></i>${t().alertOrange}</span></div></div>
    <div class="hazard-cards">${kinds.map((k) => hazardCard(k, data[k])).join('')}</div></div>
    <p class="muted-text small">${t().tornadoNote}</p>`;
  const svg = node.querySelector<SVGSVGElement>('.country-map svg');
  const country = byIso().get(iso3);
  const key = country?.numeric ?? (iso3 === 'XKX' ? 'name:Kosovo' : '');
  if (svg && !drawCountryMap(svg, key, points)) svg.closest('.country-map')?.remove();
}

function changeList(changes: Change[]) {
  if (!changes.length) return notice(t().noChanges);
  const countries = byIso();
  return `<ul class="changes">${changes.slice(0, 200).map((change) => {
    const name = countryName(countries.get(change.iso3), change.iso3);
    const type = typeLabel(typeEntry(change.event_type));
    const head = `<button type="button" class="link" data-select="${change.iso3}">${escape(name)}</button><span class="change-type">${escape(type)}</span>`;
    if (change.kind === 'state_change') {
      return `<li>${head}<strong class="${change.to === 'active_at_end' ? 'up' : 'down'}">${change.to === 'active_at_end' ? t().stateStarted : t().stateEnded}</strong></li>`;
    }
    const delta = change.delta ?? 0;
    const pp = (Math.abs(delta) * 100).toFixed(1).replace('.', lang === 'ru' ? ',' : '.');
    return `<li>${head}<span class="change-detail">${escape(horizonLabel(change.horizon ?? ''))}: ${pct(Number(change.from))} → <strong>${pct(Number(change.to))}</strong>
      <span class="${delta > 0 ? 'up' : 'down'}">${delta > 0 ? '+' : '−'}${pp} ${t().pp}</span></span></li>`;
  }).join('')}</ul>`;
}

function changesPage() {
  if (!snapshot) return '';
  const visit = previousVisit
    ? `<p class="period">${formatDate(previousVisit.generated_at)} — ${formatDate(snapshot.generated_at)}</p>${changeList(changesSince(previousVisit, snapshot))}`
    : notice(t().firstVisitNote);
  const data = snapshot.previous_generated_at
    ? `<p class="period">${formatDate(snapshot.previous_generated_at)} — ${formatDate(snapshot.generated_at)}</p>${changeList(snapshot.changes)}`
    : notice(t().firstSnapshot);
  return `<section class="page-head"><h1>${t().changesTitle}</h1><p>${t().changesLead}</p></section>
    <div class="columns"><section class="section"><div class="section-head"><h2>${t().changesVisit}</h2></div>${visit}</section>
    <section class="section"><div class="section-head"><h2>${t().changesData}</h2></div>${data}</section></div>`;
}

function assistantPage() {
  const country = byIso().get(selected);
  return `<section class="page-head"><h1>${t().assistantTitle}</h1></section>
    <div class="assistant-page"><label class="select compact"><span>${t().selectCountry}</span><select data-field="country">${countryOptions()}</select></label>
    ${assistantPanel(lang, countryName(country, selected), escape)}</div>`;
}

// Compact summary of the selected country for the assistant (the only data it sees).
function assistantContext() {
  const country = byIso().get(selected);
  if (!country || !snapshot) return {};
  const d = dangerOf(country);
  const risks: Record<string, unknown> = {};
  for (const e of snapshot.event_types) {
    const r = country.risks[e.key];
    if (!r) continue;
    risks[lang === 'ru' ? e.label_ru : e.label_en] = {
      ongoing: r.active || undefined,
      question: r.question,
      ...Object.fromEntries(Object.entries(r.horizons).map(([h, v]) => [h, `${pct(v.p)} (${pct(v.low)}–${pct(v.high)})`])),
    };
  }
  const scen = (scenariosData?.scenarios ?? []).filter((s) => s.affected.some((a) => a.iso3 === country.iso3)).slice(0, 6)
    .map((s) => ({ title: lang === 'ru' ? s.title_ru : s.title_en, role: s.affected.find((a) => a.iso3 === country.iso3)?.role,
      horizons: Object.fromEntries(Object.entries(s.horizons).map(([h, v]) => [h, pct(v.p)])) }));
  return {
    country: countryName(country), data_date: snapshot.generated_at.slice(0, 10), model_version: (snapshot as unknown as { model_version?: string }).model_version,
    danger_level: d ? { level: d.level, scale: '1 normal, 2 elevated, 3 high, 4 very high, 5 extreme (fighting in the region)',
      drivers: d.drivers.slice(0, 5), ministries: d.ministries, ministry_median: d.ministry_median,
      regional: (d as unknown as { regional?: unknown }).regional, foreigners: d.foreigners.map((f) => f.en), trend: d.trend } : undefined,
    advice_levels: { travel: travelOf(country).level, business: businessOf(country).level, relocation_1_5y: relocationParts(country)[1].level },
    humanitarian: country.humanitarian_severity ?? undefined,
    probabilities: risks, scenarios: scen,
    notes: 'Probabilities: chance of at least one event within the horizon; ranges are 90% intervals. "ongoing" means the state continues.',
  };
}

function rerenderChat() {
  const node = root.querySelector<HTMLElement>('#assistant');
  if (!node) return;
  node.outerHTML = assistantPanel(lang, countryName(byIso().get(selected), selected), escape, currentPage() === 'country');
  root.querySelector<HTMLElement>('#assistant .chat-log')?.lastElementChild?.scrollIntoView({ block: 'nearest' });
}

function methodPage() {
  if (!snapshot) return '';
  const sources = snapshot.sources.map((s) => `<tr><th scope="row">${escape(s.name)}</th>
    <td><span class="status ${s.status}">${s.status === 'ok' ? t().ok : t().failed}</span></td>
    <td>${s.version ? escape(t().version + ' ' + s.version) : ''}${s.retrieved_at ? '<br><small>' + formatDate(s.retrieved_at) + '</small>' : ''}</td></tr>`).join('');
  const types = snapshot.event_types.map((e) => `<tr><th scope="row">${escape(typeLabel(e))}</th>
    <td><span class="status ${e.available ? 'ok' : e.modeled ? 'failed' : 'pending'}">${!e.modeled ? t().inProgress : e.available ? t().ok : t().failed}</span></td>
    <td>${e.data_window ? `${t().window} ${e.data_window[0]}–${e.data_window[1]}` : ''}<br><small>${escape(lang === 'ru' ? e.resolution_ru : e.resolution_en)}</small></td></tr>`).join('');
  return `<section class="page-head"><h1>${t().methodTitle}</h1><p>${t().methodLead}</p></section>
    <section class="section prose"><h2>${t().method}</h2><p>${escape(lang === 'ru' ? snapshot.method.description_ru : snapshot.method.description_en)}</p>
      <h3>${t().interval}</h3><p>${t().intervalText}</p><h3>${t().calibration}</h3><p>${t().notCalibrated}</p><h3>${t().protestTitle}</h3><p>${t().protestText}</p></section>
    <section class="section"><div class="section-head"><h2>${t().eventTypes}</h2></div><table class="table"><tbody>${types}</tbody></table></section>
    <section class="section"><div class="section-head"><h2>${t().sources}</h2></div><table class="table"><tbody>${sources}</tbody></table></section>`;
}

function body(page: Page) {
  if (loadError) return notice(t().loadError, `<button class="button" data-retry>${t().retry}</button>`, 'alert');
  if (!snapshot) return `<div class="loading" role="status">${t().loading}</div>`;
  if (page === 'country') return countryPage();
  if (page === 'scenarios') return scenariosPage(viewContext(), scenariosData, currentScenario, horizonLabels());
  if (page === 'lenses') return lensesPage(viewContext(), scenariosData);
  if (page === 'accuracy') return accuracyPage(viewContext(), accuracyData, backtestData, realBacktestData, btCase, trainedSection(trainedData, lang, escape));
  if (page === 'signals') return signalsPage(viewContext(), signalsData);
  if (page === 'migration') return migrationPage(viewContext(), linksData, migMode);
  if (page === 'changes') return changesPage();
  if (page === 'assistant') return assistantPage();
  if (page === 'method') return methodPage();
  return overview();
}

function render() {
  const page = currentPage();
  document.documentElement.lang = lang;
  regionNames = undefined;
  root.innerHTML = `<header class="topbar">
      <a class="brand" href="#overview" aria-label="${t().brand}"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><ellipse cx="12" cy="12" rx="4.2" ry="10"/><path d="M2 12h20"/></svg><span>${t().brand}</span></a>
      <nav aria-label="Primary">${pages.map(([key, label]) =>
        `<a href="#${key}"${key === page ? ' aria-current="page"' : ''}>${t()[label]}</a>`).join('')}</nav>
      <div class="topbar-meta">${snapshot ? searchBox(lang) : ''}${snapshot ? `<span class="updated">${t().updated} ${formatDate(snapshot.generated_at)}</span>` : ''}${themeButton(theme, lang)}<button type="button" class="lang" data-lang>${t().langSwitch}</button></div>
    </header>
    <main id="workspace" tabindex="-1">${body(page)}</main>
    <footer class="footer">${t().brand}. ${t().summaryCaveat} Natural Earth.</footer>`;
  if (snapshot) {
    wireSearch(root, () => (snapshot?.countries ?? []).map((c) => ({ iso3: c.iso3, name: countryName(c), level: dangerLevelOf(c) || undefined })),
      (iso) => { selectCountry(iso); if (currentPage() !== 'country') location.hash = '#country'; else window.scrollTo(0, 0); }, lang);
  }
  if (page === 'country' && snapshot) {
    void fillHazards(selected);
    const iso = selected;
    void fillRegional(root, iso, lang, (p) => percent(p, lang), escape, () => currentPage() === 'country' && selected === iso);
  }
  drawExtraMaps();
  const map = root.querySelector<HTMLElement>('#map');
  if (map && snapshot) {
    const shapes = shapeToIso();
    const countries = byIso();
    updateMapSelection = drawMap(map, [...shapes].find(([, iso]) => iso === selected)?.[0] ?? '',
      (key) => {
        const country = countries.get(shapes.get(key) ?? '');
        if (eventType === 'view_danger') return country && dangerLevelOf(country) ? 'd-' + dangerLevelOf(country) : '';
        if (eventType === 'view_political') { const p = country ? signalsData?.political_crisis?.[country.iso3] : undefined; return !country ? '' : p?.confirmed ? 'active' : 'minimal'; }
        if (isView(eventType)) return country ? 'v-' + levelClass(viewVerdict(country).level) : '';
        const group = lens !== 'countries' ? currentGroup() : undefined;
        if (group && !group.members.includes(country?.iso3 ?? '')) return 'dimmed';
        const risk = country?.risks[eventType];
        if (!risk) return '';
        return risk.question === 'active_at_end' ? 'active' : band(risk.horizons[horizon].p);
      },
      (key, fallback) => {
        const country = countries.get(shapes.get(key) ?? '');
        const risk = country?.risks[eventType];
        const label = country ? countryName(country) : fallback;
        if (country && eventType === 'view_danger') { const d = dangerLevelOf(country); return d ? `${label}: ${d} — ${dangerName(d, lang)}` : label; }
        if (country && eventType === 'view_political') { const p = signalsData?.political_crisis?.[country.iso3]; return p ? `${label}: ${p.events[0] ? (lang === 'ru' ? p.events[0].summary_ru : p.events[0].summary_en) : ''}` : `${label}: ${lang === 'ru' ? 'событий не обнаружено' : 'no events detected'}`; }
        if (country && isView(eventType)) return `${label}: ${viewVerdict(country).level} — ${levelLabel(viewKind(), viewVerdict(country).level, lang)}`;
        if (!risk) return label + ': ' + t().legendNoData.toLowerCase();
        const v = risk.horizons[horizon];
        return `${label}: ${pct(v.p)} (${pct(v.low)} – ${pct(v.high)})${risk.active ? ', ' + t().ongoing : ''}`;
      },
      (key) => { const iso = shapes.get(key); if (iso) selectCountry(iso); });
  }
}

// Initial map view per scenario: [longitude, latitude, zoom].
const SCENARIO_FOCUS: Record<string, [number, number, number]> = {
  russia_nato: [22, 56, 3], ukraine_ceasefire: [25, 50, 2.6], china_taiwan: [122, 26, 2.6],
  iran_strikes: [48, 28, 2.6], india_pakistan: [74, 28, 3], korea: [128, 37, 3.2],
  russia_nato_war: [22, 56, 2.6], moldova_transnistria: [29, 47, 5], belarus_front: [27, 53, 4],
  serbia_kosovo: [21, 43, 6], venezuela_guyana: [-61, 6, 4], turkey_greece: [27, 38, 4.5],
  sahel_coups: [5, 15, 3], us_guarantee: [10, 50, 1.6],
  armenia_azerbaijan: [46, 40, 6], israel_hezbollah: [35.5, 33, 7], hormuz_reopening: [54, 26, 4],
  georgia_crisis: [43.5, 42, 6], iraq_strikes: [44, 33, 4.5],
};

function drawExtraMaps() {
  if (!snapshot) return;
  const shapes = shapeToIso();
  const scenarioMap = root.querySelector<HTMLElement>('#scenario-map');
  const scenario = scenariosData?.scenarios.find((s) => s.key === currentScenario) ?? scenariosData?.scenarios[0];
  if (scenarioMap && scenario) {
    const roles = new Map(scenario.affected.map((a) => [a.iso3, a.role]));
    drawMap(scenarioMap, '', (key) => { const role = roles.get(shapes.get(key) ?? ''); return role ? roleClass(role) : ''; },
      (key, fallback) => {
        const iso = shapes.get(key) ?? '';
        const role = roles.get(iso);
        return `${iso ? nameOf(iso) : fallback}${role ? ': ' + vt(lang).role[role].toLowerCase() : ''}`;
      },
      (key) => { const iso = shapes.get(key); if (iso) { selectCountry(iso); location.hash = '#country'; } },
      SCENARIO_FOCUS[scenario.key]);
  }
  const signalsMap = root.querySelector<HTMLElement>('#signals-map');
  if (signalsMap && signalsData) {
    const of = (iso: string) => signalsData?.countries[iso];
    drawMap(signalsMap, '', (key) => factorClass(of(shapes.get(key) ?? '')?.max_factor),
      (key, fallback) => {
        const iso = shapes.get(key) ?? '';
        const c = of(iso);
        return `${iso ? nameOf(iso) : fallback}${c ? `: ×${c.max_factor.toFixed(2).replace('.', lang === 'ru' ? ',' : '.')} · ${st(lang).activeSigns(c.active)}` : ''}`;
      },
      (key) => { const iso = shapes.get(key); if (iso) { selectCountry(iso); location.hash = '#country'; } });
  }
  const migrationMap = root.querySelector<HTMLElement>('#migration-map');
  if (migrationMap && linksData) {
    const per = (iso: string) => linksData?.countries[iso]?.migration?.[migMode === 'hosted' ? 'hosted_per_1000' : 'abroad_per_1000'];
    drawMap(migrationMap, '', (key) => migrationClass(per(shapes.get(key) ?? '')),
      (key, fallback) => {
        const iso = shapes.get(key) ?? '';
        const v = per(iso);
        return `${iso ? nameOf(iso) : fallback}: ${v === undefined ? vt(lang).migNoData.toLowerCase() : vt(lang).perThousand(v.toFixed(1).replace('.', lang === 'ru' ? ',' : '.'))}`;
      },
      (key) => { const iso = shapes.get(key); if (iso) { selectCountry(iso); location.hash = '#country'; } });
  }
}

function selectCountry(iso3: string) {
  selected = iso3;
  store('geointel.country', iso3);
  const panel = root.querySelector<HTMLElement>('#country-panel');
  if (panel && currentPage() === 'overview') {
    panel.outerHTML = briefPanel();
    const key = [...shapeToIso()].find(([, iso]) => iso === iso3)?.[0];
    if (key) updateMapSelection?.(key);
  } else {
    render();
  }
}

root.addEventListener('click', (event) => {
  const target = event.target as HTMLElement;
  const suggestion = target.closest<HTMLElement>('[data-ask]')?.dataset.ask;
  if (suggestion) { void ask(suggestion, lang, assistantContext(), rerenderChat); return; }
  if (target.closest('[data-chat-clear]')) { clearChat(); rerenderChat(); return; }
  if (target.closest('[data-theme-cycle]')) { theme = nextTheme(theme); applyTheme(theme); render(); return; }
  if (target.closest('[data-picker-toggle]')) { togglePicker(root); return; }
  const pick = target.closest<HTMLElement>('[data-pick]')?.dataset.pick;
  if (pick) { eventType = pick; store('geointel.type', pick); render(); return; }
  if (!target.closest('.picker')) togglePicker(root, false);
  const pin = target.closest<HTMLElement>('[data-pin]')?.dataset.pin;
  if (pin) { togglePin(pin); render(); return; }
  const jump = target.closest<HTMLElement>('[data-jump]')?.dataset.jump;
  if (jump) { event.preventDefault(); root.querySelector(`#${jump}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
  const select = target.closest<HTMLElement>('[data-select]')?.dataset.select;
  if (select) {
    selectCountry(select);
    if (currentPage() !== 'overview') location.hash = '#country';
    else root.querySelector('#country-panel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return;
  }
  const scenarioKey = target.closest<HTMLElement>('[data-scenario]')?.dataset.scenario;
  if (scenarioKey) {
    currentScenario = scenarioKey;
    store('geointel.scenario', scenarioKey);
    if (currentPage() === 'scenarios') render(); else location.hash = '#scenarios';
    return;
  }
  const chain = target.closest<HTMLElement>('[data-chain]')?.dataset.chain as ChainEvent | undefined;
  if (chain) {
    chainEvent = chain;
    store('geointel.chain', chain);
    const node = root.querySelector<HTMLElement>('#country-links');
    if (node) node.innerHTML = linksSection(viewContext(), selected, chainEvent, neighbourCodes(selected), linksData);
    return;
  }
  const bt = target.closest<HTMLElement>('[data-btcase]')?.dataset.btcase;
  if (bt) { btCase = bt; store('geointel.btcase', bt); render(); return; }
  const mode = target.closest<HTMLElement>('[data-migmode]')?.dataset.migmode as typeof migMode | undefined;
  if (mode) { migMode = mode; store('geointel.migmode', mode); render(); return; }
  const lensKey = target.closest<HTMLElement>('[data-lens]')?.dataset.lens as typeof lens | undefined;
  if (lensKey) { lens = lensKey; store('geointel.lens', lens); render(); return; }
  const groupKey = target.closest<HTMLElement>('[data-group]')?.dataset.group;
  if (groupKey) { selectedGroup = groupKey; store('geointel.group', groupKey); render(); return; }
  const h = target.closest<HTMLElement>('[data-horizon]')?.dataset.horizon as HorizonKey | undefined;
  if (h) { horizon = h; store('geointel.horizon', h); render(); return; }
  if (target.closest('[data-lang]')) { lang = lang === 'ru' ? 'en' : 'ru'; store('geointel.lang', lang); render(); return; }
  if (target.closest('[data-retry]')) void start();
});

root.addEventListener('submit', (event) => {
  const chat = (event.target as HTMLElement).closest<HTMLFormElement>('[data-chat]');
  if (chat) {
    event.preventDefault();
    const q = (chat.elements.namedItem('q') as HTMLTextAreaElement).value;
    void ask(q, lang, assistantContext(), rerenderChat);
    return;
  }
  const form = (event.target as HTMLElement).closest<HTMLFormElement>('#expert-form');
  if (!form) return;
  event.preventDefault();
  const { text, ok, fail } = surveyAnswer(form, lang);
  const out = form.querySelector<HTMLTextAreaElement>('#expert-output');
  const status = form.querySelector<HTMLElement>('#expert-status');
  if (out) { out.hidden = false; out.value = text; out.select(); }
  const done = (good: boolean) => { if (status) status.textContent = good ? ok : fail; };
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => done(true), () => done(false));
  else done(false);
});

root.addEventListener('change', (event) => {
  const field = event.target as HTMLSelectElement;
  if (field.dataset.field === 'type') { eventType = field.value; store('geointel.type', eventType); render(); }
  if (field.dataset.field === 'country') selectCountry(field.value);
  if (field.dataset.field === 'group') { selectedGroup = field.value; store('geointel.group', selectedGroup); render(); }
});

root.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') togglePicker(root, false);
  const node = (event.target as Element).closest?.('g[data-select]') as SVGGElement | null;
  if (node && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault();
    selectCountry(node.dataset.select!);
    window.scrollTo(0, 0);
  }
});

window.addEventListener('hashchange', () => { render(); window.scrollTo(0, 0); root.querySelector<HTMLElement>('main')?.focus({ preventScroll: true }); });

async function start() {
  loadError = false;
  render();
  try {
    snapshot = await loadSnapshot();
    previousVisit = readVisit();
    if (previousVisit?.generated_at === snapshot.generated_at) {
      previousVisit = JSON.parse(stored('geointel.prevVisit.v1') ?? 'null') ?? undefined;
    } else if (previousVisit) {
      store('geointel.prevVisit.v1', JSON.stringify(previousVisit));
    }
    writeVisit(snapshot);
    void loadHazards().then((data) => { hazardsData = data; if (currentPage() === 'overview') render(); });
    void loadScenarios().then((data) => { scenariosData = data; if (['scenarios', 'country', 'lenses'].includes(currentPage())) render(); });
    void loadLinks().then((data) => { linksData = data; if (['migration', 'country', 'overview'].includes(currentPage())) render(); });
    void loadSignals().then((data) => { signalsData = data; if (['signals', 'country', 'overview'].includes(currentPage())) render(); });
    void loadBacktest().then((data) => { backtestData = data; if (currentPage() === 'accuracy') render(); });
    void loadRealBacktest().then((data) => { realBacktestData = data; if (currentPage() === 'accuracy') render(); });
    void loadAccuracy().then((data) => { accuracyData = data; if (currentPage() === 'accuracy') render(); });
    void fetch(import.meta.env.BASE_URL + 'data/trained.json', { cache: 'no-cache' }).then((r) => (r.ok ? r.json() as Promise<TrainedFile> : undefined)).then((data) => { trainedData = data; if (currentPage() === 'accuracy') render(); }).catch(() => undefined);
    if (!isView(eventType) && !typeEntry(eventType)?.available) eventType = snapshot.event_types.find((e) => e.available)?.key ?? eventType;
    if (!byIso().has(selected)) selected = snapshot.countries[0]?.iso3 ?? '';
  } catch {
    loadError = true;
  }
  render();
}

void start();
