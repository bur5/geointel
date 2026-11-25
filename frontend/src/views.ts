// Scenario, links and migration views (rendered into the shell built by main.ts).
import { band } from './data';
import type { HorizonKey, Lang, LinksFile, Probability, Scenario, ScenarioFile, ScenarioRole } from './data';
import { CHAIN_EVENTS, effect, formatPeople, linksOf } from './chains';
import type { ChainEvent, CountryLink, LinkKind } from './chains';

export interface ViewContext {
  lang: Lang;
  esc: (value: string) => string;
  name: (iso3: string) => string;
  pct: (p: number) => string;
}

const ru = {
  scenariosTitle: 'Сценарии',
  scenariosLead: 'Конкретные события вместо средней частоты. Вероятность каждого сценария собрана из нескольких независимых источников, рядом — сигналы эскалации и страны, которых он коснётся, с объяснением почему.',
  definition: 'Что считается наступлением сценария',
  deescalation: 'Сценарий деэскалации: высокая вероятность — хорошая новость.',
  componentsTitle: 'Из чего складывается вероятность',
  componentsLead: 'Каждый источник показан отдельно. Итог — взвешенное среднее источников, затем поправка по индикаторам. Диапазон показывает разброс между источниками.',
  colSource: 'Источник',
  colAnnual: 'За год',
  colRange: 'Диапазон',
  colWeight: 'Вес',
  kind: { history: 'История конфликтов сторон (UCDP/PRIO)', expert: 'Экспертная априорная оценка GeoIntel', market: 'Рынок прогнозов (Polymarket)', official: 'Официальная оценка разведки (по шкале формулировок)', community: 'Сообщество прогнозистов (Metaculus)', panel: 'Анкета экспертов GeoIntel' },
  communityOff: 'Metaculus не подключён (нужен токен) — источник не участвует.',
  communityNone: 'Подходящего вопроса Metaculus со сроком от 4 месяцев не нашлось.',
  combo: 'Активны признаки из трёх и более групп подготовки — дополнительный коэффициент × 1,5.',
  inCountries: 'где',
  factor: (x: string) => `Поправка по индикаторам: шансы × ${x}`,
  pooled: 'Итог',
  marketNone: 'Подходящего рынка прогнозов со сроком от 4 месяцев не нашлось — источник не участвует (рынки на ближайшие недели показаны в индикаторах).',
  marketOff: 'Рынки прогнозов сегодня недоступны — источник не участвует.',
  candidates: 'Найденные рынки (для проверки)',
  inverse: 'обратный вопрос, вероятность сценария',
  indicatorsTitle: 'Индикаторы эскалации и деэскалации',
  indicatorsLead: 'Признаки, которые сдвигают оценку, с коэффициентом: во сколько раз каждый меняет шансы. Подробнее — на странице «Сигналы».',
  dir: { 1: 'эскалация', 0: 'нейтрально', [-1]: 'деэскалация' } as Record<number, string>,
  warningsTitle: 'Официальные оценки и события',
  affectedTitle: 'Кого затронет и почему',
  affectedLead: 'Роли стран: стороны сценария, передовая (граница, войска, логистика), союзники с обязательствами и экономически связанные страны.',
  role: { party: 'Сторона', frontline: 'Передовая', ally: 'Союзник с обязательствами', economic: 'Экономические последствия' } as Record<ScenarioRole, string>,
  roleShort: { party: 'сторона', frontline: 'передовая', ally: 'союзник', economic: 'экономика' } as Record<ScenarioRole, string>,
  uncalibrated: 'Оценки сценариев не откалиброваны: прецедентов мало, проверить точность на истории пока нельзя. Это ориентир для сравнения сценариев и отслеживания сдвигов, а не точный прогноз.',
  confidence: { low: 'низкая', medium: 'средняя' },
  confidenceLabel: 'Уверенность',
  inCountryTitle: 'Сценарии, затрагивающие страну',
  inCountryLead: 'Роль страны в каждом сценарии и вероятность сценария.',
  inCountryNone: 'Ни один сценарий из каталога пока не затрагивает эту страну напрямую.',
  openScenario: 'Открыть сценарий',
  perYear: 'за год',
  in5y: 'за 5 лет',
  linksTitle: 'Связи и цепочки последствий',
  linksLead: 'Если в стране случится событие, через какие связи оно дойдёт до других стран и что там произойдёт. Связи: границы, союзы, торговля, беженцы и миграционные маршруты.',
  chainEvent: { conflict: 'Вооружённый конфликт', political: 'Политический кризис', economic: 'Экономический кризис', disaster: 'Стихийное бедствие', migration: 'Миграционный всплеск' } as Record<ChainEvent, string>,
  linkKind: { border: 'граница', bloc: 'союз', market: 'рынок сбыта', supplier: 'поставщик', diaspora: 'беженцы', route: 'маршрут' } as Record<LinkKind, string>,
  ifEvent: (event: string, country: string) => `Если в стране ${country}: ${event.toLowerCase()}`,
  consequences: 'Что произойдёт',
  blocRest: (n: number, e: string) => `Ещё ${n} — связь только через общий союз: ${e}.`,
  noLinks: 'Данных о связях для этой страны пока нет.',
  tradeNote: (year: string) => `Торговля: UN Comtrade${year ? ', ' + year : ''}; импорт — по зеркальным данным экспорта партнёров.`,
  migrationTitle: 'Миграция и беженцы',
  hosted: 'Принимает беженцев и просителей убежища',
  perThousand: (v: string) => `${v} на 1000 жителей`,
  abroad: 'Беженцы и просители убежища из страны за рубежом',
  idps: 'Внутренне перемещённые',
  fromWhere: 'Откуда',
  whereTo: 'Где находятся',
  asylumEu: 'Первичные заявления на убежище (Eurostat), за 12 мес.',
  vsPrev: (v: string) => `${v} к предыдущим 12 мес.`,
  routesHere: 'Миграционные маршруты',
  routeFrom: 'отсюда',
  routeTo: 'сюда',
  unhcrNote: (year: string) => `UNHCR, конец ${year} года: беженцы, просители убежища и другие нуждающиеся в международной защите.`,
  migrationNone: 'Данных UNHCR по стране нет.',
  migPageTitle: 'Миграция',
  migPageLead: 'Где живут беженцы и просители убежища, откуда они, как меняется число заявлений на убежище в Европе и по каким маршрутам идут люди.',
  migMapHosted: 'Принимают (на 1000 жителей)',
  migMapAbroad: 'Покинули страну (на 1000 жителей)',
  migLegend: 'На 1000 жителей',
  migNoData: 'Нет данных',
  euTableTitle: 'Заявления на убежище в Европе',
  euTableLead: 'Первичные заявления за последние 12 месяцев и изменение к предыдущим 12 (Eurostat, ежемесячно).',
  colCountry: 'Страна',
  colLast12: 'За 12 мес.',
  colChange: 'Изменение',
  colTrend: '24 месяца',
  routesTitle: 'Основные маршруты нерегулярной миграции',
  routesLead: 'Маршруты по классификации Frontex и пограничных служб США. Это связи «откуда — куда», без оценки объёма.',
  topHosts: 'Больше всего принимают',
  topOrigins: 'Больше всего покинули',
  milexTitle: 'Военные расходы',
  milexNote: (y: number, d: string) => `% ВВП, ${y}; изменение за 5 лет: ${d} п. п. (SIPRI)`,
  loading: 'Загружаем…',
  unavailable: 'Данные пока не опубликованы. Они появятся после ближайшего ежедневного обновления.',
  treeTitle: 'Как риск меняется со временем',
  treeInputs: (a: string, c: string, u: string) => `Сейчас: ${a} в год. Вероятность прекращения огня в Украине: ${c} в год; ослабления гарантий США: ${u} в год (из соответствующих сценариев).`,
  treeYear: 'Год', treeAnnual: 'Риск в этот год', treeCum: 'Накопленно',
  treeBranches: 'Ветви сценария', treeBranch: 'Ветвь', treeWeight: 'Вероятность ветви', treeP5: 'За 5 лет', treeP10: 'За 10 лет',
  ukraine: { war: 'Война в Украине идёт все 10 лет', cease_early: 'Прекращение огня в ближайшие 2 года', cease_late: 'Прекращение огня через 2–10 лет' } as Record<string, string>,
  us: { us_firm: 'гарантии США сохраняются', us_weak: 'гарантии США ослабевают' } as Record<string, string>,
};

