import './style.css';
import {
  band, changesSince, loadSnapshot, percent, readVisit, writeVisit,
} from './data';
import type { Change, CountryEntry, EventTypeEntry, HorizonKey, Lang, Risk, Snapshot, VisitMemory } from './data';
import { dictionaries } from './i18n';
import { drawMap } from './map';

const pages = [
  ['overview', 'navOverview', '◈'],
  ['country', 'navCountry', '◎'],
  ['changes', 'navChanges', '⌁'],
  ['method', 'navMethod', '▤'],
] as const;
type Page = typeof pages[number][0];

const root = document.querySelector<HTMLElement>('#app')!;
const stored = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const store = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* ignore */ } };

let lang: Lang = (new URLSearchParams(location.search).get('lang') ?? stored('geointel.lang')) === 'en' ? 'en' : 'ru';
let eventType = stored('geointel.type') ?? 'internal_armed_conflict';
let horizon: HorizonKey = (stored('geointel.horizon') as HorizonKey | null) ?? '1y';
let selected = stored('geointel.country') ?? 'UKR';
let snapshot: Snapshot | undefined;
let previousVisit: VisitMemory | undefined;
let loadError = false;
let updateMapSelection: ((key: string) => void) | undefined;

const t = () => dictionaries[lang];
const escape = (value: string) => value.replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]!));
const currentPage = (): Page => pages.find(([key]) => '#' + key === location.hash)?.[0] ?? 'overview';
const dateTime = (value: string) => new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
}).format(new Date(value)) + ' UTC';

