// Absolute danger level 1–5 (how dangerous it is here) and a separate trend arrow
// (whether it got worse than usual). Advice for every audience follows the level only.
import type { Lang } from './data';

export type DangerLevel = 1 | 2 | 3 | 4 | 5;
export interface DangerDriver {
  risk: string; class: 'A' | 'B' | 'C'; level: number; p12?: number; active?: boolean;
  intensity?: number; abroad?: boolean; regional?: boolean; regional_level?: number;
}
export interface DangerInfo {
  level: DangerLevel; model_level: number; drivers: DangerDriver[];
  ministries: { key: string; level: number; url?: string | null }[];
  ministry_median: number | null; raised_by_ministries: boolean; divergence: number | null;
  foreigners: { key: string; ru: string; en: string }[];
  trend: { direction: 'up' | 'flat' | 'down'; ratio: number; risk?: string | null };
}

interface LevelText { name: string; meaning: string; residents: string[]; travel: string[]; business: string[]; relocation: string[] }

const RU: Record<DangerLevel, LevelText> = {
  1: {
    name: 'Обычный',
    meaning: 'Серьёзных угроз для жизни и привычного уклада по имеющимся данным нет.',
    residents: ['Жить обычной жизнью.', 'Раз в год проверять документы и аптечку.'],
    travel: ['Обычные меры предосторожности.', 'Следить за рекомендациями МИД своей страны.'],
    business: ['Обычное планирование.', 'Иметь общий план на случай перебоев (поставки, связь, расчёты).'],
    relocation: ['Переезд можно планировать в обычном порядке.', 'Сравнить долгосрочные риски на 5 и 10 лет (ниже).'],
  },
  2: {
    name: 'Повышенный',
    meaning: 'Есть заметный риск тяжёлых событий или идут локальные конфликты. Жизнь в целом идёт обычно, но нужна подготовка.',
    residents: [
      'Проверить срок действия паспортов, держать копии документов в облаке.',
      'Держать запас воды, еды и лекарств на 3 дня, зарядки для телефона.',
      'Знать официальные каналы оповещения.',
    ],
    travel: [
      'Брать билеты с возможностью возврата и страховку, покрывающую отмену поездки.',
      'Зарегистрироваться в консульской системе своей страны, проверить, в какие регионы не стоит ехать.',
    ],
    business: [
      'Проверить план непрерывности: запасные поставщики, удалённая работа, резервные копии.',
      'Оценить долю выручки и поставок, завязанных на страну, и запас ликвидности.',
    ],
    relocation: [
      'Переезжать можно, но не сжигать мосты: сохранить жильё, счёт и документы для возвращения.',
      'Выбирать гибкий договор аренды, держать часть сбережений вне страны.',
    ],
  },
  3: {
    name: 'Высокий',
    meaning: 'Высокая вероятность событий, опасных для жизни или резко меняющих жизнь (война, переворот, тяжёлый кризис), или такие события уже идут.',
    residents: [
      'Собрать «тревожный рюкзак»: документы, наличные, лекарства, зарядки, вода на 3 дня.',
      'Договориться с близкими о месте встречи и связи без мобильной сети.',
      'Знать несколько маршрутов выезда, следить за официальными заявлениями каждый день.',
    ],
    travel: [
      'Отложить необязательные поездки.',
      'Если поездка нужна — иметь обратный билет и план выезда, следить за закрытием неба и границ.',
    ],
    business: [
      'Сократить запасы и платежи, завязанные на страну, перенести критичные данные и функции.',
      'Подготовить план эвакуации персонала, проверить страховку от политических рисков.',
    ],
    relocation: [
      'Отложить переезд, если он ещё не начат.',
      'Если вы уже переехали — держать «план Б»: куда и как уехать за 24–48 часов.',
    ],
  },
  4: {
    name: 'Очень высокий',
    meaning: 'Идёт война или крупный вооружённый конфликт, либо вероятность такого события очень высока.',
    residents: [
      'Если есть возможность — уехать из приграничных и стратегических районов.',
      'Выполнять указания властей, держать при себе документы и наличные.',
      'Не публиковать в сети фото и данные о военных объектах и передвижениях.',
    ],
    travel: [
      'Не ехать. Если вы на месте — уезжать, пока работают рейсы и пункты пропуска.',
      'Связаться с консульством, сообщить о своём местонахождении.',
    ],
    business: [
      'Эвакуировать персонал и семьи или не направлять их в страну.',
      'Перенести управление и расчёты за пределы страны, проверить санкционные ограничения.',
    ],
    relocation: ['Не переезжать.', 'Если вы уже там — выезжать по заранее подготовленному плану.'],
  },
  5: {
    name: 'Чрезвычайный',
    meaning: 'В регионе идут боевые действия с погибшими.',
    residents: ['Уходить из зоны боёв по безопасным маршрутам, выполнять указания властей.', 'Держаться укрытий во время обстрелов.'],
    travel: ['Не ехать ни при каких условиях.', 'Если вы на месте — немедленно связаться с консульством.'],
    business: ['Остановить деятельность в регионе, эвакуировать людей.'],
    relocation: ['Не переезжать.'],
  },
};