type Dict = typeof ru;
const en: Dict = {
  scenariosTitle: 'Scenarios',
  scenariosLead: 'Concrete events instead of average frequencies. Each scenario\'s probability combines several independent sources, next to escalation signals and the countries it would hit, with the reasons why.',
  definition: 'What counts as the scenario happening',
  treeTitle: 'How the risk changes over time',
  treeInputs: (a: string, c: string, u: string) => `Now: ${a} a year. Chance of a ceasefire in Ukraine: ${c} a year; of weaker US guarantees: ${u} a year (from those scenarios).`,
  treeYear: 'Year', treeAnnual: 'Risk in that year', treeCum: 'Cumulative',
  treeBranches: 'Scenario branches', treeBranch: 'Branch', treeWeight: 'Branch probability', treeP5: 'Within 5 years', treeP10: 'Within 10 years',
  ukraine: { war: 'War in Ukraine continues all 10 years', cease_early: 'Ceasefire within 2 years', cease_late: 'Ceasefire in 2–10 years' } as Record<string, string>,
  us: { us_firm: 'US guarantees hold', us_weak: 'US guarantees weaken' } as Record<string, string>,
  deescalation: 'De-escalation scenario: a high probability is good news.',
  componentsTitle: 'What the probability is made of',
  componentsLead: 'Each source is shown separately. The result is a weighted average of the sources, then adjusted by the indicators. The range shows the spread between sources.',
  colSource: 'Source',
  colAnnual: 'Per year',
  colRange: 'Range',
  colWeight: 'Weight',
  kind: { history: 'Conflict history of the sides (UCDP/PRIO)', expert: 'GeoIntel expert prior', market: 'Prediction market (Polymarket)', official: 'Official intelligence judgement (wording scale)', community: 'Forecasting community (Metaculus)', panel: 'GeoIntel expert questionnaire' },
  communityOff: 'Metaculus is not connected (token needed), so this source is not used.',
  communityNone: 'No matching Metaculus question running 4+ months was found.',
  combo: 'Signs from three or more preparation groups are active, adding a further × 1.5.',
  inCountries: 'where',
  factor: (x: string) => `Indicator adjustment: odds × ${x}`,
  pooled: 'Result',
  marketNone: 'No matching prediction market running at least 4 months was found, so this source is not used (near-term markets appear among the indicators).',
  marketOff: 'Prediction markets were unavailable today, so this source is not used.',
  candidates: 'Markets found (for checking)',
  inverse: 'inverse question, scenario probability',
  indicatorsTitle: 'Escalation and de-escalation indicators',
  indicatorsLead: 'Signs that shift the estimate, with the factor by which each changes the odds. More on the Signals page.',
  dir: { 1: 'escalation', 0: 'neutral', [-1]: 'de-escalation' } as Record<number, string>,
  warningsTitle: 'Official assessments and events',
  affectedTitle: 'Who it affects and why',
  affectedLead: 'Country roles: parties, the front line (borders, troops, logistics), allies with obligations and economically exposed countries.',
  role: { party: 'Party', frontline: 'Front line', ally: 'Ally with obligations', economic: 'Economic effects' },
  roleShort: { party: 'party', frontline: 'front line', ally: 'ally', economic: 'economy' },
  uncalibrated: 'Scenario estimates are not calibrated: precedents are few and accuracy cannot yet be checked against history. Use them to compare scenarios and track shifts, not as exact forecasts.',
  confidence: { low: 'low', medium: 'medium' },
  confidenceLabel: 'Confidence',
  inCountryTitle: 'Scenarios that involve this country',
  inCountryLead: 'The country\'s role in each scenario and the scenario\'s probability.',
  inCountryNone: 'No scenario in the catalogue involves this country directly yet.',
  openScenario: 'Open scenario',
  perYear: 'per year',
  in5y: 'in 5 years',
  linksTitle: 'Links and impact chains',
  linksLead: 'If something happens in this country, which links carry it to other countries and what happens there. Links: borders, alliances, trade, refugees and migration routes.',
  chainEvent: { conflict: 'Armed conflict', political: 'Political crisis', economic: 'Economic crisis', disaster: 'Natural disaster', migration: 'Migration surge' },
  linkKind: { border: 'border', bloc: 'alliance', market: 'export market', supplier: 'supplier', diaspora: 'refugees', route: 'route' },
  ifEvent: (event: string, country: string) => `If ${country} has a ${event.toLowerCase()}`,
  consequences: 'What happens',
  blocRest: (n: number, e: string) => `${n} more linked only through a shared alliance: ${e}.`,
  noLinks: 'No link data for this country yet.',
  tradeNote: (year: string) => `Trade: UN Comtrade${year ? ', ' + year : ''}; imports from partners' reported exports (mirror data).`,
  migrationTitle: 'Migration and refugees',
  hosted: 'Hosts refugees and asylum seekers',
  perThousand: (v: string) => `${v} per 1,000 residents`,
  abroad: 'Refugees and asylum seekers from the country abroad',
  idps: 'Internally displaced',
  fromWhere: 'From',
  whereTo: 'Where they are',
  asylumEu: 'First-time asylum applications (Eurostat), last 12 months',
  vsPrev: (v: string) => `${v} vs the previous 12 months`,
  routesHere: 'Migration routes',
  routeFrom: 'from here',
  routeTo: 'to here',
  unhcrNote: (year: string) => `UNHCR, end of ${year}: refugees, asylum seekers and others in need of international protection.`,
  migrationNone: 'No UNHCR data for this country.',
  migPageTitle: 'Migration',
  migPageLead: 'Where refugees and asylum seekers live, where they come from, how asylum applications in Europe are changing and which routes people take.',
  migMapHosted: 'Hosting (per 1,000 residents)',
  migMapAbroad: 'Left the country (per 1,000 residents)',
  migLegend: 'Per 1,000 residents',
  migNoData: 'No data',
  euTableTitle: 'Asylum applications in Europe',
  euTableLead: 'First-time applications in the last 12 months and the change from the previous 12 (Eurostat, monthly).',
  colCountry: 'Country',
  colLast12: 'Last 12 months',
  colChange: 'Change',
  colTrend: '24 months',
  routesTitle: 'Main irregular migration routes',
  routesLead: 'Routes as named by Frontex and US border agencies. They are "from – to" links without volumes.',
  topHosts: 'Largest hosts',
  topOrigins: 'Largest origins',
  milexTitle: 'Military spending',
  milexNote: (y: number, d: string) => `% of GDP, ${y}; 5-year change: ${d} pp (SIPRI)`,
  loading: 'Loading…',
  unavailable: 'Not published yet. It will appear after the next daily update.',
};
const dicts: Record<Lang, Dict> = { ru, en };
export const vt = (lang: Lang) => dicts[lang];

