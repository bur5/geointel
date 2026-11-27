// Plain-language explanations of a probability: "1 in N", compared with the typical country,
// how it accumulates over time, and what the event would mean in this sphere.
import type { Lang } from './data';

type Sphere = 'conflict' | 'natural' | 'society';

const MEANING: Record<string, { ru: string; en: string }> = {
  internal_armed_conflict: { ru: 'бои внутри страны с не менее чем 25 погибшими за год; обычно в отдельных регионах, а не везде', en: 'fighting inside the country with at least 25 deaths in a year; usually in some regions, not everywhere' },
  interstate_conflict: { ru: 'вооружённое столкновение с другим государством; удары могут затронуть и тыловые города', en: 'armed clashes with another state; strikes may reach cities far from the front' },
  coup_attempt: { ru: 'попытка военных или элит захватить власть; на дни возможны комендантский час, закрытые аэропорты и отключение связи', en: 'an attempt by the military or elites to seize power; curfews, closed airports and cut communications for days are possible' },
  mass_protest: { ru: 'протест против правительства более чем на 10 000 человек; чаще всего — перекрытые улицы в столице, реже — столкновения', en: 'a protest against the government of more than 10,000 people; usually blocked streets in the capital, sometimes clashes' },
  economic_crisis: { ru: 'резкий спад или скачок цен; для жителя — рост цен, для бизнеса — валютные и платёжные риски', en: 'a sharp contraction or price surge; for residents rising prices, for business currency and payment risks' },
  humanitarian_crisis: { ru: 'кризис, на который ООН объявляет призыв о помощи; нехватка еды, лекарств или жилья у части населения', en: 'a crisis with a UN appeal for aid; shortages of food, medicine or shelter for part of the population' },
};
const SPHERE_MEANING: Record<Sphere, { ru: string; en: string }> = {
  conflict: { ru: 'вооружённое насилие', en: 'armed violence' },
  natural: { ru: 'стихийное бедствие; оно бьёт по отдельным регионам, а не по всей стране', en: 'a natural hazard; it strikes particular regions, not the whole country' },
  society: { ru: 'кризис в обществе или экономике', en: 'a crisis in society or the economy' },
};

export function oneIn(p: number, lang: Lang): string {
  if (p >= 0.995) return lang === 'ru' ? 'почти наверняка' : 'almost certain';
  if (p >= 0.5) {
    const odds = Math.round((p / (1 - p)) * 10) / 10;
    return lang === 'ru' ? `скорее да, чем нет (примерно ${String(odds).replace('.', ',')} к 1)` : `more likely than not (about ${odds} to 1)`;
  }
  if (p <= 0.0005) return lang === 'ru' ? 'меньше 1 шанса из 2000' : 'less than 1 in 2,000';
  const n = 1 / p;
  const round = n < 10 ? Math.round(n * 2) / 2 : n < 100 ? Math.round(n) : Math.round(n / 10) * 10;
  const text = String(round).replace('.', lang === 'ru' ? ',' : '.');
  return lang === 'ru' ? `примерно 1 шанс из ${text}` : `about 1 in ${text}`;
}

function everyday(p: number, lang: Lang): string {
  // Familiar reference odds, chosen by size; all are exact probabilities.
  const refs: [number, string, string][] = [
    [0.5, 'выпадение орла при броске монеты (50%)', 'a coin landing heads (50%)'],
    [1 / 6, 'выпадение шестёрки на кубике (17%)', 'rolling a six on a die (17%)'],
    [1 / 36, 'две шестёрки подряд на кубике (2,8%)', 'two sixes in a row on a die (2.8%)'],
    [1 / 216, 'три шестёрки подряд (0,5%)', 'three sixes in a row (0.5%)'],
    [1 / 1296, 'четыре шестёрки подряд (0,08%)', 'four sixes in a row (0.08%)'],
  ];
  let best = refs[0];
  for (const r of refs) if (Math.abs(Math.log(p) - Math.log(r[0])) < Math.abs(Math.log(p) - Math.log(best[0]))) best = r;
  return lang === 'ru' ? `по порядку величины как ${best[1]}` : `roughly as likely as ${best[2]}`;
}

export function explain(opts: {
  key: string; sphere: Sphere; p: number; horizonLabel: string; median: number | null;
  p10: number | null; active: boolean; lang: Lang;
}): string[] {
  const { key, sphere, p, horizonLabel, median, p10, active, lang } = opts;
  const ru = lang === 'ru';
  const lines: string[] = [];
  if (active) {
    lines.push(ru ? `Событие уже идёт: цифра — вероятность, что оно будет продолжаться в конце срока (${horizonLabel.toLowerCase()}).` : `The event is already under way: the figure is the chance it is still going at the end of the period (${horizonLabel.toLowerCase()}).`);
  }
  lines.push(ru ? `${horizonLabel}: ${oneIn(p, lang)}; ${everyday(p, lang)}.` : `${horizonLabel}: ${oneIn(p, lang)}; ${everyday(p, lang)}.`);
  if (median !== null && median > 0) {
    const ratio = p / median;
    const fmt = (x: number) => (x >= 10 ? Math.round(x).toString() : (Math.round(x * 10) / 10).toString().replace('.', ru ? ',' : '.'));
    const raz = (x: number) => {
      const text = fmt(x);
      if (text.includes(',') || text.includes('.')) return `${text} раза`;
      const n = Number(text);
      return `${text} ${n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'раза' : 'раз'}`;
    };
    lines.push(ratio >= 1.5
      ? (ru ? `Это в ${raz(ratio)} выше, чем у типичной страны мира (медиана ${pctText(median, lang)}).` : `That is ${fmt(ratio)} times the typical country (median ${pctText(median, lang)}).`)
      : ratio <= 1 / 1.5
        ? (ru ? `Это в ${raz(1 / ratio)} ниже, чем у типичной страны мира (медиана ${pctText(median, lang)}).` : `That is ${fmt(1 / ratio)} times lower than the typical country (median ${pctText(median, lang)}).`)
        : (ru ? `Примерно как у типичной страны мира (медиана ${pctText(median, lang)}).` : `About the same as the typical country (median ${pctText(median, lang)}).`));
  }
  if (p10 !== null && !active && p10 > p * 1.5) {
    lines.push(ru ? `Риск накапливается: за 10 лет шанс хотя бы одного такого события — ${pctText(p10, lang)}.` : `Risk accumulates: over 10 years the chance of at least one such event is ${pctText(p10, lang)}.`);
  }
  const meaning = MEANING[key] ?? SPHERE_MEANING[sphere];
  lines.push(ru ? `Что это значит на деле: ${meaning.ru}.` : `What it means in practice: ${meaning.en}.`);
  return lines;
}

function pctText(p: number, lang: Lang) {
  const v = p * 100;
  const s = v < 1 ? v.toFixed(1) : Math.round(v).toString();
  return (lang === 'ru' ? s.replace('.', ',') : s) + '%';
}
