// Warning signs: country section, world page and the 2022 backtest chart.
import { band } from './data';
import type { BacktestFile, CountryEntry, Lang, RealBacktestFile, RealCase, Sign, SignalsFile, SignSpec } from './data';
import type { ViewContext } from './views';

const ru = {
  title: 'Признаки и сигналы',
  lead: 'Что сейчас сдвигает риск: признаки подготовки к войне, кризису или беспорядкам. У каждого признака свой коэффициент: во сколько раз он повышает шансы события. Базовая вероятность из истории умножается на эти коэффициенты.',
  none: 'Активных признаков нет — оценки равны базовым.',
  base: 'база',
  withSigns: 'с учётом признаков',
  perYear: 'за год',
  factor: (x: string) => `шансы × ${x}`,
  combo: 'Признаки из трёх и более групп подготовки одновременно — дополнительный коэффициент × 1,5.',
  ongoing: 'Конфликт уже идёт: признаки показаны, но вероятность «будет ли идти» не пересчитывается.',
  normalTitle: (n: number) => `Проверено, отклонений нет (${n})`,
  noDataTitle: (n: number) => `Нет данных (${n})`,
  weak: 'одно сообщение СМИ — вес снижен',
  reports: (n: number) => `${n} сообщ.`,
  source: 'источник',
  risk: {
    interstate_conflict: 'Война с другой страной', internal_armed_conflict: 'Внутренний вооружённый конфликт',
    mass_protest: 'Массовые протесты', political_crisis: 'Политический кризис', economic_crisis: 'Экономический кризис',
    humanitarian_crisis: 'Гуманитарный кризис', coup_attempt: 'Попытка переворота',
  } as Record<string, string>,
  pageTitle: 'Сигналы',
  pageLead: 'Признаки подготовки к войне, кризисам и беспорядкам по всем странам: события в новостях, глушение GPS, изменения рекомендаций МИД, выборы, экономика, проверенный журнал событий и, когда подключены ключи, разбор новостей языковой моделью и спутниковые снимки.',
  mapLegend: 'Во сколько раз признаки повышают шансы (наибольший из рисков)',
  top: 'Где признаков больше всего',
  activeSigns: (n: number) => `${n} актив.`,
  catalogueTitle: 'Признаки и их сила',
  catalogueLead: 'Коэффициенты заданы заранее и одинаковы для всех стран. Автоматические сигналы вместе ограничены диапазоном × 1/3…3, проверенные признаки — до × 500. Коэффициенты — экспертная оценка GeoIntel, не подобраны под конкретный случай.',
  colSign: 'Признак', colGroup: 'Группа', colLr: 'Коэффициент', colApplies: 'К каким рискам', colKind: 'Как собирается',
  auto: 'автоматически', curated: 'журнал и новости',
  sourcesTitle: 'Источники сигналов сегодня',
  ok: 'работает', failed: 'не подключено или ошибка',
  sourceNames: {
    gdelt: 'События в новостях (GDELT)', gpsjam: 'Глушение GPS (GPSJam)', advisories: 'Рекомендации Госдепа США',
    fcdo: 'Рекомендации МИД Великобритании', elections: 'Выборы (Wikidata)', imf: 'Прогноз МВФ', milex: 'Военные расходы (SIPRI)',
    gpr: 'Индекс геополитического риска', newswire: 'Разбор новостей языковой моделью (ключ Claude API)',
    sentinel: 'Спутники Sentinel-1 (ключ Copernicus)', metaculus: 'Metaculus (токен)', markets: 'Polymarket',
    ioda: 'Отключения интернета (IODA)', firms: 'Пожары со спутников (NASA FIRMS)', military: 'Военные самолёты (airplanes.live)',
    zakupki: 'Госзакупки России (zakupki.gov.ru)', media: 'Русскоязычные СМИ: мобилизация и военное положение (GDELT)',
    fx: 'Курсы валют (ExchangeRate-API)', food: 'Цены на продовольствие (ВПП ООН)', telegram: 'Публичные Telegram-каналы',
    coups: 'Перевороты (Cline Center)',
  } as Record<string, string>,
  persistent: 'держится 2 недели — вес × 1,25',
  trendTitle: 'Как менялась сила признаков (90 дней)',
  fxCredit: 'Курсы валют: <a href="https://www.exchangerate-api.com" rel="noreferrer">Rates By Exchange Rate API</a>.',
  btTitle: 'Проверка на истории: вторжение в Украину 2022',
  btLead: 'Тот же набор признаков и коэффициентов, применённый к открытым сообщениям 2021–2022 годов. Линии — вероятность нападения в течение месяца и года на каждую дату.',
  btCaveat: 'Важно: признаки и коэффициенты записаны в 2026 году, когда исход уже известен. Это проверка того, что метод ведёт себя разумно, а не доказательство, что мы бы предсказали. Апрель 2021 года — ложная тревога: тогда наращивание войск не закончилось вторжением.',
  btMonth: 'в течение месяца',
  btYear: 'в течение года',
  btEvents: 'Признаки по датам',
  btSummary: (aug: string, dec: string, feb: string) => `Август 2021 (за полгода): ${aug} за год. Декабрь 2021 (за 3 месяца): ${dec}. 23 февраля 2022: ${feb} в течение месяца.`,
  realTitle: 'Проверка на реальных данных — только автоматические сигналы',
  realLead: 'Архивы событий в новостях (GDELT) и, для 2021–2022 годов, спутниковый радар прогнаны через те же правила, что и на сайте сейчас, без подбора под случай и без ручного журнала. Так видно, что система показала бы сама.',
  realLeadDays: (n: number) => n > 0 ? `сигнал непрерывно держался ${n} дн. до события` : 'устойчивого сигнала перед событием не было',
  realMax: (x: string) => `максимум: шансы × ${x}`,
  realBrier: (a: string, b: string) => `точность (Брайер, меньше — лучше): ${a} против ${b} без сигналов`,
  realElevated: (n: number) => `точек с повышенным риском: ${n}`,
  realMonthly: 'до апреля 2013 года GDELT публикует только месячные файлы — точки раз в месяц',
  realCaveat: 'Автоматические сигналы ловят рост напряжённости в новостях, но не подготовку войск: без журнала и спутников их сила ограничена. Это нижняя граница того, что может система.',
  realNone: 'Проверка на реальных данных ещё выполняется (отдельный процесс, около двух часов).',
};
type Dict = typeof ru;
const en: Dict = {
  title: 'Warning signs',
  lead: 'What is moving the risk now: signs of preparation for war, crisis or unrest. Each sign has a factor: how many times it raises the odds of the event. The historical base probability is multiplied by these factors.',
  none: 'No active signs: estimates equal the base rates.',
  base: 'base',
  withSigns: 'with signs',
  perYear: 'per year',
  factor: (x: string) => `odds × ${x}`,
  combo: 'Signs from three or more preparation groups at once add a further × 1.5.',
  ongoing: 'The conflict is already under way: signs are listed, but the probability that it continues is not recalculated.',
  normalTitle: (n: number) => `Checked, nothing unusual (${n})`,
  noDataTitle: (n: number) => `No data (${n})`,
  weak: 'one media report, weight reduced',
  reports: (n: number) => `${n} reports`,
  source: 'source',
  risk: {
    interstate_conflict: 'War with another state', internal_armed_conflict: 'Internal armed conflict',
    mass_protest: 'Mass protests', political_crisis: 'Political crisis', economic_crisis: 'Economic crisis',
    humanitarian_crisis: 'Humanitarian crisis', coup_attempt: 'Coup attempt',
  },
  pageTitle: 'Signals',
  pageLead: 'Signs of preparation for war, crises and unrest in every country: events in the news, GPS interference, travel-advice changes, elections, the economy, a verified event journal and, once keys are connected, news classified by a language model and satellite imagery.',
  mapLegend: 'How many times signs raise the odds (largest across risks)',
  top: 'Where signs are strongest',
  activeSigns: (n: number) => `${n} active`,
  catalogueTitle: 'Signs and their strength',
  catalogueLead: 'Factors are fixed in advance and the same for every country. Automated signals together are limited to × 1/3–3, verified signs to × 500. Factors are GeoIntel judgements, not fitted to any case.',
  colSign: 'Sign', colGroup: 'Group', colLr: 'Factor', colApplies: 'Risks', colKind: 'Collected',
  auto: 'automatically', curated: 'journal and news',
  sourcesTitle: 'Signal sources today',
  ok: 'working', failed: 'not connected or failed',
  sourceNames: {
    gdelt: 'Events in the news (GDELT)', gpsjam: 'GPS interference (GPSJam)', advisories: 'US travel advisories',
    fcdo: 'UK travel advice', elections: 'Elections (Wikidata)', imf: 'IMF outlook', milex: 'Military spending (SIPRI)',
    gpr: 'Geopolitical risk index', newswire: 'News classified by a language model (Claude API key)',
    sentinel: 'Sentinel-1 satellites (Copernicus key)', metaculus: 'Metaculus (token)', markets: 'Polymarket',
    ioda: 'Internet outages (IODA)', firms: 'Satellite fires (NASA FIRMS)', military: 'Military aircraft (airplanes.live)',
    zakupki: 'Russian public procurement (zakupki.gov.ru)', media: 'Russian-language media: mobilisation and martial law (GDELT)',
    fx: 'Exchange rates (ExchangeRate-API)', food: 'Food prices (WFP)', telegram: 'Public Telegram channels',
    coups: 'Coups (Cline Center)',
  },
  persistent: 'lasting two weeks, weight × 1.25',
  trendTitle: 'How the strength of signs changed (90 days)',
  fxCredit: 'Exchange rates: <a href="https://www.exchangerate-api.com" rel="noreferrer">Rates By Exchange Rate API</a>.',
  btTitle: 'Backtest: the 2022 invasion of Ukraine',
  btLead: 'The same signs and factors applied to public reports from 2021–2022. Lines show the probability of an attack within a month and within a year on each date.',
  btCaveat: 'Important: the signs and factors were written in 2026, with the outcome known. This checks that the method behaves sensibly; it does not prove we would have predicted it. April 2021 is a false alarm: that build-up did not end in an invasion.',
  btMonth: 'within a month',
  btYear: 'within a year',
  btEvents: 'Signs by date',
  btSummary: (aug: string, dec: string, feb: string) => `August 2021 (six months before): ${aug} within a year. December 2021 (three months before): ${dec}. 23 February 2022: ${feb} within a month.`,
  realTitle: 'Backtest on real data: automated signals only',
  realLead: 'Archived news events (GDELT) and, for 2021–2022, satellite radar replayed through the same rules the site uses now, with no case-specific tuning and no hand-written journal. This shows what the system would have shown on its own.',
  realLeadDays: (n: number) => n > 0 ? `the signal held without a break for ${n} days before the event` : 'no lasting signal before the event',
  realMax: (x: string) => `peak: odds × ${x}`,
  realBrier: (a: string, b: string) => `accuracy (Brier, lower is better): ${a} vs ${b} without signals`,
  realElevated: (n: number) => `points with raised risk: ${n}`,
  realMonthly: 'before April 2013 GDELT publishes only monthly files, so points are monthly',
  realCaveat: 'Automated signals pick up rising tension in the news, not troop preparation: without the journal and satellites their strength is limited. This is the lower bound of what the system can do.',
  realNone: 'The real-data backtest is still running (a separate process of about two hours).',
};
const dicts: Record<Lang, Dict> = { ru, en };
export const st = (lang: Lang) => dicts[lang];