const ROLE_ORDER: ScenarioRole[] = ['party', 'frontline', 'ally', 'economic'];
const ROLE_CLASS: Record<ScenarioRole, string> = { party: 'role-party', frontline: 'role-frontline', ally: 'role-ally', economic: 'role-economic' };
export const roleClass = (role: ScenarioRole) => ROLE_CLASS[role];
const num = (v: number, lang: Lang, digits = 1) => v.toFixed(digits).replace('.', lang === 'ru' ? ',' : '.');
const signed = (v: number, lang: Lang) => (v > 0 ? '+' : v < 0 ? '−' : '') + num(Math.abs(v), lang);
const title = (s: Scenario, lang: Lang) => (lang === 'ru' ? s.title_ru : s.title_en);
const probClass = (s: Scenario, p: number) => (s.polarity < 0 ? 'good' : band(p));

function bar(v: Probability, cls: string) {
  const left = v.low * 100, width = Math.max((v.high - v.low) * 100, 0.6), dot = v.p * 100;
  return `<span class="bar" aria-hidden="true"><span class="bar-range ${cls}" style="left:${left}%;width:${width}%"></span><span class="bar-dot" style="left:${dot}%"></span></span>`;
}
const probability = (ctx: ViewContext, s: Scenario, v: Probability, size: 'lg' | 'sm' = 'sm') =>
  `<div class="value value-${size}"><span class="num">${ctx.pct(v.p)}</span>${bar(v, probClass(s, v.p))}<span class="range">${ctx.pct(v.low)} – ${ctx.pct(v.high)}</span></div>`;

