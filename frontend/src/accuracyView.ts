// "How accurate are we" page: historical checks, the live forecast record and honest status.
import type { AccuracyFile, BacktestFile, RealBacktestFile } from './data';
import type { ViewContext } from './views';
import { backtestSection, realBacktestSection } from './signalsView';

const ru = {
  title: 'Насколько мы точны',
  lead: 'Здесь мы показываем, как модель справлялась с прошлыми событиями и как сбываются её собственные прогнозы. Пока это ранние проверки: вероятности ещё не откалиброваны.',
  statusTitle: 'Что уже проверено и что нет',
  status: [
    'Проверка на реальных архивных данных (GDELT, спутниковый радар Sentinel-1) — семь исторических случаев, таблица ниже.',
    'Отдельная проверка по вручную собранной хронологии подготовки вторжения в Украину в 2021–2022 годах.',
    'Собственные прогнозы GeoIntel сохраняются каждый день и будут оцениваться через 30 дней после каждого прогноза.',
    'Калибровка (совпадают ли 10% в среднем с 1 событием из 10) появится только после десятков оценённых прогнозов и событий — на это нужны годы.',
  ],
  casesTitle: 'Все исторические случаи',
  colCase: 'Случай', colLead: 'Заранее (дней)', colMax: 'Макс. множитель', colBrier: 'Ошибка Брайера', colBase: 'Без сигналов',
  better: 'лучше', worse: 'хуже',
  brierNote: 'Ошибка Брайера — средний квадрат разницы между вероятностью и тем, что произошло (0 — идеально). «Без сигналов» — та же модель только с базовой частотой. Если с сигналами ошибка меньше — сигналы помогают.',
  liveTitle: 'Наши прогнозы на месяц вперёд',
  collecting: (first: string, on: string) => `Собираем прогнозы с ${first}. Первые оценки появятся ${on}, когда пройдут 30 дней после первого прогноза.`,
  scoring: (n: number, ev: number, b: string) => `Оценено прогнозов: ${n}; наступивших событий: ${ev}; средняя ошибка Брайера: ${b}.`,
  resolutions: (d: string) => `Наступление событий проверяется вручную по публичным источникам; последняя проверка: ${d}.`,
  colScenario: 'Сценарий', colN: 'Прогнозов', colEvents: 'Событий', colMeanP: 'Средний прогноз',
  seriesTitle: 'Как менялась годовая вероятность сценариев',
  seriesNone: 'История пока короткая — график появится, когда накопится несколько дней.',
  unavailable: 'Файл с историей прогнозов ещё не опубликован. Он появится после ближайшего ежедневного обновления.',
};
type Dict = typeof ru;
const en: Dict = {
  title: 'How accurate are we',
  lead: 'This page shows how the model handled past events and how its own forecasts turn out. These are early checks: the probabilities are not calibrated yet.',
  statusTitle: 'What has and has not been checked',
  status: [
    'A check on real archived data (GDELT, Sentinel-1 radar) — seven historical cases, table below.',
    'A separate check against a hand-built timeline of the 2021–2022 build-up to the invasion of Ukraine.',
    'GeoIntel\'s own forecasts are stored every day and will be scored 30 days after each forecast.',
    'Calibration (whether 10% on average matches 1 event in 10) needs dozens of scored forecasts and events — that takes years.',
  ],
  casesTitle: 'All historical cases',
  colCase: 'Case', colLead: 'Ahead (days)', colMax: 'Max factor', colBrier: 'Brier error', colBase: 'Without signs',
  better: 'better', worse: 'worse',
  brierNote: 'The Brier error is the mean squared gap between the probability and what happened (0 is perfect). "Without signs" is the same model with the base rate only. If the error with signs is lower, the signs help.',
  liveTitle: 'Our one-month forecasts',
  collecting: (first: string, on: string) => `Collecting forecasts since ${first}. The first scores appear on ${on}, 30 days after the first forecast.`,
  scoring: (n: number, ev: number, b: string) => `Forecasts scored: ${n}; events that happened: ${ev}; mean Brier error: ${b}.`,
  resolutions: (d: string) => `Whether events happened is checked by hand against public sources; last check: ${d}.`,
  colScenario: 'Scenario', colN: 'Forecasts', colEvents: 'Events', colMeanP: 'Mean forecast',
  seriesTitle: 'How the scenarios\' yearly probability changed',
  seriesNone: 'The history is still short — the chart appears once a few days have accumulated.',
  unavailable: 'The forecast history file is not published yet. It will appear after the next daily update.',
};
const at = (lang: string) => (lang === 'ru' ? ru : en);

function num(v: number, lang: string, digits = 4) {
  return v.toFixed(digits).replace('.', lang === 'ru' ? ',' : '.');
}