const EN: Record<DangerLevel, LevelText> = {
  1: {
    name: 'Normal',
    meaning: 'No serious threats to life or normal routines in the available data.',
    residents: ['Live normally.', 'Once a year, check documents and the first-aid kit.'],
    travel: ['Normal precautions.', "Follow your foreign ministry's advice."],
    business: ['Normal planning.', 'Keep a general plan for disruptions (supplies, communications, payments).'],
    relocation: ['A move can be planned as usual.', 'Compare long-term risks at 5 and 10 years (below).'],
  },
  2: {
    name: 'Elevated',
    meaning: 'There is a noticeable risk of severe events, or local conflicts are under way. Life goes on as usual, but preparation is wise.',
    residents: [
      'Check passport expiry dates and keep copies of documents in the cloud.',
      'Keep a 3-day supply of water, food and medicine, and phone chargers.',
      'Know the official alert channels.',
    ],
    travel: [
      'Buy refundable tickets and insurance that covers cancellation.',
      "Register with your country's consular service and check which regions to avoid.",
    ],
    business: [
      'Review the continuity plan: backup suppliers, remote work, backups.',
      'Check the share of revenue and supplies tied to the country and the liquidity buffer.',
    ],
    relocation: [
      "A move is possible, but don't burn bridges: keep housing, an account and documents for a return.",
      'Choose a flexible lease and keep part of your savings outside the country.',
    ],
  },
  3: {
    name: 'High',
    meaning: 'A high probability of events that threaten life or sharply disrupt it (war, coup, severe crisis), or such events are under way.',
    residents: [
      'Pack a grab bag: documents, cash, medicine, chargers, 3 days of water.',
      'Agree with family on a meeting place and a way to communicate without mobile networks.',
      'Know several exit routes and follow official statements daily.',
    ],
    travel: [
      'Postpone non-essential trips.',
      'If the trip is necessary, have a return ticket and an exit plan; watch for airspace and border closures.',
    ],
    business: [
      'Reduce inventory and payments tied to the country; move critical data and functions elsewhere.',
      'Prepare a staff evacuation plan and check political-risk insurance.',
    ],
    relocation: [
      'Postpone the move if it has not started.',
      'If you have moved, keep a plan B: where and how to leave within 24–48 hours.',
    ],
  },
  4: {
    name: 'Very high',
    meaning: 'A war or major armed conflict is under way, or the probability of one is very high.',
    residents: [
      'If you can, leave border and strategic areas.',
      'Follow official instructions; keep documents and cash on you.',
      "Don't post photos or details of military sites and movements online.",
    ],
    travel: ["Don't go. If you are there, leave while flights and border crossings work.", 'Contact your consulate and report your location.'],
    business: ['Evacuate staff and families or do not send them.', 'Move management and payments outside the country and check sanctions.'],
    relocation: ["Don't move.", 'If you are there, leave following the plan prepared in advance.'],
  },
  5: {
    name: 'Extreme',
    meaning: 'Fighting with fatalities is under way in the region.',
    residents: ['Leave the combat zone by safe routes and follow official instructions.', 'Stay in shelters during shelling.'],
    travel: ['Do not go under any circumstances.', 'If you are there, contact your consulate immediately.'],
    business: ['Stop operations in the region and evacuate people.'],
    relocation: ["Don't move."],
  },
};