const arrow = (d: number) => (d > 0 ? '▲' : d < 0 ? '▼' : '•');

export function scenarioTabs(ctx: ViewContext, file: ScenarioFile, current: string) {
  return `<div class="scenario-tabs" role="tablist">${file.scenarios.map((s) =>
    `<button type="button" role="tab" data-scenario="${s.key}" aria-selected="${s.key === current}">
      <span>${ctx.esc(title(s, ctx.lang))}</span><b class="${probClass(s, s.horizons['1y'].p)}-text">${ctx.pct(s.horizons['1y'].p)}<small> ${vt(ctx.lang).perYear}</small></b></button>`).join('')}</div>`;
}

export function scenarioDetail(ctx: ViewContext, s: Scenario, horizonLabels: Record<HorizonKey, string>) {
  const d = vt(ctx.lang);
  const { esc, lang } = ctx;
  const horizons = (Object.keys(horizonLabels) as HorizonKey[]).map((h) =>
    `<div><span class="h-label">${esc(horizonLabels[h])}</span>${probability(ctx, s, s.horizons[h], 'lg')}</div>`).join('');
  const rows = s.components.map((c) => `<tr class="main-row"><th scope="row">${esc(d.kind[c.kind])}</th>
      <td class="numcell">${ctx.pct(c.annual)}</td><td class="numcell">${ctx.pct(c.low)} – ${ctx.pct(c.high)}</td><td class="numcell">${num(c.weight, lang)}</td></tr>
      <tr class="detail-row"><td colspan="4" class="detail">${esc(lang === 'ru' ? c.detail_ru : c.detail_en)}${c.url ? ` <a href="${esc(c.url)}" rel="noreferrer">${lang === 'ru' ? 'источник' : 'source'}</a>` : ''}</td></tr>`).join('');
  const communityRow = s.community_status === 'matched' ? '' : `<tr class="main-row muted-row"><th scope="row">${esc(d.kind.community)}</th><td colspan="3">${s.community_status === 'no_match' ? d.communityNone : d.communityOff}</td></tr>`;
  const marketRow = s.market_status === 'matched' ? '' : `<tr class="main-row muted-row"><th scope="row">${esc(d.kind.market)}</th><td colspan="3">${s.market_status === 'unavailable' ? d.marketOff : d.marketNone}</td></tr>`;
  const indicators = s.indicators.map((i) => `<li class="ind dir-${i.direction > 0 ? 'up' : i.direction < 0 ? 'down' : 'flat'}">
      <span class="ind-arrow" aria-label="${esc(d.dir[i.direction])}">${i.lr && i.lr !== 1 ? '×' + num(i.lr, lang, i.lr >= 10 ? 0 : 2).replace(/[,.]00$/, '') : arrow(i.direction)}</span>
      <span class="ind-label">${esc(lang === 'ru' ? i.label_ru : i.label_en)}</span>
      <span class="ind-value">${esc((lang === 'ru' ? i.value_ru : i.value_en) ?? i.value)}${i.countries?.length ? ` <span class="muted-text">(${d.inCountries}: ${i.countries.map((c) => esc(ctx.name(c))).join(', ')})</span>` : ''}${i.url ? ` <a href="${esc(i.url)}" rel="noreferrer">↗</a>` : ''}</span><span class="ind-source">${esc(i.source)}</span></li>`).join('');
  const warnings = s.warnings.map((w) => `<li><time>${esc(w.date)}</time><div><p>${esc(lang === 'ru' ? w.summary_ru : w.summary_en)}</p>
      <a href="${esc(w.url)}" rel="noreferrer">${esc(w.source)}</a></div></li>`).join('');
  const affected = ROLE_ORDER.map((role) => {
    const items = s.affected.filter((a) => a.role === role);
    if (!items.length) return '';
    const byReason = new Map<string, string[]>();
    for (const a of items) {
      const reason = lang === 'ru' ? a.reason_ru : a.reason_en;
      byReason.set(reason, [...(byReason.get(reason) ?? []), a.iso3]);
    }
    return `<div class="role-group"><h4><i class="${roleClass(role)}"></i>${esc(d.role[role])}</h4><ul>${[...byReason].map(([reason, codes]) =>
      `<li><span class="role-countries">${codes.map((c) => `<button type="button" class="link" data-select="${c}">${esc(ctx.name(c))}</button>`).join(', ')}</span><span class="muted-text">${esc(reason)}</span></li>`).join('')}</ul></div>`;
  }).join('');
  const candidates = s.market_candidates.length ? `<details><summary>${d.candidates}</summary><ul class="candidates">${s.market_candidates.map((m) =>
    `<li><a href="https://polymarket.com/event/${esc(m.slug)}" rel="noreferrer" lang="en">${esc(m.question)}</a> — ${m.inverse ? d.inverse + ' ' : ''}${ctx.pct(m.p)}, ${esc(m.end)}</li>`).join('')}</ul></details>` : '';
  const tree = s.tree ? treeSection(ctx, s) : '';
  return `<article class="scenario" id="scenario-detail">
    <div class="scenario-head"><h2>${esc(title(s, lang))}</h2>
      <p class="muted-text">${d.confidenceLabel}: ${d.confidence[s.confidence]}.${s.polarity < 0 ? ' ' + d.deescalation : ''}</p>
      <details open><summary>${d.definition}</summary><p>${esc(lang === 'ru' ? s.event_ru : s.event_en)}</p></details></div>
    <div class="horizon-grid">${horizons}</div>
    <div class="scenario-cols">
      <section class="sub-section"><h3>${d.componentsTitle}</h3><p class="muted-text">${d.componentsLead}</p>
        <div class="table-wrap"><table class="table comp"><thead><tr><th>${d.colSource}</th><th>${d.colAnnual}</th><th>${d.colRange}</th><th>${d.colWeight}</th></tr></thead>
        <tbody>${rows}${marketRow}${communityRow}<tr class="main-row pooled"><th scope="row">${d.pooled}</th><td class="numcell">${ctx.pct(s.annual.p)}</td><td class="numcell">${ctx.pct(s.annual.low)} – ${ctx.pct(s.annual.high)}</td><td></td></tr>
        <tr class="detail-row"><td colspan="4" class="detail">${esc(d.factor(num(s.indicator_factor, lang, 2)))}</td></tr></tbody></table></div>${candidates}</section>
      <section class="sub-section"><h3>${d.indicatorsTitle}</h3><p class="muted-text">${d.indicatorsLead}</p><ul class="indicators">${indicators}</ul>${s.sign_combo ? `<p class="muted-text small">${d.combo}</p>` : ''}
        ${warnings ? `<h3>${d.warningsTitle}</h3><ul class="warnings">${warnings}</ul>` : ''}</section>
    </div>
    ${tree}
    <section class="sub-section"><h3>${d.affectedTitle}</h3><p class="muted-text">${d.affectedLead}</p>
      <div class="affected-layout"><div class="map-stage scenario-map" id="scenario-map"><svg viewBox="0 0 900 440" role="img" tabindex="0" aria-label="${esc(d.affectedTitle)}"><g></g></svg>
        <div class="tooltip" hidden></div>
        <div class="map-controls"><button data-map="in" aria-label="+">+</button><button data-map="out" aria-label="−">−</button><button data-map="reset" aria-label="⟲">⟲</button></div></div>
      <div class="legend">${ROLE_ORDER.map((r) => `<span class="legend-key"><i class="${roleClass(r)}"></i>${esc(d.role[r])}</span>`).join('')}</div>
      <div class="roles">${affected}</div></div></section>
    <p class="caveat">${d.uncalibrated}</p>
  </article>`;
}