type CountrySignalsEx = SignalsFile['countries'][string] & { trend?: { series?: [string, number][] } };

function trendLine(values: number[]) {
  const max = Math.max(...values, 1.5), min = Math.min(...values, 1);
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * 240).toFixed(1)},${(38 - ((v - min) / (max - min || 1)) * 34).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 240 40" aria-hidden="true"><polyline points="${pts}"/></svg>`;
}

const num = (v: number, lang: Lang, d = 1) => v.toFixed(d).replace('.', lang === 'ru' ? ',' : '.');
const fx = (v: number, lang: Lang) => (v >= 10 ? v.toFixed(0) : num(v, lang, v >= 2 ? 1 : 2));
export const factorClass = (f: number | undefined) =>
  f === undefined ? '' : f >= 10 ? 'critical' : f >= 3 ? 'high' : f >= 1.5 ? 'elevated' : f > 1.05 ? 'low' : 'minimal';

function signRow(ctx: ViewContext, sign: Sign, spec: SignSpec | undefined, groups: SignalsFile['groups']) {
  const d = st(ctx.lang);
  const label = spec ? (ctx.lang === 'ru' ? spec.label_ru : spec.label_en) : sign.key;
  const lr = Math.pow(sign.lr, sign.strength ?? 1);
  const group = groups[sign.group]?.[ctx.lang] ?? sign.group;
  const weak = sign.curated === false && (sign.strength ?? 1) < 1;
  return `<li class="sig ${lr >= 1 ? 'up' : 'down'}"><span class="sig-lr">×${fx(lr, ctx.lang)}</span>
    <div><strong>${ctx.esc(label)}</strong> <span class="muted-text small">${ctx.esc(group)}</span>
    <p>${ctx.esc(ctx.lang === 'ru' ? sign.value_ru : sign.value_en)}</p>
    <p class="muted-text small">${sign.date ? ctx.esc(sign.date) + ' · ' : ''}${ctx.esc(sign.source ?? '')}${sign.reports ? ' · ' + d.reports(sign.reports) : ''}${(sign as Sign & { persistent?: boolean }).persistent ? ' · ' + d.persistent : ''}${weak ? ' · ' + d.weak : ''}${sign.url ? ` · <a href="${ctx.esc(sign.url)}" rel="noreferrer">${d.source}</a>` : ''}</p></div></li>`;
}

