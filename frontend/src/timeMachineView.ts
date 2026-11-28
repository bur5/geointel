// Results of the time machine for the base model (docs/backtest-rules.md).
import type { Lang } from './data';

type Skill = [number, number, number] | null;
interface Summary { n: number; events: number; brier: number; bss_vs_base?: Skill; bss_vs_world: Skill; bss_vs_last_year: Skill }
interface DangerCheck { levels: Record<string, { n: number; rate: number }>; order_ok: boolean; band_level3: { n: number; rate: number; low: number; high: number; promised: [number, number]; inside: boolean } | null }
export interface TimeMachineFile {
  generated_at: string; model_version: string; holdout_opened: boolean;
  periods: Record<string, [number, number]>;
  types: Record<string, { lag_years: number; periods: Record<string, Record<string, Summary>> }>;
  danger: Record<string, DangerCheck>;
}

const NAMES: Record<string, [string, string]> = {
  internal_armed_conflict: ['Внутренний вооружённый конфликт', 'Internal armed conflict'],
  interstate_conflict: ['Межгосударственный конфликт', 'Interstate conflict'],
  coup_attempt: ['Попытка переворота', 'Coup attempt'],
  mass_protest: ['Массовые протесты', 'Mass protests'],
  major_earthquake: ['Сильное землетрясение', 'Major earthquake'],
  tsunami: ['Цунами', 'Tsunami'],
  economic_crisis: ['Экономический кризис', 'Economic crisis'],
  humanitarian_crisis: ['Гуманитарный кризис', 'Humanitarian crisis'],
};
const STATES: Record<string, [string, string]> = {
  onset: ['начало', 'onset'], continuation: ['продолжение', 'continuation'], all: ['', ''],
};

export interface HoldoutFile extends TimeMachineFile { holdout_views?: number }