function treeSection(ctx: ViewContext, s: Scenario) {
  const d = vt(ctx.lang);
  const t = s.tree!;
  const start = new Date().getFullYear();
  const top = Math.max(...t.yearly.map((y) => y.annual), 1e-6);
  const years = t.yearly.map((y) => `<tr><th scope="row">${start + y.year - 1}</th>
    <td><span class="tree-bar" style="width:${Math.round((y.annual / top) * 100)}%"></span>${ctx.pct(y.annual)}</td><td class="numcell">${ctx.pct(y.cumulative)}</td></tr>`).join('');
  const branches = [...t.branches].sort((a, b) => b.weight - a.weight).map((b) => `<tr><th scope="row">${ctx.esc(d.ukraine[b.ukraine])}; ${ctx.esc(d.us[b.us])}</th>
    <td class="numcell">${ctx.pct(b.weight)}</td><td class="numcell">${ctx.pct(b.p5y)}</td><td class="numcell">${ctx.pct(b.p10y)}</td></tr>`).join('');
  return `<section class="sub-section tree" id="scenario-tree"><h3>${d.treeTitle}</h3>
    <p class="muted-text">${ctx.esc(ctx.lang === 'ru' ? t.basis_ru : t.basis_en)}</p>
    <p class="muted-text">${ctx.esc(d.treeInputs(ctx.pct(t.inputs.annual_now), ctx.pct(t.inputs.ceasefire_annual), ctx.pct(t.inputs.us_weak_annual)))}</p>
    <div class="scenario-cols"><div class="table-wrap"><table class="table"><thead><tr><th>${d.treeYear}</th><th>${d.treeAnnual}</th><th>${d.treeCum}</th></tr></thead><tbody>${years}</tbody></table></div>
    <div class="table-wrap"><table class="table"><caption>${d.treeBranches}</caption><thead><tr><th>${d.treeBranch}</th><th>${d.treeWeight}</th><th>${d.treeP5}</th><th>${d.treeP10}</th></tr></thead><tbody>${branches}</tbody></table></div></div></section>`;
}