let regionNames: Intl.DisplayNames | undefined;
function countryName(country: CountryEntry | undefined, iso3 = ''): string {
  if (!country) return iso3;
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
const questionText = (key: string, risk: Risk) =>
  risk.question === 'active_at_end' ? t().qActive : isConflict(key) ? t().qOnsetConflict : t().qEvent;
const confidenceText = (value: Risk['confidence']) => ({
  low: t().confidenceLow, medium: t().confidenceMedium, high: t().confidenceHigh,
}[value]);
const ongoingTag = () => `<span class="tag active-tag">${t().ongoing}</span>`;
const state = (headline: string, description = '', role = 'status') =>
  `<div class="state" role="${role}"><strong>${headline}</strong>${description ? `<p>${description}</p>` : ''}</div>`;

function cell(risk: Risk, h: HorizonKey) {
  const v = risk.horizons[h];
  const cls = risk.question === 'active_at_end' ? 'active' : band(v.p);
  return `<span class="prob ${cls}">${percent(v.p, lang)}</span><small class="range">${percent(v.low, lang)}–${percent(v.high, lang)}</small>`;
}

function controls() {
  const types = snapshot?.event_types ?? [];
  const typeOptions = types.map((entry) => {
    const suffix = !entry.modeled ? ' — ' + t().notModeled : !entry.available ? ' — ' + t().unavailable : '';
    return `<option value="${entry.key}"${entry.key === eventType ? ' selected' : ''}${entry.available ? '' : ' disabled'}>${escape(typeLabel(entry) + suffix)}</option>`;
  }).join('');
  const horizonButtons = (snapshot?.horizons ?? []).map((h) =>
    `<button type="button" data-horizon="${h.key}" aria-pressed="${h.key === horizon}">${escape(lang === 'ru' ? h.label_ru : h.label_en)}</button>`).join('');
  return `<div class="filters">
    <label class="field">${t().eventType}<select data-field="type">${typeOptions}</select></label>
    <div class="field"><span>${t().horizon}</span><div class="segmented" role="group" aria-label="${t().horizon}">${horizonButtons}</div></div>
  </div>`;
}

function metrics() {
  if (!snapshot) return '';
  const active = snapshot.countries.filter((c) =>
    Object.entries(c.risks).some(([key, r]) => isConflict(key) && r.active)).length;
  const visitChanges = previousVisit ? changesSince(previousVisit, snapshot).length : null;
  return `<section class="metrics" aria-label="Summary">
    <div><span>${t().countries.toUpperCase()}</span><strong>${snapshot.countries.length}</strong></div>
    <div><span>${t().activeConflicts.toUpperCase()}</span><strong>${active}</strong></div>
    <div><span>${t().sinceVisit.toUpperCase()}</span><strong>${visitChanges ?? '—'}</strong><small>${visitChanges === null ? t().firstVisit : ''}</small></div>
    <div><span>${t().updated.toUpperCase()}</span><strong class="small-strong">${dateTime(snapshot.generated_at)}</strong></div>
  </section>`;
}

function mapPanel() {
  const legend = [['minimal', '<1%'], ['low', '1–5%'], ['elevated', '5–20%'], ['high', '20–50%'], ['critical', '≥50%']]
    .map(([cls, label]) => `<span><i class="${cls}"></i>${label}</span>`).join('');
  return `<section class="panel" aria-labelledby="map-heading">
    <div class="panel-heading"><div><h2 id="map-heading">${t().mapTitle}</h2><p>${escape(typeLabel(typeEntry(eventType)))} · ${escape(horizonLabel(horizon))}</p></div></div>
    <div class="map-stage" id="map"><svg viewBox="0 0 900 440" role="img" tabindex="0" aria-label="${t().mapTitle}"><g></g></svg><div class="tooltip" hidden></div>
      <div class="map-controls"><button data-map="in" aria-label="Zoom in">+</button><button data-map="out" aria-label="Zoom out">−</button><button data-map="reset" aria-label="Reset">↺</button></div></div>
    <div class="map-legend">${legend}${isConflict(eventType) ? `<span><i class="active"></i>${t().legendActive}</span>` : ''}<span><i></i>${t().noData}</span></div>
    <div class="map-credit">Natural Earth / World Atlas</div>
  </section>`;
}

function ranking() {
  const rows = (snapshot?.countries ?? [])
    .filter((c) => c.risks[eventType])
    .map((c) => ({ c, r: c.risks[eventType] }))
    .sort((a, b) => b.r.horizons[horizon].p - a.r.horizons[horizon].p)
    .slice(0, 15);
  return `<section class="panel"><div class="panel-heading"><div><h2>${t().top}</h2><p>${escape(typeLabel(typeEntry(eventType)))} · ${escape(horizonLabel(horizon))}</p></div></div>
    <div class="watchlist">${rows.map(({ c, r }, i) => `<button type="button" data-select="${c.iso3}">
      <span class="rank">${String(i + 1).padStart(2, '0')}</span>
      <span>${escape(countryName(c))}${r.active ? ' ' + ongoingTag() : ''}</span>
      <span class="ranked-value">${cell(r, horizon)}</span><span aria-hidden="true">›</span></button>`).join('')}</div></section>`;
}

function countrySummary() {
  const country = byIso().get(selected);
  const types = (snapshot?.event_types ?? []).filter((e) => e.available);
  const rows = types.map((entry) => {
    const risk = country?.risks[entry.key];
    if (!risk) return '';
    return `<div class="risk-row"><div><strong>${escape(typeLabel(entry))}</strong>${risk.active ? ' ' + ongoingTag() : ''}
      <small>${escape(questionText(entry.key, risk))}</small></div><div class="risk-value">${cell(risk, horizon)}</div></div>`;
  }).join('');
  return `<section class="panel country-panel" id="country-panel" aria-labelledby="country-heading">
    <div class="panel-heading"><div><span class="eyebrow">${t().navCountry.toUpperCase()}</span><h2 id="country-heading">${escape(countryName(country, selected))}</h2><p>${escape(horizonLabel(horizon))}</p></div></div>
    <label class="field country-field">${t().selectCountry}<select data-field="country">${countryOptions()}</select></label>
    <div class="country-section">${rows || state(t().noData)}</div>
    <div class="country-section"><a href="#country">${t().details} →</a></div>
  </section>`;
}

function countryOptions() {
  return (snapshot?.countries ?? [])
    .map((c) => [c.iso3, countryName(c)] as const)
    .sort((a, b) => a[1].localeCompare(b[1], lang))
    .map(([iso3, label]) => `<option value="${iso3}"${iso3 === selected ? ' selected' : ''}>${escape(label)}</option>`).join('');
}

function overview() {
  return `<div class="page-heading"><h1>${t().overviewTitle}</h1><p>${t().overviewLead}</p></div>
    <div class="notice">${t().baselineNotice}</div>
    ${metrics()}
    ${controls()}
    <div class="overview-grid">${mapPanel()}${countrySummary()}${ranking()}</div>`;
}

function countryPage() {
  const country = byIso().get(selected);
  const horizons = snapshot?.horizons ?? [];
  const types = snapshot?.event_types ?? [];
  const rows = types.map((entry) => {
    const risk = country?.risks[entry.key];
    const head = `<th scope="row"><strong>${escape(typeLabel(entry))}</strong>${risk?.active ? ' ' + ongoingTag() : ''}</th>`;
    if (!entry.modeled || !entry.available || !risk) {
      return `<tr class="muted-row">${head}<td colspan="${horizons.length}">${!entry.modeled ? t().notModeled : t().unavailable}</td></tr>`;
    }
    return `<tr>${head}${horizons.map((h) => `<td>${cell(risk, h.key)}</td>`).join('')}</tr>
      <tr class="note-row"><td colspan="${horizons.length + 1}">${escape(questionText(entry.key, risk))}
        ${escape(t().basis(risk.basis.exposure_years, risk.basis.event_years, risk.basis.last_event_year))}
        ${t().stateAsOf} ${risk.state_as_of}. ${t().confidence}: ${confidenceText(risk.confidence)}.
        <details><summary>${t().definition}</summary>${escape(lang === 'ru' ? entry.resolution_ru : entry.resolution_en)}</details></td></tr>`;
  }).join('');
  return `<div class="page-heading"><h1>${escape(countryName(country, selected))}</h1><p>${t().probHint}</p></div>
    <label class="field narrow">${t().selectCountry}<select data-field="country">${countryOptions()}</select></label>
    <section class="panel"><div class="table-wrap"><table class="risk-table">
      <thead><tr><th scope="col">${t().eventType}</th>${horizons.map((h) => `<th scope="col">${escape(lang === 'ru' ? h.label_ru : h.label_en)}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody></table></div></section>
    <div class="notice">${t().baselineNotice}</div>`;
}

function changeList(changes: Change[]) {
  if (!changes.length) return state(t().noChanges);
  const countries = byIso();
  return `<ul class="changes">${changes.slice(0, 200).map((change) => {
    const name = countryName(countries.get(change.iso3), change.iso3);
    const type = typeLabel(typeEntry(change.event_type));
    if (change.kind === 'state_change') {
      return `<li><button type="button" data-select="${change.iso3}">${escape(name)}</button> · ${escape(type)} · <strong>${change.to === 'active_at_end' ? t().stateStarted : t().stateEnded}</strong></li>`;
    }
    const delta = change.delta ?? 0;
    return `<li><button type="button" data-select="${change.iso3}">${escape(name)}</button> · ${escape(type)} · ${escape(horizonLabel(change.horizon ?? ''))}:
      ${percent(Number(change.from), lang)} → <strong>${percent(Number(change.to), lang)}</strong>
      <span class="${delta > 0 ? 'up' : 'down'}">${delta > 0 ? '▲' : '▼'} ${(Math.abs(delta) * 100).toFixed(1).replace('.', lang === 'ru' ? ',' : '.')} ${lang === 'ru' ? 'п.п.' : 'pp'}</span></li>`;
  }).join('')}</ul>`;
}

function changesPage() {
  if (!snapshot) return '';
  const visit = previousVisit
    ? `<p class="muted">${dateTime(previousVisit.generated_at)} → ${dateTime(snapshot.generated_at)}</p>${changeList(changesSince(previousVisit, snapshot))}`
    : state(t().firstVisitNote);
  const data = snapshot.previous_generated_at
    ? `<p class="muted">${dateTime(snapshot.previous_generated_at)} → ${dateTime(snapshot.generated_at)}</p>${changeList(snapshot.changes)}`
    : state(t().firstSnapshot);
  return `<div class="page-heading"><h1>${t().changesTitle}</h1></div>
    <div class="two-col"><section class="panel"><div class="panel-heading"><h2>${t().changesVisit}</h2></div><div class="section-body">${visit}</div></section>
    <section class="panel"><div class="panel-heading"><h2>${t().changesData}</h2></div><div class="section-body">${data}</div></section></div>`;
}

function methodPage() {
  if (!snapshot) return '';
  const sources = snapshot.sources.map((s) => `<tr><td>${escape(s.name)}</td><td class="${s.status === 'ok' ? 'low' : 'high'}">${s.status === 'ok' ? t().ok : t().failed}</td>
    <td>${s.version ? escape(t().version + ' ' + s.version) : ''}${s.retrieved_at ? '<br><small>' + dateTime(s.retrieved_at) + '</small>' : ''}</td>
    <td>${s.url ? `<a href="${escape(s.url)}" rel="noreferrer">link</a>` : ''}</td></tr>`).join('');
  const types = snapshot.event_types.map((e) => `<tr><td>${escape(typeLabel(e))}</td>
    <td>${!e.modeled ? t().notModeled : e.available ? t().ok : t().unavailable}</td>
    <td>${e.data_window ? `${t().window}: ${e.data_window[0]}–${e.data_window[1]}` : ''}</td>
    <td><small>${escape(lang === 'ru' ? e.resolution_ru : e.resolution_en)}</small></td></tr>`).join('');
  return `<div class="page-heading"><h1>${t().methodTitle}</h1></div>
    <section class="panel"><div class="panel-heading"><h2>${t().method}</h2></div><div class="section-body">
      <p>${escape(lang === 'ru' ? snapshot.method.description_ru : snapshot.method.description_en)}</p>
      <dl><dt>${t().calibration}</dt><dd>${t().notCalibrated}</dd><dt>${t().interval}</dt><dd>${escape(snapshot.method.interval)}</dd><dt>ID</dt><dd>${escape(snapshot.method.name)}</dd></dl></div></section>
    <section class="panel"><div class="panel-heading"><h2>${t().sources}</h2></div><div class="table-wrap"><table class="risk-table"><tbody>${sources}</tbody></table></div></section>
    <section class="panel"><div class="panel-heading"><h2>${t().eventTypes}</h2></div><div class="table-wrap"><table class="risk-table"><tbody>${types}</tbody></table></div></section>`;
}

function body(page: Page) {
  if (loadError) return state(t().loadError, `<button data-retry>${t().retry}</button>`, 'alert');
  if (!snapshot) return state(t().loading);
  if (page === 'country') return countryPage();
  if (page === 'changes') return changesPage();
  if (page === 'method') return methodPage();
  return overview();
}

function render() {
  const page = currentPage();
  document.documentElement.lang = lang;
  regionNames = undefined;
  root.innerHTML = `<aside class="sidebar">
      <a class="brand" href="#overview"><span class="brand-icon">◈</span><span>${t().title}<small>${t().subtitle.toUpperCase()}</small></span></a>
      <nav aria-label="Primary">${pages.map(([key, label, icon]) =>
        `<a href="#${key}"${key === page ? ' aria-current="page"' : ''}><span aria-hidden="true">${icon}</span>${t()[label]}</a>`).join('')}</nav>
      <div class="sidebar-footer">${snapshot ? dateTime(snapshot.generated_at) : ''}</div>
    </aside>
    <div><header class="topbar"><span>${t().subtitle}</span><div><button type="button" data-lang>${t().langSwitch}</button></div></header>
    <main id="workspace" tabindex="-1">${body(page)}</main></div>`;
  const map = root.querySelector<HTMLElement>('#map');
  if (map && snapshot) {
    const shapes = shapeToIso();
    const countries = byIso();
    updateMapSelection = drawMap(map, [...shapes].find(([, iso]) => iso === selected)?.[0] ?? '',
      (key) => {
        const risk = countries.get(shapes.get(key) ?? '')?.risks[eventType];
        if (!risk) return '';
        return risk.question === 'active_at_end' ? 'active' : band(risk.horizons[horizon].p);
      },
      (key, fallback) => {
        const country = countries.get(shapes.get(key) ?? '');
        const risk = country?.risks[eventType];
        const label = country ? countryName(country) : fallback;
        if (!risk) return label + ' · ' + t().noData;
        const v = risk.horizons[horizon];
        return `${label} · ${percent(v.p, lang)} (${percent(v.low, lang)}–${percent(v.high, lang)})${risk.active ? ' · ' + t().ongoing : ''}`;
      },
      (key) => { const iso = shapes.get(key); if (iso) selectCountry(iso); });
  }
}

function selectCountry(iso3: string) {
  selected = iso3;
  store('geointel.country', iso3);
  const panel = root.querySelector<HTMLElement>('#country-panel');
  if (panel && currentPage() === 'overview') {
    panel.outerHTML = countrySummary();
    const key = [...shapeToIso()].find(([, iso]) => iso === iso3)?.[0];
    if (key) updateMapSelection?.(key);
  } else {
    render();
  }
}

root.addEventListener('click', (event) => {
  const target = event.target as HTMLElement;
  const select = target.closest<HTMLElement>('[data-select]')?.dataset.select;
  if (select) { selectCountry(select); if (currentPage() === 'changes') location.hash = '#country'; return; }
  const h = target.closest<HTMLElement>('[data-horizon]')?.dataset.horizon as HorizonKey | undefined;
  if (h) { horizon = h; store('geointel.horizon', h); render(); return; }
  if (target.closest('[data-lang]')) { lang = lang === 'ru' ? 'en' : 'ru'; store('geointel.lang', lang); render(); return; }
  if (target.closest('[data-retry]')) void start();
});

root.addEventListener('change', (event) => {
  const field = event.target as HTMLSelectElement;
  if (field.dataset.field === 'type') { eventType = field.value; store('geointel.type', eventType); render(); }
  if (field.dataset.field === 'country') selectCountry(field.value);
});

window.addEventListener('hashchange', () => { render(); root.querySelector<HTMLElement>('main')?.focus(); });

async function start() {
  loadError = false;
  render();
  try {
    snapshot = await loadSnapshot();
    previousVisit = readVisit();
    if (previousVisit?.generated_at === snapshot.generated_at) {
      // Same data as last time: keep comparing against the visit before that.
      previousVisit = JSON.parse(stored('geointel.prevVisit.v1') ?? 'null') ?? undefined;
    } else if (previousVisit) {
      store('geointel.prevVisit.v1', JSON.stringify(previousVisit));
    }
    writeVisit(snapshot);
    if (!typeEntry(eventType)?.available) eventType = snapshot.event_types.find((e) => e.available)?.key ?? eventType;
    if (!byIso().has(selected)) selected = snapshot.countries[0]?.iso3 ?? '';
  } catch {
    loadError = true;
  }
  render();
}

void start();