const H = {
  ru: {
    title: 'Уровень опасности',
    residents: 'Жителям', travel: 'Путешественникам', business: 'Бизнесу', relocation: 'Переезжающим',
    drivers: 'Что определяет уровень',
    trend: { up: '↑ хуже обычного', flat: '→ как обычно', down: '↓ спокойнее обычного' },
    trendNote: 'Стрелка сравнивает текущий риск с обычным уровнем этой страны; на уровень опасности она не влияет.',
    war: (i?: number) => (i && i >= 2 ? 'идёт война (больше 1000 погибших в боях за год)' : 'идёт вооружённый конфликт (25–999 погибших в год)'),
    abroad: 'страна воюет за рубежом',
    regionalWar: 'идёт локально, в отдельных регионах',
    year: (p: string) => `${p} за 12 месяцев`,
    regional: 'Только в отдельных регионах (на уровень страны не влияет)',
    ministries: (m: string, n: number) => `Рекомендации МИД (${n}): нижняя медиана — ${m} из 4.`,
    raised: 'Уровень поднят на одну ступень по рекомендациям МИД.',
    divergenceUp: (m: number, x: number) => `МИД оценивают опасность выше (${m} из 4), чем наша модель (${x}). Часто это риски для иностранцев, которые модель не считает: задержания, терроризм, преступность.`,
    divergenceDown: (m: number, x: number) => `Наша модель оценивает опасность выше (${x}), чем МИД (${m} из 4).`,
    foreigners: 'Риски для иностранцев (по текстам МИД)',
    ministryNames: { us: 'Госдеп США', uk: 'МИД Великобритании', ca: 'МИД Канады', au: 'МИД Австралии', de: 'МИД Германии' } as Record<string, string>,
    scale: 'Шкала: 1 — обычный, 2 — повышенный, 3 — высокий, 4 — очень высокий, 5 — чрезвычайный (бои в регионе; бывает только у регионов, у страны в целом самый высокий уровень — 4). Уровень считается по самой тяжёлой угрозе; события разной тяжести имеют разные пороги.',
  },
  en: {
    title: 'Danger level',
    residents: 'Residents', travel: 'Travellers', business: 'Business', relocation: 'Relocating',
    drivers: 'What sets the level',
    trend: { up: '↑ worse than usual', flat: '→ as usual', down: '↓ calmer than usual' },
    trendNote: "The arrow compares current risk with this country's usual level; it does not change the danger level.",
    war: (i?: number) => (i && i >= 2 ? 'a war is under way (1,000+ battle deaths a year)' : 'an armed conflict is under way (25–999 deaths a year)'),
    abroad: 'the country fights abroad',
    regionalWar: 'local, in some regions',
    year: (p: string) => `${p} within 12 months`,
    regional: 'Only in some regions (does not change the country level)',
    ministries: (m: string, n: number) => `Foreign-ministry advice (${n}): lower median ${m} of 4.`,
    raised: 'The level is raised one step following foreign-ministry advice.',
    divergenceUp: (m: number, x: number) => `Foreign ministries rate the danger higher (${m} of 4) than our model (${x}). Often these are risks to foreigners the model does not measure: detention, terrorism, crime.`,
    divergenceDown: (m: number, x: number) => `Our model rates the danger higher (${x}) than foreign ministries (${m} of 4).`,
    foreigners: 'Risks to foreigners (from ministry texts)',
    ministryNames: { us: 'US State Department', uk: 'UK FCDO', ca: 'Global Affairs Canada', au: 'Australia DFAT', de: 'German Foreign Office' } as Record<string, string>,
    scale: 'Scale: 1 normal, 2 elevated, 3 high, 4 very high, 5 extreme (fighting in the region; only regions get it; for a whole country the highest level is 4). The level follows the most severe threat; events of different severity have different thresholds.',
  },
};