export function scenariosPage(ctx: ViewContext, file: ScenarioFile | undefined, current: string, horizonLabels: Record<HorizonKey, string>) {
  const d = vt(ctx.lang);
  const head = `<section class="page-head"><h1>${d.scenariosTitle}</h1><p>${d.scenariosLead}</p></section>`;
  if (!file) return head + `<div class="notice" role="status"><strong>${d.unavailable}</strong></div>`;
  const s = file.scenarios.find((x) => x.key === current) ?? file.scenarios[0];
  return head + scenarioTabs(ctx, file, s.key) + `<section class="section">${scenarioDetail(ctx, s, horizonLabels)}</section>`;
}

export function countryScenarios(ctx: ViewContext, file: ScenarioFile | undefined, iso3: string) {
  const d = vt(ctx.lang);
  const head = `<div class="section-head"><h2>${d.inCountryTitle}</h2><p>${d.inCountryLead}</p></div>`;
  if (!file) return head + `<p class="muted-text">${d.unavailable}</p>`;
  const items = file.scenarios.flatMap((s) => s.affected.filter((a) => a.iso3 === iso3).map((a) => ({ s, a })));
  if (!items.length) return head + `<p class="muted-text">${d.inCountryNone}</p>`;
  items.sort((x, y) => ROLE_ORDER.indexOf(x.a.role) - ROLE_ORDER.indexOf(y.a.role) || y.s.horizons['1y'].p - x.s.horizons['1y'].p);
  return head + `<div class="sc-cards">${items.map(({ s, a }) => `<article class="sc-card">
      <span class="role-badge ${roleClass(a.role)}">${ctx.esc(d.roleShort[a.role])}</span>
      <h3>${ctx.esc(title(s, ctx.lang))}</h3>
      <p>${ctx.esc(ctx.lang === 'ru' ? a.reason_ru : a.reason_en)}</p>
      <div class="sc-probs"><span><b class="${probClass(s, s.horizons['1y'].p)}-text">${ctx.pct(s.horizons['1y'].p)}</b> ${d.perYear}</span><span><b>${ctx.pct(s.horizons['5y'].p)}</b> ${d.in5y}</span></div>
      <a class="link" href="#scenarios" data-scenario="${s.key}">${d.openScenario}</a></article>`).join('')}</div>`;
}

// ---------------------------------------------------------------------------- links graph

const KIND_ORDER: LinkKind[] = ['border', 'bloc', 'market', 'supplier', 'diaspora', 'route'];

export function linksSection(
  ctx: ViewContext, iso3: string, event: ChainEvent, neighbours: string[], data: LinksFile | undefined,
) {
  const d = vt(ctx.lang);
  const { esc, lang } = ctx;
  const switcher = `<div class="segmented wrap" role="group" aria-label="${esc(d.linksTitle)}">${CHAIN_EVENTS.map((e) =>
    `<button type="button" data-chain="${e}" aria-pressed="${e === event}">${esc(d.chainEvent[e])}</button>`).join('')}</div>`;
  const head = `<div class="section-head"><h2>${d.linksTitle}</h2><p>${d.linksLead}</p></div>${switcher}`;
  const all = linksOf(iso3, event, neighbours, data, ctx.name);
  if (!all.length) return head + `<p class="muted-text">${d.noLinks}</p>`;
  // Alliance-only ties are many and alike: show direct ties first and summarise the rest.
  const direct = all.filter((l) => l.reasons.some((r) => r.kind !== 'bloc'));
  const blocOnly = all.filter((l) => l.reasons.every((r) => r.kind === 'bloc'));
  const links = [...direct, ...blocOnly.slice(0, Math.max(0, 6 - direct.length))].slice(0, 14);
  const rest = blocOnly.slice(Math.max(0, 6 - direct.length));
  const restLine = rest.length ? `<p class="muted-text small">${esc(d.blocRest(rest.length, effect(event, 'bloc', lang)))}</p>` : '';
  const list = links.map((link) => {
    const kinds = [...new Set(link.reasons.map((r) => r.kind))];
    return `<li><button type="button" class="link" data-select="${link.iso3}">${esc(ctx.name(link.iso3))}</button>
      <span class="chips">${link.reasons.slice(0, 3).map((r) => `<span class="chip k-${r.kind}" title="${esc(d.linkKind[r.kind])}">${esc(lang === 'ru' ? r.ru : r.en)}</span>`).join('')}</span>
      <p class="effects">→ ${esc(kinds.slice(0, 3).map((k) => effect(event, k, lang)).join('; '))}</p></li>`;
  }).join('');
  const year = data?.countries[iso3]?.trade?.year ?? Object.values(data?.countries ?? {}).find((c) => c.trade?.year)?.trade?.year;
  return head + `<div class="links-layout">${graph(ctx, iso3, links)}
    <div><h3 class="sub">${esc(d.ifEvent(d.chainEvent[event], ctx.name(iso3)))}</h3><ul class="link-list">${list}</ul>${restLine}
    <p class="muted-text small">${esc(d.tradeNote(year ? String(year) : ''))}</p></div></div>
    <div class="legend">${KIND_ORDER.map((k) => `<span class="legend-key"><i class="k-${k}"></i>${esc(d.linkKind[k])}</span>`).join('')}</div>`;
}

