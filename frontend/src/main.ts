import './style.css';
import { band, fixtureDate, fixtures, loadForecasts, months, provenance } from './data';
import type { Fixture, Forecast } from './data';
import { countries, countryNames, drawMap } from './map';

const pages = [
  ['overview', 'Global Overview', '◈'],
  ['country', 'Country Intelligence', '◎'],
  ['risk', 'Risk Monitoring', '▥'],
  ['forecasts', 'Forecasts', '⌁'],
  ['briefings', 'Intelligence Briefings', '▤'],
  ['analyst', 'AI Analyst', '✧'],
] as const;
type Page = typeof pages[number][0];
type Mode = 'demo' | 'api';

const root = document.querySelector<HTMLElement>('#app')!;
let mode: Mode = new URLSearchParams(location.search).get('mode') === 'api' ? 'api' : 'demo';
let country = '804';
let riskCountry = '';
let period = 6;
let briefCountry = '';
let briefRegion = '';
let briefSince = '';
let abandonForecasts: AbortController | undefined;
let updateMapSelection: ((id: string) => void) | undefined;
const messages: { question: string; country: string }[] = [];

const available = () => mode === 'demo' ? fixtures : [];
const name = (id: string) => countryNames.get(id) ?? 'Unknown geography';
const score = (item: Fixture) => item.history.at(-1)!;
const sorted = () => [...available()].sort((a, b) => score(b) - score(a));
const currentPage = (): Page => pages.find(([key]) => '#' + key === location.hash)?.[0] ?? 'overview';
const date = (value: string) => new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC',
}).format(new Date(value));
const escape = (value: string) => value.replace(/[&<>"']/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[character]!));
const signed = (value: number) => (value > 0 ? '+' : '') + value;
const synthetic = '<span class="tag synthetic">Synthetic</span>';
const state = (headline: string, description: string, role = 'status') =>
  '<div class="state" role="' + role + '"><strong>' + headline + '</strong><p>' + description + '</p></div>';
const unavailable = (subject: string) => state(subject + ' unavailable', 'Current GEOINTEL API contracts do not provide this view.');
const options = (items: readonly (readonly [string, string])[], selected: string) => items
  .map(([value, label]) => '<option value="' + escape(value) + '"' + (value === selected ? ' selected' : '') + '>' + escape(label) + '</option>').join('');
const countryOptions = (selected: string, all = false) => options(all ? [['', 'All countries'], ...countries] : countries, selected);
const list = (items: string[]) => items.length
  ? '<ul>' + items.map((item) => '<li>' + escape(item) + '</li>').join('') + '</ul>' : '<p class="muted">Unavailable</p>';

function chart(values: number[], labels: string[], description: string) {
  const points = values.map((value, i) => [28 + i * 284 / (values.length - 1), 104 - value * .86]);
  return `<div class="chart"><svg viewBox="0 0 340 130" role="img" aria-label="${escape(description + ': ' + values.map((v, i) => labels[i] + ' ' + v).join(', ') + ' on a 0–100 scale')}">
    <defs><linearGradient id="trend-fill" x2="0" y2="1"><stop stop-color="#62aaff" stop-opacity=".28"/><stop offset="1" stop-color="#62aaff" stop-opacity="0"/></linearGradient></defs>
    ${[0, 50, 100].map((value) => `<line x1="28" x2="312" y1="${104-value*.86}" y2="${104-value*.86}" class="chart-grid"/><text x="21" y="${107-value*.86}" text-anchor="end">${value}</text>`).join('')}
    <polygon fill="url(#trend-fill)" points="28,104 ${points.join(' ')} 312,104"/>
    <polyline points="${points.join(' ')}" class="trend-line"/>
    ${points.map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="3"/><text x="${x}" y="123" text-anchor="middle">${labels[i]}</text>`).join('')}
  </svg></div>`;
}

function scoreDefinition() {
  return 'Illustrative index from 0–100 in the synthetic fixture. Bands: low 0–44, elevated 45–69, high 70–100.';
}

function countryPanel() {
  const item = available().find((entry) => entry.id === country);
  return `<section class="panel country-panel" aria-labelledby="country-heading">
    <div class="panel-heading"><div><span class="eyebrow">COUNTRY INTELLIGENCE</span><h2 id="country-heading">${escape(name(country))}</h2><p>${item?.region ?? 'Country / territory'} · ISO numeric ${escape(country)}</p></div>${item ? synthetic : ''}</div>
    <label class="field country-field">Select country<select data-field="country">${countryOptions(country)}</select></label>
    ${item ? `<div class="score-card"><div><span class="eyebrow">SYNTHETIC RISK INDEX</span><strong>${score(item)}<small> / 100</small></strong></div><span class="tag ${band(score(item)).toLowerCase()}">${band(score(item))}</span></div>
      <details class="definition"><summary>Index definition</summary><p>${scoreDefinition()} The index has no probability interpretation.</p></details>
      <div class="country-section"><h3>Synthetic historical trend</h3>${chart(item.history, months, 'Synthetic historical trend')}</div>
      <div class="country-section"><h3>Synthetic recent events</h3>${eventList([item], 6, false)}</div>
      <div class="country-section"><h3>Forecast information</h3>${item.projection ? `<p>Synthetic 1-month index projection: <strong>${item.projection.low}–${item.projection.high}</strong>. Illustrative bounds. Statistical confidence unavailable.</p>` : state('Forecast unavailable', 'This fixture has no projection.')}</div>
      <div class="country-section"><h3>Source and freshness</h3><p><a href="#fixture-source" data-source>[${provenance}]</a><br>Fixture snapshot · ${date(fixtureDate)} UTC<br>Real-world source freshness unavailable.</p></div>`
      : mode === 'demo' ? state('Country data unavailable', 'This geography has no synthetic indicators, events, or forecast in the fixture.') : unavailable('Country indicators, events and forecasts')}
    </section>`;
}

function eventList(items: Fixture[], window: number, showNames = true) {
  const events = items.flatMap((item) => item.events.filter((event) => window === 6 || event.date >= '2025-02-01')
    .map((event) => ({ ...event, id: item.id }))).sort((a, b) => b.date.localeCompare(a.date));
  return events.length ? `<ol class="timeline">${events.map((event) => `<li><time datetime="${event.date}">${date(event.date)}</time><span>${showNames ? '<strong>' + escape(name(event.id)) + '</strong> · ' : ''}${event.title}</span></li>`).join('')}</ol>`
    : state('No events', 'No synthetic events match the selected country and period.');
}

function riskMap() {
  return `<section class="panel map-panel" aria-labelledby="map-title">
    <div class="panel-heading"><div><h2 id="map-title">Geographic risk distribution</h2><p>${mode === 'demo' ? 'Synthetic conflict-risk index · 01 Mar 2025' : 'Country risk unavailable from the current API'}</p></div></div>
    <div class="map-stage" id="map">
      <svg viewBox="0 0 900 440" tabindex="0" role="img" aria-label="World country boundaries. Zoom with the map controls and pan with arrow keys. Use Select country for keyboard selection."><g></g></svg>
      <div class="tooltip" aria-hidden="true" hidden></div>
      <div class="map-controls" aria-label="Map zoom controls">
        <button data-map="in" aria-label="Zoom in">+</button><button data-map="out" aria-label="Zoom out">−</button><button data-map="reset" aria-label="Reset map">↺</button>
      </div>
    </div>
    <div class="map-legend" aria-label="Risk legend">
      ${mode === 'demo' ? '<span><i class="low"></i>Low · 0–44</span><span><i class="elevated"></i>Elevated · 45–69</span><span><i class="high"></i>High · 70–100</span>' : ''}<span><i></i>Unavailable</span>
    </div>
    <div class="map-credit">Boundaries · Natural Earth / World Atlas</div>
  </section>`;
}

function watchlist() {
  const items = sorted().slice(0, 5);
  return `<section class="panel"><div class="panel-heading"><div><h2>Highest index readings</h2><p>Synthetic readings on the fixture snapshot date</p></div>${synthetic}</div>
    <div class="watchlist">${items.map((item, index) => `<button data-pick="${item.id}"><span class="rank">${String(index + 1).padStart(2, '0')}</span>
      <span><strong>${escape(name(item.id))}</strong><small>${item.region}</small></span><b class="${band(score(item)).toLowerCase()}">${score(item)}</b><span aria-hidden="true">›</span></button>`).join('')}</div></section>`;
}

function overview() {
  const items = available();
  return `<div class="metrics">
    <div><span>COUNTRIES WITH READINGS</span><strong>${items.length || '—'}</strong><small>${items.length ? 'Synthetic fixture coverage' : 'Coverage unavailable'}</small></div>
    <div><span>HIGH INDEX READINGS</span><strong>${items.length ? items.filter((item) => band(score(item)) === 'High').length : '—'}</strong><small>${items.length ? '70–100 on the synthetic index' : 'Index unavailable'}</small></div>
    <div><span>FIXTURE SNAPSHOT</span><strong>${items.length ? '01 Mar 2025' : '—'}</strong><small>${items.length ? 'Fixed demonstration snapshot · UTC' : 'API mode'}</small></div>
  </div>
  <div class="overview-grid">${riskMap()}<div id="country-panel" aria-live="polite">${countryPanel()}</div>${items.length ? watchlist() : ''}</div>`;
}

function riskView() {
  if (mode === 'api') return unavailable('Risk distribution, trends and event timeline');
  const items = sorted().filter((item) => !riskCountry || item.id === riskCountry);
  const trend = items.length ? months.map((_, index) => Math.round(items.reduce((sum, item) => sum + item.history[index], 0) / items.length)) : [];
  return `<div class="filters"><label class="field">Country<select data-field="risk-country">${countryOptions(riskCountry, true)}</select></label>
  <label class="field">Snapshot period<select data-field="period">${options([['6', 'Oct 2024 – Mar 2025'], ['2', 'Feb – Mar 2025']], String(period))}</select></label>${synthetic}</div>
  ${items.length ? `<div class="two-col">
    <section class="panel"><div class="panel-heading"><div><h2>Geographic distribution</h2><p>Snapshot readings by country · 01 Mar 2025</p></div></div><div class="section-body">
      ${items.map((item) => `<div class="bar-row"><span>${escape(name(item.id))}</span><meter min="0" max="100" value="${score(item)}" class="${band(score(item)).toLowerCase()}" aria-label="${escape(name(item.id))} synthetic risk index"></meter><strong>${score(item)}</strong></div>`).join('')}
      <p class="muted">${scoreDefinition()}</p></div></section>
    <section class="panel"><div class="panel-heading"><div><h2>Synthetic index trend</h2><p>${riskCountry ? escape(name(riskCountry)) : 'Unweighted mean across fixture countries'}</p></div></div><div class="section-body">${chart(trend.slice(-period), months.slice(-period), 'Synthetic index trend')}
      <h3>Escalation indicators</h3><p class="muted">Change in synthetic index points across the selected period.</p>
      ${items.map((item) => `<div class="delta"><span>${escape(name(item.id))}</span><strong>${signed(score(item) - item.history[6-period])} pts</strong></div>`).join('')}</div></section>
  </div><section class="panel"><div class="panel-heading"><div><h2>Synthetic event timeline</h2><p>${provenance} · ${date(fixtureDate)} UTC · Real-world freshness unavailable</p></div></div><div class="section-body">${eventList(items, period)}</div></section>`
  : state('Country data unavailable', 'This country has no synthetic risk readings or events.')}`;
}

function briefings() {
  if (mode === 'api') return unavailable('Intelligence briefings');
  const regions = [...new Set(fixtures.map((item) => item.region))].sort();
  const items = sorted().filter((item) => (!briefCountry || item.id === briefCountry)
    && (!briefRegion || item.region === briefRegion) && (!briefSince || fixtureDate >= briefSince));
  return `<div class="filters">
    <label class="field">Country<select data-field="brief-country">${countryOptions(briefCountry, true)}</select></label>
    <label class="field">Region<select data-field="brief-region">${options([['', 'All regions'], ...regions.map((region) => [region, region] as const)], briefRegion)}</select></label>
    <label class="field">Published on or after<input type="date" data-field="brief-since" value="${escape(briefSince)}"></label>${synthetic}
  </div><div class="stack">${items.length ? items.map((item) => `<article class="panel briefing">
    <details><summary><span><strong>${escape(name(item.id))} · Synthetic country briefing</strong><small>${item.region} · ${date(fixtureDate)} UTC</small></span></summary>
      <div class="section-body"><h3>Simulated observations</h3>${eventList([item], 6, false)}
      <h3>Synthetic forecast example</h3><p>${item.projection ? `1-month index projection: ${item.projection.low}–${item.projection.high}. Illustrative bounds. Confidence unavailable.` : 'Forecast unavailable in this fixture.'}</p>
      <h3>Demonstration interpretation</h3><p>The synthetic score changed by ${signed(score(item) - item.history[0])} points over the fixture period. This description applies only to the synthetic series.</p>
      <h3>Evidence and provenance</h3><p><a href="#fixture-source" data-source>[${provenance}]</a> · snapshot ${date(fixtureDate)} UTC</p></div>
    </details></article>`).join('') : state('No matching briefings', 'Adjust the country, region, or publication date.')}</div>`;
}

function forecastCard(row: Forecast) {
  const range = row.probability_low === null || row.probability_high === null ? 'Unavailable' :
    new Intl.NumberFormat('en', { style: 'percent', maximumFractionDigits: 2 }).formatRange(row.probability_low, row.probability_high);
  return `<article class="panel section-body forecast"><span class="tag">API forecast</span><h2>${escape(row.question)}</h2>
    <p class="muted">${escape(row.conflict_type)} · ${row.horizon_months} month(s) · Version ${row.version}</p>
    <dl><dt>Probability interval</dt><dd>${range}</dd><dt>Reported confidence</dt><dd>${escape(row.confidence)}</dd>
    <dt>Generated</dt><dd><time datetime="${escape(row.created_at)}">${escape(row.created_at)}</time></dd>
    <dt>Provenance</dt><dd>Analysis run ${escape(row.analysis_run_id)} · Forecast ${escape(row.id)}</dd></dl>
    <p>${escape(row.rationale)}</p><details><summary>Evidence and uncertainty</summary>
      <h3>Evidence for</h3>${list(row.evidence_for)}<h3>Evidence against</h3>${list(row.evidence_against)}
      <h3>Unknowns</h3>${list(row.unknowns)}<h3>Resolution criteria</h3>${list(row.resolution_criteria)}
      <h3>Change conditions</h3>${list(row.change_conditions)}
    </details></article>`;
}

function forecasts() {
  if (mode === 'api') return '<div id="forecast-results" class="stack" aria-live="polite"></div>';
  return `<div class="notice">These synthetic projections illustrate the index display. They have no probability or calibrated confidence.</div>
    <div class="two-col">${sorted().filter((item) => item.projection).map((item) => `<article class="panel section-body forecast">${synthetic}
      <h2>${escape(name(item.id))}</h2><p>${item.region} · 1-month horizon</p><dl><dt>Illustrative index interval</dt><dd>${item.projection!.low}–${item.projection!.high} / 100</dd>
      <dt>Statistical confidence</dt><dd>Unavailable</dd><dt>Snapshot</dt><dd>${date(fixtureDate)} UTC</dd></dl>
      <a href="#fixture-source" data-source>[${provenance}]</a></article>`).join('')}</div>`;
}

const prompts = ['Summarize the synthetic index', 'List synthetic recent events', 'Describe forecast uncertainty'];

function analystReply(id: string, question: string) {
  const item = fixtures.find((entry) => entry.id === id);
  if (!item) return state('Country data unavailable', 'The fixture has no records for this geography.');
  let content: string;
  if (question === prompts[0]) {
    content = `<p>The synthetic index for ${escape(name(id))} is <strong>${score(item)}/100</strong> (${band(score(item)).toLowerCase()}), a change of ${signed(score(item) - item.history[0])} points across the fixture period.</p>`;
  } else if (question === prompts[1]) {
    content = eventList([item], 6, false);
  } else if (question === prompts[2]) {
    content = item.projection ? `<p>The synthetic 1-month interval is ${item.projection.low}–${item.projection.high} index points. Statistical confidence and calibrated uncertainty are unavailable.</p>` : '<p>Projection and uncertainty are unavailable for this country.</p>';
  } else {
    content = '<p>This demonstration has scripted responses for the three suggested questions. Choose one to inspect the selected country fixture.</p>';
  }
  return content + `<p class="muted"><a href="#fixture-source" data-source>[${provenance}]</a> · ${date(fixtureDate)} UTC</p>`;
}

function messagePair(message: typeof messages[number]) {
  return `<div class="message user"><span class="eyebrow">YOU · ${escape(name(message.country))}</span><p>${escape(message.question)}</p></div>
    <div class="message"><span class="eyebrow">SCRIPTED DEMONSTRATION RESPONSE</span>${analystReply(message.country, message.question)}</div>`;
}

function messageHistory() {
  return messages.length ? messages.map(messagePair).join('')
    : '<div data-chat-empty>' + state('Start with a suggested question', 'Choose a country to examine its synthetic data, evidence and forecast uncertainty.') + '</div>';
}

function analyst() {
  if (mode === 'api') return unavailable('AI Analyst conversations');
  return `<section class="panel analyst">
    <div class="panel-heading"><div><h2>Analyst conversation</h2><p>Scripted demonstrations grounded in the local synthetic fixture</p></div>${synthetic}</div>
    <div class="section-body">
      <label class="field">Country context<select data-field="country">${countryOptions(country)}</select></label>
      <div id="history" class="history" role="log" aria-label="Conversation history" tabindex="0">${messageHistory()}</div>
      <div class="prompts">${prompts.map((prompt, index) => `<button type="button" data-prompt="${index}">${prompt}</button>`).join('')}</div>
      <form id="chat-form"><label class="field">Message<input name="question" maxlength="500" required placeholder="Ask about the fixture…"></label><button class="primary" type="submit">Send</button></form>
    </div></section>`;
}

const descriptions: Record<Page, string> = {
  overview: 'Explore country coverage and conflict-risk indicators.',
  country: 'Review geographic context, historical readings and evidence.',
  risk: 'Compare geographic distribution, trends and escalation indicators.',
  forecasts: 'Inspect forecast horizons, confidence and uncertainty.',
  briefings: 'Browse country reports and their supporting evidence.',
  analyst: 'Explore the selected country through a conversational interface.',
};

const views: Record<Page, () => string> = { overview, country: countryPanel, risk: riskView, forecasts, briefings, analyst };

function render() {
  abandonForecasts?.abort();
  updateMapSelection = undefined;
  const page = currentPage();
  const title = pages.find(([key]) => key === page)![1];
  document.title = title + ' | GEOINTEL';
  root.innerHTML = `<aside class="sidebar">
    <a class="brand" href="#overview"><span class="brand-icon" aria-hidden="true">◈</span><span>GEOINTEL<small>INTELLIGENCE WORKSTATION</small></span></a>
    <nav aria-label="Global navigation">${pages.map(([key, label, icon]) => `<a href="#${key}" ${key === page ? 'aria-current="page"' : ''}><span aria-hidden="true">${icon}</span>${label}</a>`).join('')}</nav>
    <div class="sidebar-footer"><span class="status-dot"></span> Frontend v0.1</div>
  </aside><div class="shell">
    <header class="topbar"><span>Intelligence workspace</span><div><span class="status-label"><i></i>${mode === 'demo' ? 'Synthetic data' : 'Backend data only'}</span>
      <label class="mode">Data mode<select data-field="mode">${options([['demo', 'Demo mode'], ['api', 'API mode']], mode)}</select></label></div></header>
    <main id="workspace" tabindex="-1"><header class="page-heading"><h1>${title}</h1><p>${descriptions[page]}</p></header>
      <div class="notice ${mode === 'api' ? 'api' : ''}"><strong>${mode === 'demo' ? 'Demonstration environment' : 'API environment'}</strong><span>${mode === 'demo' ? 'All displayed indicators, events and projections are synthetic.' : 'Forecasts use the configured backend. Other data depends on compatible API contracts.'}</span></div>
      ${views[page]()}
    </main></div>
    <dialog id="fixture-source" aria-labelledby="source-title">
      <form method="dialog"><button aria-label="Close source details">×</button></form>
      <h2 id="source-title">${provenance}</h2><p>Fixed synthetic snapshot dated ${date(fixtureDate)} UTC. The frontend fixture supplies illustrative readings, event descriptions and index projections. It has no external sources or live refresh.</p>
    </dialog>`;
  const map = root.querySelector<HTMLElement>('#map');
  if (map) updateMapSelection = drawMap(map, country, new Map(available().map((item) => [item.id, score(item)])), selectCountry);
  if (page === 'forecasts' && mode === 'api') void renderApiForecasts();
}

async function renderApiForecasts() {
  const node = root.querySelector<HTMLElement>('#forecast-results')!;
  const controller = new AbortController();
  abandonForecasts = controller;
  node.innerHTML = state('Loading forecasts', 'Requesting records from the configured GEOINTEL API.');
  try {
    const rows = await loadForecasts(AbortSignal.any([controller.signal, AbortSignal.timeout(12000)]));
    if (!controller.signal.aborted) node.innerHTML = rows.length ? rows.map(forecastCard).join('') : state('No forecasts', 'The backend returned no forecast records.');
  } catch {
    if (!controller.signal.aborted) node.innerHTML = state('Forecast API unavailable', 'The request failed or the response was invalid. <button data-retry>Retry</button>', 'alert');
  }
}

function selectCountry(id: string) {
  if (!countryNames.has(id)) return;
  country = id;
  const panel = root.querySelector('#country-panel');
  if (panel) {
    const restoreFocus = panel.contains(document.activeElement);
    panel.innerHTML = countryPanel();
    updateMapSelection?.(id);
    if (restoreFocus) panel.querySelector('select')?.focus();
  } else if (currentPage() === 'country') {
    render();
    root.querySelector<HTMLElement>('[data-field="country"]')?.focus();
  }
}

function sendMessage(question: string) {
  question = question.trim();
  if (!question || mode !== 'demo' || currentPage() !== 'analyst') return;
  messages.push({ question, country });
  const history = root.querySelector<HTMLElement>('#history')!;
  history.querySelector('[data-chat-empty]')?.remove();
  history.insertAdjacentHTML('beforeend', messagePair({ question, country }));
  history.scrollTop = history.scrollHeight;
}

root.addEventListener('click', (event) => {
  const control = (event.target as Element).closest<HTMLElement>('[data-pick], [data-source], [data-prompt], [data-retry]');
  if (!control) return;
  if (control.dataset.pick) {
    selectCountry(control.dataset.pick);
    root.querySelector<HTMLSelectElement>('#country-panel select')?.focus();
  }
  if (control.hasAttribute('data-source')) {
    event.preventDefault();
    root.querySelector<HTMLDialogElement>('dialog')?.showModal();
  }
  if (control.dataset.prompt !== undefined) sendMessage(prompts[Number(control.dataset.prompt)]);
  if (control.hasAttribute('data-retry')) void renderApiForecasts();
});

root.addEventListener('change', (event) => {
  const target = event.target as HTMLSelectElement | HTMLInputElement;
  const field = target.dataset.field;
  if (!field) return;
  if (field === 'country') { selectCountry(target.value); return; }
  if (field === 'mode') {
    mode = target.value === 'api' ? 'api' : 'demo';
    const url = new URL(location.href);
    if (mode === 'api') url.searchParams.set('mode', 'api');
    else url.searchParams.delete('mode');
    history.replaceState(null, '', url);
  }
  if (field === 'risk-country') riskCountry = target.value;
  if (field === 'period') period = Number(target.value);
  if (field === 'brief-country') briefCountry = target.value;
  if (field === 'brief-region') briefRegion = target.value;
  if (field === 'brief-since') briefSince = target.value;
  render();
  root.querySelector<HTMLElement>('[data-field="' + field + '"]')?.focus();
});

root.addEventListener('submit', (event) => {
  const form = event.target as HTMLFormElement;
  if (form.id !== 'chat-form') return;
  event.preventDefault();
  const question = new FormData(form).get('question');
  if (typeof question === 'string' && question.trim()) {
    sendMessage(question);
    form.reset();
    form.querySelector('input')?.focus();
  }
});

window.addEventListener('hashchange', () => {
  if (location.hash === '#workspace') return;
  render();
  root.querySelector<HTMLElement>('main')?.focus();
});
document.querySelector('.skip')?.addEventListener('click', (event) => {
  event.preventDefault();
  root.querySelector<HTMLElement>('main')?.focus();
});
render();
