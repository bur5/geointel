import './style.css';
import { band, changesSince, loadHazards, loadSnapshot, percent, readVisit, writeVisit } from './data';
import type {
  Change, CountryEntry, EventTypeEntry, HazardSummary, HorizonKey, Lang, Probability, Risk, Snapshot, VisitMemory,
} from './data';
import { dictionaries } from './i18n';
import { drawCountryMap, drawMap } from './map';

const pages = [
  ['overview', 'navOverview'],
  ['country', 'navCountry'],
  ['changes', 'navChanges'],
  ['assistant', 'navAssistant'],
  ['method', 'navMethod'],
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

function typeSelect() {
  const groups = [['conflict', t().groupConflict], ['natural', t().groupNatural], ['society', t().groupSociety]] as const;
  return groups.map(([group, label]) => {
    const options = (snapshot?.event_types ?? []).filter((e) => (e.group ?? 'conflict') === group).map((entry) => {
      const suffix = !entry.modeled ? ` (${t().notModeled})` : !entry.available ? ` (${t().unavailable})` : '';
      return `<option value="${entry.key}"${entry.key === eventType ? ' selected' : ''}${entry.available ? '' : ' disabled'}>${escape(typeLabel(entry) + suffix)}</option>`;
    }).join('');
    return options ? `<optgroup label="${escape(label)}">${options}</optgroup>` : '';
  }).join('');
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
  const steps = [['minimal', '0'], ['low', '1%'], ['elevated', '5%'], ['high', '20%'], ['critical', '50%']];
  return `<div class="legend">
    <div class="legend-scale"><span class="legend-title">${t().legendProbability}</span>
      <div class="ramp">${steps.map(([cls, label]) => `<span class="${cls}"><i></i><small>${label}</small></span>`).join('')}<span class="ramp-end"><small>100%</small></span></div></div>
    ${(snapshot?.countries ?? []).some((c) => c.risks[eventType]?.active) ? `<span class="legend-key"><i class="swatch-active"></i>${t().legendActive}</span>` : ''}
    <span class="legend-key"><i class="swatch-none"></i>${t().legendNoData}</span>
  </div>`;
}

function mapBlock() {
  return `<section class="map-card" aria-label="${escape(typeLabel(typeEntry(eventType)))}">
    <div class="toolbar">
      <label class="select"><span>${t().eventType}</span><select data-field="type">${typeSelect()}</select></label>
      <div class="toolbar-group"><span>${t().horizon}</span>${horizonSwitch()}</div>
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

function briefPanel() {
  const country = byIso().get(selected);
  const rows = (snapshot?.event_types ?? []).filter((e) => e.available && country?.risks[e.key]).map((e) => {
    const r = country!.risks[e.key];
    return `<li><div class="brief-row-head"><span>${escape(typeLabel(e))}</span>${r.active ? ongoingTag() : ''}</div>${value(r, horizon)}</li>`;
  }).join('');
  return `<aside class="brief" id="country-panel" aria-labelledby="brief-heading">
    <label class="select compact"><span>${t().selectCountry}</span><select data-field="country">${countryOptions()}</select></label>
    <h2 id="brief-heading">${escape(countryName(country, selected))}</h2>
    <div class="brief-summary">${summarySentences(country, horizon)}</div>
    <ul class="brief-list">${rows}</ul>
    <a class="button" href="#country">${t().openCountry}</a>
  </aside>`;
}

function ranking() {
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

function overview() {
  return `<section class="hero"><h1>${t().heroTitle}</h1><p>${t().heroLead}</p>${stats()}</section>
    <div class="explorer">${mapBlock()}${briefPanel()}</div>
    ${ranking()}`;
}

function countryPage() {
  const country = byIso().get(selected);
  const horizons = snapshot?.horizons ?? [];
  const block = (entry: EventTypeEntry) => {
    const risk = country?.risks[entry.key]!;
    return `<article class="risk-block"><div class="risk-head"><h3>${escape(typeLabel(entry))}</h3>${risk.active ? ongoingTag() : ''}</div>
      <p class="question">${escape(questionText(entry.key, risk))}</p>
      <div class="horizon-grid">${horizons.map((h) => `<div><span class="h-label">${escape(lang === 'ru' ? h.label_ru : h.label_en)}</span>${value(risk, h.key, 'lg')}</div>`).join('')}</div>
      <p class="basis">${escape(t().basis(risk.basis.exposure_years, risk.basis.event_years, risk.basis.last_event_year))} ${t().confidence}: ${confidenceText(risk.confidence)}.</p>
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
      <h1>${escape(countryName(country, selected))}</h1>
      <div class="lead-summary"><h2>${t().summaryTitle}</h2>${summarySentences(country, '1y')}</div>
    </section>
    <section class="section hazards" id="hazards" aria-live="polite"><div class="section-head"><h2>${t().hazardsTitle}</h2><p>${t().hazardsLead}</p></div>
      <div class="loading-inline">${t().hazardsLoading}</div></section>
    <section class="section"><div class="section-head"><h2>${t().allRisks}</h2><p>${t().intervalText}</p></div><div class="risk-blocks">${blocks}</div></section>`;
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
    <span class="ev-meta">${e.month ? t().months[e.month - 1] + ' ' : ''}${e.year}${e.severity ? ' · ' + escape(e.severity) : ''}</span></li>`).join('');
  return `<article class="hazard-card"><div class="hazard-head"><h3>${escape(typeLabel(entry))}</h3>
      <p>${escape(t().hazardCount(h.count, h.red, h.first_year, h.last_year))}</p></div>
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
  return `<section class="page-head"><h1>${t().assistantTitle}</h1><p>${t().assistantLead}</p></section>
    ${notice(t().assistantPending, t().assistantPendingText)}`;
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
      <h3>${t().interval}</h3><p>${t().intervalText}</p><h3>${t().calibration}</h3><p>${t().notCalibrated}</p></section>
    <section class="section"><div class="section-head"><h2>${t().eventTypes}</h2></div><table class="table"><tbody>${types}</tbody></table></section>
    <section class="section"><div class="section-head"><h2>${t().sources}</h2></div><table class="table"><tbody>${sources}</tbody></table></section>`;
}