function graph(ctx: ViewContext, iso3: string, links: CountryLink[]) {
  const w = 560, h = 440, cx = w / 2, cy = h / 2;
  const max = Math.max(...links.map((l) => l.score));
  const nodes = links.map((link, i) => {
    const angle = (i / links.length) * Math.PI * 2 - Math.PI / 2;
    const r = 120 + (1 - link.score / max) * 70;
    return { link, x: cx + Math.cos(angle) * r * 1.15, y: cy + Math.sin(angle) * r * 0.92, size: 10 + (link.score / max) * 12 };
  });
  const edges = nodes.map((n) => `<line x1="${cx}" y1="${cy}" x2="${n.x.toFixed(1)}" y2="${n.y.toFixed(1)}" class="edge k-${n.link.reasons[0].kind}" stroke-width="${(1 + (n.link.score / max) * 5).toFixed(1)}"/>`).join('');
  const dots = nodes.map((n) => {
    const name = ctx.esc(ctx.name(n.link.iso3));
    const anchor = n.x < cx - 10 ? 'end' : n.x > cx + 10 ? 'start' : 'middle';
    const dx = anchor === 'end' ? -(n.size + 5) : anchor === 'start' ? n.size + 5 : 0;
    const dy = anchor === 'middle' ? (n.y < cy ? -(n.size + 6) : n.size + 14) : 4;
    return `<g class="node" data-select="${n.link.iso3}" tabindex="0" role="button" aria-label="${name}">
      <circle cx="${n.x.toFixed(1)}" cy="${n.y.toFixed(1)}" r="${n.size.toFixed(1)}" class="k-${n.link.reasons[0].kind}"/>
      <text x="${(n.x + dx).toFixed(1)}" y="${(n.y + dy).toFixed(1)}" text-anchor="${anchor}">${name}</text></g>`;
  }).join('');
  return `<svg class="link-graph" viewBox="0 0 ${w} ${h}" role="img" aria-label="${ctx.esc(vt(ctx.lang).linksTitle)}">${edges}${dots}
    <circle cx="${cx}" cy="${cy}" r="30" class="center"/><text x="${cx}" y="${cy + 4}" text-anchor="middle" class="center-label">${ctx.esc(ctx.name(iso3)).slice(0, 14)}</text></svg>`;
}

// ---------------------------------------------------------------------------- migration