export function countrySignals(ctx: ViewContext, data: SignalsFile | undefined, country: CountryEntry | undefined) {
  const d = st(ctx.lang);
  const head = `<div class="section-head"><h2>${d.title}</h2><p>${d.lead}</p></div>`;
  if (!data || !country) return head + `<p class="muted-text">…</p>`;
  const entry = data.countries[country.iso3];
  if (!entry) return head + `<p class="muted-text">${d.none}</p>`;
  const specs = new Map(data.catalogue.map((s) => [s.key, s]));
  const active = entry.signs.filter((s) => s.status === 'active');
  const risks = Object.entries(entry.adjusted).sort((a, b) => b[1].factor - a[1].factor).map(([risk, adj]) => {
    const base = country.risks[risk];
    const ongoing = base?.question === 'active_at_end';
    const values = base && adj.horizons && !ongoing
      ? `<span class="adj-base">${d.base} ${ctx.pct(base.horizons['1y'].p)}</span> → <b class="${band(adj.horizons['1y'].p)}-text">${ctx.pct(adj.horizons['1y'].p)}</b> <span class="muted-text small">${d.perYear}</span>`
      : '';
    return `<li><span class="adj-name">${ctx.esc(d.risk[risk] ?? risk)}</span><span class="adj-factor ${factorClass(adj.factor)}">${d.factor(fx(adj.factor, ctx.lang))}</span>${values}${ongoing ? `<span class="muted-text small">${d.ongoing}</span>` : ''}</li>`;
  }).join('');
  const normal = entry.signs.filter((s) => s.status === 'normal');
  const noData = entry.signs.filter((s) => s.status === 'no_data');
  const plain = (list: Sign[]) => `<ul class="plain small">${list.map((s) => {
    const spec = specs.get(s.key);
    return `<li>${ctx.esc(spec ? (ctx.lang === 'ru' ? spec.label_ru : spec.label_en) : s.key)}: <span class="muted-text">${ctx.esc(ctx.lang === 'ru' ? s.value_ru : s.value_en)}</span></li>`;
  }).join('')}</ul>`;
  const combo = Object.values(entry.adjusted).some((a) => a.combo);
  const series = (entry as CountrySignalsEx).trend?.series ?? [];
  const trend = series.length >= 3 ? `<h3 class="sub">${d.trendTitle}</h3>${trendLine(series.map((p) => p[1]))}` : '';
  return head + `<div class="signals-layout">
    <div>${risks ? `<ul class="adjusted">${risks}</ul>` : `<p class="muted-text">${d.none}</p>`}${combo ? `<p class="muted-text small">${d.combo}</p>` : ''}${trend}</div>
    <div>${active.length ? `<ul class="sig-list">${active.sort((a, b) => Math.abs(Math.log(b.lr)) - Math.abs(Math.log(a.lr))).map((s) => signRow(ctx, s, specs.get(s.key), data.groups)).join('')}</ul>` : ''}
      ${normal.length ? `<details><summary>${d.normalTitle(normal.length)}</summary>${plain(normal)}</details>` : ''}
      ${noData.length ? `<details><summary>${d.noDataTitle(noData.length)}</summary>${plain(noData)}</details>` : ''}</div></div>`;
}