export const dangerName = (level: number, lang: Lang) => (lang === 'ru' ? RU : EN)[(Math.min(5, Math.max(1, level)) as DangerLevel)].name;
export const dangerTexts = (level: number, lang: Lang) => (lang === 'ru' ? RU : EN)[(Math.min(5, Math.max(1, level)) as DangerLevel)];

export function dangerBadge(level: number, lang: Lang) {
  return `<span class="danger-badge danger-${level}"><b>${level}</b>${dangerName(level, lang)}</span>`;
}

export function trendChip(info: DangerInfo, lang: Lang) {
  return `<span class="trend-chip trend-${info.trend.direction}" title="${H[lang].trendNote}">${H[lang].trend[info.trend.direction]}</span>`;
}

export function dangerCard(
  info: DangerInfo | null | undefined, lang: Lang, label: (k: string) => string,
  pct: (p: number) => string, esc: (s: string) => string,
) {
  if (!info) return '';
  const h = H[lang];
  const t = dangerTexts(info.level, lang);
  const list = (items: string[]) => `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>`;
  const main = info.drivers.filter((d) => !d.regional && d.level > 1).map((d) => {
    const what = d.active ? (d.abroad ? h.abroad : d.risk === 'internal_armed_conflict' && (d.intensity ?? 1) < 2 ? `${h.war(d.intensity)}, ${h.regionalWar}` : h.war(d.intensity)) : d.p12 !== undefined ? h.year(pct(d.p12)) : '';
    return `<li>${dangerBadge(d.level, lang)} ${esc(label(d.risk))}${what ? ': ' + esc(what) : ''}</li>`;
  });
  const regional = info.drivers.filter((d) => d.regional).map((d) => esc(label(d.risk)));
  const ministries = info.ministries.length
    ? `<p class="muted-text">${esc(h.ministries(String(info.ministry_median ?? '—'), info.ministries.length))} ${info.ministries.map((m) => m.url ? `<a href="${esc(m.url)}" rel="noreferrer">${esc(h.ministryNames[m.key] ?? m.key)}: ${m.level}</a>` : `${esc(h.ministryNames[m.key] ?? m.key)}: ${m.level}`).join(' · ')}</p>` : '';
  const notes = [
    info.raised_by_ministries ? h.raised : '',
    info.divergence !== null && info.ministry_median !== null
      ? (info.divergence > 0 ? h.divergenceUp(info.ministry_median, info.model_level) : h.divergenceDown(info.ministry_median, info.model_level)) : '',
  ].filter(Boolean).map((n) => `<p class="note-line">${esc(n)}</p>`).join('');
  const foreigners = info.foreigners.length
    ? `<p><b>${h.foreigners}:</b> ${info.foreigners.map((f) => esc(lang === 'ru' ? f.ru : f.en)).join(', ')}.</p>` : '';
  return `<section class="danger-card danger-l${info.level}" id="alert-card">
    <div class="danger-head"><h3>${h.title}: ${dangerBadge(info.level, lang)}</h3>${trendChip(info, lang)}</div>
    <p>${esc(t.meaning)}</p>
    ${main.length ? `<h4 class="sub">${h.drivers}</h4><ul class="driver-list">${main.join('')}</ul>` : ''}
    ${regional.length ? `<p class="muted-text"><b>${h.regional}:</b> ${regional.join(', ')}.</p>` : ''}
    ${ministries}${notes}${foreigners}
    <div class="alert-grid"><div><h4>${h.residents}</h4>${list(t.residents)}</div><div><h4>${h.travel}</h4>${list(t.travel)}</div>
    <div><h4>${h.business}</h4>${list(t.business)}</div><div><h4>${h.relocation}</h4>${list(t.relocation)}</div></div>
    <p class="muted-text small">${h.scale} ${h.trendNote}</p></section>`;
}