function spark(values: number[]) {
  if (values.length < 2) return '';
  const max = Math.max(...values, 1), min = Math.min(...values, 0);
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * 120).toFixed(1)},${(26 - ((v - min) / (max - min || 1)) * 24).toFixed(1)}`).join(' ');
  return `<svg class="spark small" viewBox="0 0 120 28" aria-hidden="true"><polyline points="${pts}"/></svg>`;
}

export function migrationSection(ctx: ViewContext, iso3: string, data: LinksFile | undefined) {
  const d = vt(ctx.lang);
  const { esc, lang } = ctx;
  const head = `<div class="section-head"><h2>${d.migrationTitle}</h2></div>`;
  if (!data) return head + `<p class="muted-text">${d.unavailable}</p>`;
  const entry = data.countries[iso3] ?? {};
  const m = entry.migration;
  const cards: string[] = [];
  const list = (items: { iso3: string; n: number }[] = []) => `<ul class="mig-list">${items.slice(0, 6).map((x) =>
    `<li><button type="button" class="link" data-select="${x.iso3}">${esc(ctx.name(x.iso3))}</button><span>${formatPeople(x.n, lang)}</span></li>`).join('')}</ul>`;
  if (m?.hosted) {
    cards.push(`<article class="ctx"><h3>${d.hosted}</h3><p class="big">${formatPeople(m.hosted, lang)}</p>
      ${m.hosted_per_1000 !== undefined ? `<p class="muted-text small">${d.perThousand(num(m.hosted_per_1000, lang))}</p>` : ''}
      <h4 class="sub">${d.fromWhere}</h4>${list(m.hosted_from)}</article>`);
  }
  if (m?.abroad) {
    cards.push(`<article class="ctx"><h3>${d.abroad}</h3><p class="big">${formatPeople(m.abroad, lang)}</p>
      ${m.abroad_per_1000 !== undefined ? `<p class="muted-text small">${d.perThousand(num(m.abroad_per_1000, lang))}</p>` : ''}
      <h4 class="sub">${d.whereTo}</h4>${list(m.abroad_in)}</article>`);
  }
  if (m?.idps) cards.push(`<article class="ctx"><h3>${d.idps}</h3><p class="big">${formatPeople(m.idps, lang)}</p></article>`);
  if (m?.asylum_eu) {
    const a = m.asylum_eu;
    cards.push(`<article class="ctx"><h3>${d.asylumEu}</h3><p class="big">${formatPeople(a.last12, lang)}</p>${spark(a.values)}
      ${a.change !== null ? `<p class="muted-text small ${a.change > 0 ? 'up' : 'down'}">${d.vsPrev(signed(a.change * 100, lang) + '%')}</p>` : ''}</article>`);
  }
  if (entry.milex) {
    cards.push(`<article class="ctx"><h3>${d.milexTitle}</h3><p class="big">${num(entry.milex.value, lang)}%</p>${spark(entry.milex.series.map(([, v]) => v))}
      <p class="muted-text small">${d.milexNote(entry.milex.year, entry.milex.change5 === null ? '—' : signed(entry.milex.change5, lang))}</p></article>`);
  }
  const routes = data.routes.filter((r) => r.from.includes(iso3) || r.to.includes(iso3));
  if (routes.length) {
    cards.push(`<article class="ctx"><h3>${d.routesHere}</h3><ul class="plain">${routes.map((r) =>
      `<li><strong>${esc(lang === 'ru' ? r.ru : r.en)}</strong> — ${r.from.includes(iso3) ? d.routeFrom : d.routeTo}</li>`).join('')}</ul></article>`);
  }
  if (!cards.length) return head + `<p class="muted-text">${d.migrationNone}</p>`;
  return head + `<div class="ctx-grid">${cards.join('')}</div>${m?.year ? `<p class="muted-text small">${esc(d.unhcrNote(String(m.year)))}</p>` : ''}`;
}

export const migrationClass = (v: number | undefined) =>
  v === undefined ? '' : v >= 50 ? 'critical' : v >= 20 ? 'high' : v >= 5 ? 'elevated' : v >= 1 ? 'low' : 'minimal';

export function migrationPage(ctx: ViewContext, data: LinksFile | undefined, mode: 'hosted' | 'abroad') {
  const d = vt(ctx.lang);
  const { esc, lang } = ctx;
  const head = `<section class="page-head"><h1>${d.migPageTitle}</h1><p>${d.migPageLead}</p></section>`;
  if (!data) return head + `<div class="notice" role="status"><strong>${d.unavailable}</strong></div>`;
  const entries = Object.entries(data.countries).filter(([, c]) => c.migration);
  const top = (key: 'hosted' | 'abroad') => entries.filter(([, c]) => c.migration?.[key])
    .sort((a, b) => (b[1].migration![key] ?? 0) - (a[1].migration![key] ?? 0)).slice(0, 10)
    .map(([code, c]) => `<li><button type="button" class="link" data-select="${code}">${esc(ctx.name(code))}</button><span>${formatPeople(c.migration![key]!, lang)}</span></li>`).join('');
  const steps = [['minimal', '0'], ['low', '1'], ['elevated', '5'], ['high', '20'], ['critical', '50']];
  const eu = entries.filter(([, c]) => c.migration?.asylum_eu).sort((a, b) => b[1].migration!.asylum_eu!.last12 - a[1].migration!.asylum_eu!.last12);
  const euRows = eu.map(([code, c]) => {
    const a = c.migration!.asylum_eu!;
    return `<tr><th scope="row"><button type="button" class="link" data-select="${code}">${esc(ctx.name(code))}</button></th><td class="numcell">${a.last12.toLocaleString(lang === 'ru' ? 'ru-RU' : 'en-GB')}</td>
      <td class="numcell ${a.change !== null && a.change > 0 ? 'up' : 'down'}">${a.change === null ? '—' : signed(a.change * 100, lang) + '%'}</td><td>${spark(a.values)}</td></tr>`;
  }).join('');
  const routes = data.routes.map((r) => `<li><strong>${esc(lang === 'ru' ? r.ru : r.en)}</strong>
    <span>${r.from.map((c) => `<button type="button" class="link" data-select="${c}">${esc(ctx.name(c))}</button>`).join(', ')} → ${r.to.map((c) => `<button type="button" class="link" data-select="${c}">${esc(ctx.name(c))}</button>`).join(', ')}</span></li>`).join('');
  return head + `<div class="explorer"><section class="map-card">
      <div class="toolbar"><div class="segmented" role="group">${(['hosted', 'abroad'] as const).map((k) =>
        `<button type="button" data-migmode="${k}" aria-pressed="${k === mode}">${k === 'hosted' ? d.migMapHosted : d.migMapAbroad}</button>`).join('')}</div></div>
      <div class="map-stage" id="migration-map"><svg viewBox="0 0 900 440" role="img" tabindex="0" aria-label="${esc(d.migPageTitle)}"><g></g></svg>
        <div class="tooltip" hidden></div>
        <div class="map-controls"><button data-map="in" aria-label="+">+</button><button data-map="out" aria-label="−">−</button><button data-map="reset" aria-label="⟲">⟲</button></div></div>
      <div class="legend"><div class="legend-scale"><span class="legend-title">${d.migLegend}</span>
        <div class="ramp">${steps.map(([cls, label]) => `<span class="${cls}"><i></i><small>${label}</small></span>`).join('')}</div></div>
        <span class="legend-key"><i class="swatch-none"></i>${d.migNoData}</span></div></section>
    <aside class="brief"><h3 class="aside-title">${d.topHosts}</h3><ul class="mig-list">${top('hosted')}</ul><h3 class="aside-title">${d.topOrigins}</h3><ul class="mig-list">${top('abroad')}</ul></aside></div>
    ${euRows ? `<section class="section"><div class="section-head"><h2>${d.euTableTitle}</h2><p>${d.euTableLead}</p></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>${d.colCountry}</th><th>${d.colLast12}</th><th>${d.colChange}</th><th>${d.colTrend}</th></tr></thead><tbody>${euRows}</tbody></table></div></section>` : ''}
    <section class="section"><div class="section-head"><h2>${d.routesTitle}</h2><p>${d.routesLead}</p></div><ul class="routes">${routes}</ul></section>`;
}
