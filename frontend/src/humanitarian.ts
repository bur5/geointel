// Humanitarian crisis: category and severity (INFORM Severity Index) and what it means
// for residents, travellers, business and people relocating.
import type { Lang } from './data';

export interface Severity { score: number; category: string; crisis: string; impact: number | null; conditions: number | null; complexity: number | null }

type Band = 1 | 2 | 3 | 4;
// INFORM Severity: index 0–10, category 1 (very low) – 5 (very high). The band follows the
// category; without it, the index (≥8 very high, ≥6 high, ≥4 medium).
const band = (s: Severity): Band => {
  const cat = parseInt(s.category, 10);
  if (cat >= 1 && cat <= 5) return (cat >= 5 ? 4 : cat === 4 ? 3 : cat === 3 ? 2 : 1) as Band;
  return s.score >= 8 ? 4 : s.score >= 6 ? 3 : s.score >= 4 ? 2 : 1;
};

const T = {
  ru: {
    title: 'Гуманитарная ситуация',
    lead: (crisis: string, score: string, cat: string) => `Самый тяжёлый текущий кризис: «${crisis}». Индекс тяжести INFORM: ${score} из 10 (категория ${cat} из 5).`,
    dims: 'Из чего складывается',
    impact: 'Масштаб последствий', conditions: 'Условия жизни людей', complexity: 'Сложность (доступ, безопасность)',
    bands: ['', 'Низкая тяжесть', 'Умеренная тяжесть', 'Высокая тяжесть', 'Очень высокая тяжесть'],
    meaning: [
      '',
      'Кризис локальный: помощь нужна ограниченному числу людей, основные службы работают.',
      'Заметная часть населения нуждается в помощи; в затронутых районах перебои с водой, медициной, жильём.',
      'Большие группы людей лишены базовых услуг; возможны вспышки болезней, нехватка еды и лекарств.',
      'Катастрофическая ситуация: массовые потребности, голод или угроза голода, разрушенная инфраструктура, ограниченный доступ помощи.',
    ],
    who: { residents: 'Жителям', travel: 'Путешественникам', business: 'Бизнесу', relocation: 'Переезжающим' },
    advice: {
      residents: ['', 'Следить за сообщениями властей в затронутых районах.', 'Держать запас воды, еды и лекарств; знать, где получить помощь.', 'Запас на 2 недели, документы под рукой; при возможности — уехать из затронутых районов.', 'Выполнять указания гуманитарных организаций и властей; при возможности — покинуть зону кризиса.'],
      travel: ['', 'Обычные меры; проверить, не затронут ли маршрут.', 'Избегать затронутых районов; страховка с медицинской эвакуацией.', 'Ехать только при необходимости; медпомощь может быть недоступна, страховка может не покрывать.', 'Не ехать, кроме гуманитарных и неотложных целей.'],
      business: ['', 'Учесть возможные перебои в затронутых районах.', 'Запасные поставщики и маршруты; оценить риски для персонала.', 'Охрана, план эвакуации, проверка санкционных и репутационных рисков.', 'Свернуть необязательную деятельность; приоритет — безопасность людей.'],
      relocation: ['', 'На выбор места внутри страны влияет мало.', 'Выбирать незатронутые регионы; проверить доступ к медицине.', 'Переезд не рекомендуется без веской причины.', 'Не переезжать.'],
    },
    source: 'Источник: INFORM Severity Index (Объединённый исследовательский центр Еврокомиссии), ежемесячно.',
  },
  en: {
    title: 'Humanitarian situation',
    lead: (crisis: string, score: string, cat: string) => `Most severe current crisis: "${crisis}". INFORM severity: ${score} of 10 (category ${cat} of 5).`,
    dims: 'What it is made of',
    impact: 'Scale of impact', conditions: "People's living conditions", complexity: 'Complexity (access, security)',
    bands: ['', 'Low severity', 'Moderate severity', 'High severity', 'Very high severity'],
    meaning: [
      '',
      'A local crisis: a limited number of people need help, basic services work.',
      'A noticeable share of people need help; affected areas lack water, health care or shelter.',
      'Large groups lack basic services; disease outbreaks and shortages of food and medicine are possible.',
      'Catastrophic: massive needs, famine or risk of famine, destroyed infrastructure, limited aid access.',
    ],
    who: { residents: 'Residents', travel: 'Travellers', business: 'Business', relocation: 'Relocating' },
    advice: {
      residents: ['', 'Follow official notices in affected areas.', 'Keep water, food and medicine; know where to get help.', 'Two weeks of supplies, documents at hand; leave affected areas if you can.', 'Follow humanitarian agencies and authorities; leave the crisis area if you can.'],
      travel: ['', 'Normal precautions; check whether your route is affected.', 'Avoid affected areas; insurance with medical evacuation.', 'Only if necessary; medical help may be unavailable and insurance may not cover it.', "Don't go except for humanitarian or urgent purposes."],
      business: ['', 'Allow for disruptions in affected areas.', 'Backup suppliers and routes; assess risks to staff.', 'Security, evacuation plan, sanctions and reputational checks.', 'Wind down non-essential operations; people first.'],
      relocation: ['', 'Little effect on where to live in the country.', 'Choose unaffected regions; check access to health care.', 'A move is not advised without a strong reason.', "Don't move."],
    },
    source: 'Source: INFORM Severity Index (European Commission Joint Research Centre), monthly.',
  },
};

export function humanitarianCard(s: Severity | null | undefined, lang: Lang, esc: (x: string) => string) {
  if (!s) return '';
  const t = T[lang];
  const b = band(s);
  const num = (v: number) => (Math.round(v * 10) / 10).toString().replace('.', lang === 'ru' ? ',' : '.');
  const dims = ([['impact', s.impact], ['conditions', s.conditions], ['complexity', s.complexity]] as const)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `<li>${t[k]}: <b>${num(v as number)}</b> / 10</li>`).join('');
  const col = (k: keyof typeof t.who) => `<div><h4>${t.who[k]}</h4><p>${esc(t.advice[k][b])}</p></div>`;
  return `<section class="hum-card hum-${b}" id="humanitarian"><h3>${t.title}: ${t.bands[b]}</h3>
    <p>${esc(t.lead(s.crisis || '—', num(s.score), s.category || t.bands[b]))}</p><p>${esc(t.meaning[b])}</p>
    ${dims ? `<h4 class="sub">${t.dims}</h4><ul>${dims}</ul>` : ''}
    <div class="alert-grid">${col('residents')}${col('travel')}${col('business')}${col('relocation')}</div>
    <p class="muted-text small">${t.source}</p></section>`;
}