export function signalsPage(ctx: ViewContext, data: SignalsFile | undefined) {
  const d = st(ctx.lang);
  const head = `<section class="page-head"><h1>${d.pageTitle}</h1><p>${d.pageLead}</p></section>`;
  if (!data) return head + `<div class="notice" role="status"><strong>${ctx.lang === 'ru' ? 'Данные пока не опубликованы. Они появятся после ближайшего ежедневного обновления.' : 'Not published yet. It will appear after the next daily update.'}</strong></div>`;
  const top = Object.entries(data.countries).filter(([, c]) => c.max_factor > 1.05)
    .sort((a, b) => b[1].max_factor - a[1].max_factor).slice(0, 25);
  const steps: [string, string][] = [['minimal', '1'], ['low', '1,05'], ['elevated', '1,5'], ['high', '3'], ['critical', '10']];
  const rows = data.catalogue.filter((s) => s.key !== 'hazard_alert').map((s) => `<tr><th scope="row">${ctx.esc(ctx.lang === 'ru' ? s.label_ru : s.label_en)}</th>
    <td>${ctx.esc(data.groups[s.group]?.[ctx.lang] ?? s.group)}</td><td class="numcell">×${fx(s.lr, ctx.lang)}</td>
    <td class="small">${s.applies.map((r) => ctx.esc(d.risk[r] ?? r)).join(', ')}</td><td class="small">${s.automated ? d.auto : d.curated}</td></tr>`).join('');
  const sources = Object.keys(d.sourceNames).filter((k) => k in data.status).map((k) =>
    `<li><span class="status ${data.status[k] === 'ok' ? 'ok' : 'failed'}">${data.status[k] === 'ok' ? d.ok : d.failed}</span> ${ctx.esc(d.sourceNames[k])}</li>`).join('');
  return head + `<div class="explorer"><section class="map-card">
      <div class="map-stage" id="signals-map"><svg viewBox="0 0 900 440" role="img" tabindex="0" aria-label="${ctx.esc(d.pageTitle)}"><g></g></svg>
        <div class="tooltip" hidden></div>
        <div class="map-controls"><button data-map="in" aria-label="+">+</button><button data-map="out" aria-label="−">−</button><button data-map="reset" aria-label="⟲">⟲</button></div></div>
      <div class="legend"><div class="legend-scale"><span class="legend-title">${d.mapLegend}</span>
        <div class="ramp">${steps.map(([cls, label]) => `<span class="${cls}"><i></i><small>×${label.replace(',', ctx.lang === 'ru' ? ',' : '.')}</small></span>`).join('')}</div></div></div></section>
    <aside class="brief"><h3 class="aside-title">${d.top}</h3><ul class="mig-list">${top.map(([code, c]) =>
      `<li><button type="button" class="link" data-select="${code}">${ctx.esc(ctx.name(code))}</button><span><b class="${factorClass(c.max_factor)}-text">×${fx(c.max_factor, ctx.lang)}</b> · ${d.activeSigns(c.active)}</span></li>`).join('')}</ul>
      <h3 class="aside-title">${d.sourcesTitle}</h3><ul class="plain small src-status">${sources}</ul><p class="muted-text small">${d.fxCredit}</p></aside></div>
    <section class="section"><div class="section-head"><h2>${d.catalogueTitle}</h2><p>${d.catalogueLead}</p></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${d.colSign}</th><th>${d.colGroup}</th><th>${d.colLr}</th><th>${d.colApplies}</th><th>${d.colKind}</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

export function backtestSection(ctx: ViewContext, data: BacktestFile | undefined) {
  if (!data) return '';
  const d = st(ctx.lang);
  const w = 860, h = 280, left = 46, right = 12, top = 14, bottom = 34;
  const t0 = Date.parse(data.points[0].date), t1 = Date.parse(data.event_date);
  const x = (date: string) => left + ((Date.parse(date) - t0) / (t1 - t0)) * (w - left - right);
  const y = (p: number) => top + (1 - p) * (h - top - bottom);
  const line = (key: 'p1m' | 'p1y') => data.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p[key]).toFixed(1)}`).join('');
  const months = data.points.filter((p) => p.date.endsWith('-01') || Number(p.date.slice(8)) <= 7).filter((p, i, arr) => i === 0 || p.date.slice(0, 7) !== arr[i - 1].date.slice(0, 7));
  const grid = [0, 0.25, 0.5, 0.75, 1].map((p) => `<line x1="${left}" x2="${w - right}" y1="${y(p)}" y2="${y(p)}" class="bt-grid"/><text x="${left - 6}" y="${y(p) + 4}" text-anchor="end" class="bt-axis">${p * 100}%</text>`).join('');
  const ticks = months.filter((_, i) => i % 2 === 0).map((p) => `<text x="${x(p.date)}" y="${h - 12}" text-anchor="middle" class="bt-axis">${p.date.slice(2, 7).replace('-', '.')}</text>`).join('');
  const marks = data.timeline.map((e) => `<line x1="${x(e.date)}" x2="${x(e.date)}" y1="${top}" y2="${h - bottom}" class="bt-mark"><title>${ctx.esc(e.date + ': ' + (ctx.lang === 'ru' ? e.summary_ru : e.summary_en))}</title></line>`).join('');
  const at = (prefix: string, key: 'p1m' | 'p1y') => {
    const p = data.points.filter((q) => q.date.startsWith(prefix));
    return p.length ? ctx.pct(Math.max(...p.map((q) => q[key]))) : '—';
  };
  const last = data.points[data.points.length - 1];
  return `<section class="section"><div class="section-head"><h2>${d.btTitle}</h2><p>${d.btLead}</p></div>
    <p class="bt-summary">${ctx.esc(d.btSummary(at('2021-08', 'p1y'), at('2021-12', 'p1y'), ctx.pct(last.p1m)))}</p>
    <svg class="bt-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${ctx.esc(d.btTitle)}">${grid}${marks}${ticks}
      <path d="${line('p1y')}" class="bt-year"/><path d="${line('p1m')}" class="bt-month"/></svg>
    <div class="legend"><span class="legend-key"><i class="bt-year-key"></i>${d.btYear}</span><span class="legend-key"><i class="bt-month-key"></i>${d.btMonth}</span></div>
    <details><summary>${d.btEvents}</summary><ul class="warnings">${data.timeline.map((e) => `<li><time>${ctx.esc(e.date)}</time><div><p>${ctx.esc(ctx.lang === 'ru' ? e.summary_ru : e.summary_en)}</p><span class="muted-text small">${ctx.esc(e.source)}</span></div></li>`).join('')}</ul></details>
    <p class="caveat">${d.btCaveat}</p></section>`;
}