function body(page: Page) {
  if (loadError) return notice(t().loadError, `<button class="button" data-retry>${t().retry}</button>`, 'alert');
  if (!snapshot) return `<div class="loading" role="status">${t().loading}</div>`;
  if (page === 'country') return countryPage();
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
      <div class="topbar-meta">${snapshot ? `<span class="updated">${t().updated} ${formatDate(snapshot.generated_at)}</span>` : ''}<button type="button" class="lang" data-lang>${t().langSwitch}</button></div>
    </header>
    <main id="workspace" tabindex="-1">${body(page)}</main>
    <footer class="footer">${t().brand}. ${t().summaryCaveat} Natural Earth.</footer>`;
  if (page === 'country' && snapshot) void fillHazards(selected);
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
        if (!risk) return label + ': ' + t().legendNoData.toLowerCase();
        const v = risk.horizons[horizon];
        return `${label}: ${pct(v.p)} (${pct(v.low)} – ${pct(v.high)})${risk.active ? ', ' + t().ongoing : ''}`;
      },
      (key) => { const iso = shapes.get(key); if (iso) selectCountry(iso); });
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
  const select = target.closest<HTMLElement>('[data-select]')?.dataset.select;
  if (select) {
    selectCountry(select);
    if (currentPage() !== 'overview') location.hash = '#country';
    else root.querySelector('#country-panel')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return;
  }
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
    if (!typeEntry(eventType)?.available) eventType = snapshot.event_types.find((e) => e.available)?.key ?? eventType;
    if (!byIso().has(selected)) selected = snapshot.countries[0]?.iso3 ?? '';
  } catch {
    loadError = true;
  }
  render();
}

void start();