function casesTable(ctx: ViewContext, data: RealBacktestFile | undefined) {
  const d = at(ctx.lang);
  if (!data?.cases.length) return '';
  const rows = data.cases.map((c) => {
    const verdict = c.brier === null || c.brier_base === null ? '' : c.brier < c.brier_base ? d.better : d.worse;
    return `<tr><th scope="row">${ctx.esc(ctx.lang === 'ru' ? c.title_ru : c.title_en)}</th>
      <td class="numcell">${c.lead_days ?? '—'}</td><td class="numcell">×${num(c.max_factor, ctx.lang, 2)}</td>
      <td class="numcell">${c.brier === null ? '—' : num(c.brier, ctx.lang)}</td><td class="numcell">${c.brier_base === null ? '—' : num(c.brier_base, ctx.lang)}</td><td>${verdict}</td></tr>`;
  }).join('');
  return `<section class="section"><div class="section-head"><h2>${d.casesTitle}</h2><p>${d.brierNote}</p></div>
    <div class="table-wrap"><table class="table"><thead><tr><th>${d.colCase}</th><th>${d.colLead}</th><th>${d.colMax}</th><th>${d.colBrier}</th><th>${d.colBase}</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

function seriesChart(ctx: ViewContext, acc: AccuracyFile) {
  const d = at(ctx.lang);
  const keys = Object.keys(acc.series).filter((k) => acc.series[k].length >= 2);
  if (!keys.length) return `<p class="muted-text">${d.seriesNone}</p>`;
  const rows = keys.map((k) => {
    const pts = acc.series[k];
    const w = 220, h = 40;
    const max = Math.max(...pts.map((p) => p.p1y), 1e-6) * 1.1;
    const path = pts.map((p, i) => `${i ? 'L' : 'M'}${((i / (pts.length - 1)) * w).toFixed(1)},${(h - (p.p1y / max) * h).toFixed(1)}`).join('');
    const t = acc.titles[k];
    const last = pts[pts.length - 1].p1y, first = pts[0].p1y;
    return `<tr><th scope="row">${ctx.esc((ctx.lang === 'ru' ? t?.title_ru : t?.title_en) ?? k)}</th>
      <td><svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true"><path d="${path}" class="bt-year"/></svg></td>
      <td class="numcell">${ctx.pct(first)} → ${ctx.pct(last)}</td></tr>`;
  }).join('');
  return `<div class="table-wrap"><table class="table"><tbody>${rows}</tbody></table></div>`;
}

function liveSection(ctx: ViewContext, acc: AccuracyFile | undefined) {
  const d = at(ctx.lang);
  const head = `<div class="section-head"><h2>${d.liveTitle}</h2></div>`;
  if (!acc) return `<section class="section">${head}<p class="muted-text">${d.unavailable}</p></section>`;
  const status = acc.status === 'collecting' || !acc.overall
    ? `<p>${ctx.esc(d.collecting(acc.first_day ?? acc.generated_at, acc.first_score_on ?? '—'))}</p>`
    : `<p>${ctx.esc(d.scoring(acc.overall.n, acc.overall.events, num(acc.overall.brier, ctx.lang)))}</p>`;
  const summary = Object.entries(acc.summary);
  const table = summary.length ? `<div class="table-wrap"><table class="table"><thead><tr><th>${d.colScenario}</th><th>${d.colN}</th><th>${d.colEvents}</th><th>${d.colMeanP}</th><th>${d.colBrier}</th></tr></thead><tbody>${summary.map(([k, s]) =>
    `<tr><th scope="row">${ctx.esc((ctx.lang === 'ru' ? acc.titles[k]?.title_ru : acc.titles[k]?.title_en) ?? k)}</th><td class="numcell">${s.n}</td><td class="numcell">${s.events}</td><td class="numcell">${ctx.pct(s.mean_p)}</td><td class="numcell">${num(s.brier, ctx.lang)}</td></tr>`).join('')}</tbody></table></div>` : '';
  return `<section class="section">${head}${status}${table}<p class="muted-text small">${ctx.esc(d.resolutions(acc.resolutions_checked))}</p>
    <h3>${d.seriesTitle}</h3>${seriesChart(ctx, acc)}</section>`;
}

export function accuracyPage(ctx: ViewContext, acc: AccuracyFile | undefined, bt: BacktestFile | undefined, real: RealBacktestFile | undefined, btCase: string, trainedHtml = '') {
  const d = at(ctx.lang);
  return `<section class="page-head"><h1>${d.title}</h1><p>${d.lead}</p></section>
    <section class="section"><div class="section-head"><h2>${d.statusTitle}</h2></div><ul class="plain">${d.status.map((s) => `<li>${ctx.esc(s)}</li>`).join('')}</ul></section>
    ${trainedHtml}${casesTable(ctx, real)}${realBacktestSection(ctx, real, btCase)}${liveSection(ctx, acc)}${backtestSection(ctx, bt)}`;
}