function caseChart(ctx: ViewContext, c: RealCase) {
  const w = 860, h = 220, left = 46, right = 12, top = 12, bottom = 30;
  if (!c.points.length) return '';
  const t0 = Date.parse(c.points[0].date), t1 = Date.parse(c.event_date);
  const x = (d: string) => left + ((Date.parse(d) - t0) / (t1 - t0)) * (w - left - right);
  const max = Math.max(0.1, ...c.points.map((p) => p.p1y)) * 1.15;
  const y = (p: number) => top + (1 - p / max) * (h - top - bottom);
  const line = (k: 'p1m' | 'p1y') => c.points.map((p, i) => `${i ? 'L' : 'M'}${x(p.date).toFixed(1)},${y(p[k]).toFixed(1)}`).join('');
  const ticks = [0, 0.5, 1].map((f) => max * f).map((p) => `<line x1="${left}" x2="${w - right}" y1="${y(p)}" y2="${y(p)}" class="bt-grid"/><text x="${left - 6}" y="${y(p) + 4}" text-anchor="end" class="bt-axis">${Math.round(p * 100)}%</text>`).join('');
  const months = c.points.filter((p, i, a) => i === 0 || p.date.slice(0, 7) !== a[i - 1].date.slice(0, 7)).filter((_, i) => i % 2 === 0)
    .map((p) => `<text x="${x(p.date)}" y="${h - 10}" text-anchor="middle" class="bt-axis">${p.date.slice(2, 7).replace('-', '.')}</text>`).join('');
  return `<svg class="bt-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${ctx.esc(ctx.lang === 'ru' ? c.title_ru : c.title_en)}">${ticks}${months}
    <line x1="${w - right}" x2="${w - right}" y1="${top}" y2="${h - bottom}" class="bt-event"/><path d="${line('p1y')}" class="bt-year"/><path d="${line('p1m')}" class="bt-month"/></svg>`;
}