export function timeMachineSection(file: TimeMachineFile | undefined, lang: Lang, esc: (s: string) => string, holdout?: HoldoutFile) {
  if (!file) return '';
  const ru = lang === 'ru';
  const pct = (v: number) => (v * 100).toFixed(1).replace('.', ru ? ',' : '.') + '%';
  const cell = (b: [number, number, number] | null) => {
    if (!b) return '—';
    const cls = b[1] > 0 ? 'up-good' : b[2] < 0 ? 'down-bad' : '';
    return `<span class="${cls}">${pct(b[0])}</span> <small>(${pct(b[1])} … ${pct(b[2])})</small>`;
  };
  const period = 'validation';
  const [lo, hi] = file.periods[period] ?? [0, 0];
  // Primary reference (Fable round 5): onset is compared with how often conflicts start among
  // countries at peace, continuation with how often they go on among countries at war; other
  // events with the world frequency. The world frequency for onset/continuation is shown only
  // for reference: it is an easy opponent there.
  const primary = (s: Summary | undefined) => (s ? (s.bss_vs_base ?? s.bss_vs_world) : null);
  const rows = Object.entries(file.types).flatMap(([key, t]) => Object.entries(t.periods[period] ?? {}).map(([state, s]) => {
    const name = (NAMES[key] ?? [key, key])[ru ? 0 : 1];
    const st = (STATES[state] ?? ['', ''])[ru ? 0 : 1];
    const h = holdout?.types?.[key]?.periods?.holdout?.[state];
    const ref = state === 'all' ? '—' : cell(s.bss_vs_world);
    return `<tr><th scope="row">${esc(name)}${st ? ` <small>(${esc(st)})</small>` : ''}</th><td class="numcell">${s.events} / ${s.n}</td><td class="numcell">${cell(primary(s))}</td><td class="numcell">${h ? cell(primary(h)) : '—'}</td><td class="numcell muted-text">${ref}</td></tr>`;
  })).join('');
  const d = file.danger[period];
  const levels = d ? Object.entries(d.levels).map(([l, v]) => `${ru ? 'уровень' : 'level'} ${l}: ${pct(v.rate)} <small>(n=${v.n})</small>`).join(' · ') : '';
  const band = d?.band_level3;
  return `<section class="section"><div class="section-head"><h2>${ru ? '«Машина времени»: проверка базовой модели на прошлом' : 'Time machine: the base model tested on the past'}</h2>
    <p>${ru ? `Для каждого года модель видит только данные, опубликованные к 1 января этого года, и прогнозирует события этого года. Правила записаны заранее (docs/backtest-rules.md). Ниже — период проверки ${lo}–${hi}; отложенный период 2021–2025 ${file.holdout_opened ? 'открыт' : 'ещё не открывался'}.` : `For every year the model sees only data published by 1 January of that year and forecasts that year's events. Rules were written in advance (docs/backtest-rules.md). Below: the validation period ${lo}–${hi}; the 2021–2025 holdout ${file.holdout_opened ? 'has been opened' : 'has not been opened yet'}.`}</p></div>
    <div class="table-wrap"><table class="table"><thead><tr><th>${ru ? 'Тип события' : 'Event type'}</th><th>${ru ? 'Событий / прогнозов' : 'Events / forecasts'}</th><th>${ru ? `Лучше простого правила, ${lo}–${hi}` : `Better than a simple rule, ${lo}–${hi}`}</th><th>${ru ? 'То же, контроль 2021–2025' : 'Same, control 2021–2025'}</th><th>${ru ? 'Против средней по миру (справочно)' : 'Against the world average (reference)'}</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted-text small">${ru ? 'Выигрыш в точности (Brier skill score) с 95% интервалом по странам и годам: больше нуля — модель лучше простого правила, меньше нуля — хуже. Простое правило: для начала конфликта — как часто конфликты начинаются среди мирных стран; для продолжения — как часто продолжаются среди воюющих; для остальных событий — средняя частота по миру. До 28.11.2026 мы сравнивали начало и продолжение со средней по миру, и это завышало выигрыш; та цифра оставлена справочно. Отрицательные результаты показаны как есть.' : 'Accuracy gain (Brier skill score) with a 95% interval over countries and years: above zero the model beats a simple rule, below zero it is worse. The simple rule: for onset, how often conflicts start among countries at peace; for continuation, how often they go on among countries at war; for other events, the world frequency. Until 28 Nov 2026 onset and continuation were compared with the world average, which overstated the gain; that number is kept for reference. Negative results are shown as they are.'}</p>
    ${holdout ? `<p class="muted-text small">${ru ? `Контрольный период 2021–2025 открыт 28.11.2026; просмотров: ${holdout.holdout_views ?? 1}. По нему варианты модели не выбирают: новая версия не должна быть на нём хуже прежней.` : `The 2021–2025 control period was opened on 28 Nov 2026; views: ${holdout.holdout_views ?? 1}. Model variants are not chosen on it: a new version must not be worse on it than the previous one.`}</p>` : ''}
    ${d ? `<h3>${ru ? 'Уровень опасности (только войны, без МИД и новостей)' : 'Danger level (wars only, without ministries and news)'}</h3>
    <p>${ru ? 'Доля стран, где в следующем году шёл вооружённый конфликт:' : 'Share of countries with an armed conflict in the next year:'} ${levels}. ${d.order_ok ? (ru ? 'Доля растёт с уровнем, как и должна.' : 'It rises with the level, as it should.') : (ru ? 'Доля растёт с уровнем не везде — это нужно исправить.' : 'It does not rise with every level — this needs fixing.')}</p>
    ${band ? `<p>${ru ? `Уровень 3 обещает 5–20% в год; на деле ${pct(band.rate)} (${pct(band.low)}–${pct(band.high)}), ${band.inside ? 'в пределах обещанного' : 'вне обещанного'}.` : `Level 3 promises 5–20% a year; observed ${pct(band.rate)} (${pct(band.low)}–${pct(band.high)}), ${band.inside ? 'within the promise' : 'outside the promise'}.`}</p>` : ''}` : ''}
  </section>`;
}