export function realBacktestSection(ctx: ViewContext, data: RealBacktestFile | undefined, current: string) {
  const d = st(ctx.lang);
  const head = `<div class="section-head"><h2>${d.realTitle}</h2><p>${d.realLead}</p></div>`;
  if (!data || !data.cases.length) return `<section class="section">${head}<p class="muted-text">${d.realNone}</p></section>`;
  const c = data.cases.find((x) => x.key === current) ?? data.cases[0];
  const fmt = (v: number | null) => (v === null ? '—' : v.toFixed(4).replace('.', ctx.lang === 'ru' ? ',' : '.'));
  const tabs = `<div class="segmented wrap" role="group">${data.cases.map((x) => `<button type="button" data-btcase="${x.key}" aria-pressed="${x.key === c.key}">${ctx.esc(ctx.lang === 'ru' ? x.title_ru : x.title_en)}</button>`).join('')}</div>`;
  return `<section class="section">${head}${tabs}
    <ul class="plain small bt-facts"><li><strong>${ctx.esc(d.realLeadDays(c.lead_days))}</strong></li>
      <li>${ctx.esc(d.realMax(fx(c.max_factor, ctx.lang)))} · ${ctx.esc(d.realElevated(c.elevated_weeks))}</li>
      <li>${ctx.esc(d.realBrier(fmt(c.brier), fmt(c.brier_base)))}</li>${c.monthly ? `<li class="muted-text">${d.realMonthly}</li>` : ''}</ul>
    ${caseChart(ctx, c)}
    <div class="legend"><span class="legend-key"><i class="bt-year-key"></i>${d.btYear}</span><span class="legend-key"><i class="bt-month-key"></i>${d.btMonth}</span></div>
    <p class="caveat">${d.realCaveat}</p></section>`;
}
