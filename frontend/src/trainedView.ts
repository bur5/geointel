// Results of the trained base models' pre-registered forward validation.
import type { Lang } from './data';

interface TypeResult {
  decision: string; test_events?: number; test_years?: [number, number];
  brier?: { model: number; base_rate: number; persistence: number };
  bss_vs_base?: { value: number; ci95: [number, number] }; auc_pr?: { model: number | null; base_rate: number | null };
  note?: string;
}
export interface TrainedFile { generated_at: string; types: Record<string, TypeResult> }

const T = {
  ru: {
    title: 'Обученные модели: проверка «вперёд»',
    lead: 'Мы проверили, предсказывают ли модели с учётом режима, экономики, соседей и истории лучше текущих базовых частот. Правила проверки записаны заранее (docs/validation-rules.md): для каждого года с 2005-го модель учится только на прошлом и прогнозирует следующий год.',
    type: 'Тип события', events: 'Событий в проверке', bss: 'Выигрыш в точности (Brier skill score)', aucpr: 'Различение (AUC-PR): модель / база', decision: 'Решение',
    decisions: { 'switch on': 'Включена', 'keep base rate': 'Остаётся базовая частота', 'not enough data': 'Мало данных', 'no current data': 'Нет свежих данных', 'no data': 'Нет данных' } as Record<string, string>,
    names: { coup_attempt: 'Попытка переворота', internal_armed_conflict: 'Начало внутреннего конфликта', mass_protest: 'Массовые протесты (10 000+ человек)' } as Record<string, string>,
    explain: 'Модель включается только если выигрыш достоверно больше нуля (весь 95% интервал выше нуля). Пока ни одна не прошла: базовые частоты оказались сильным ориентиром, а данные о протестах заканчиваются 2020 годом. Это честный результат, а не сбой.',
  },
  en: {
    title: 'Trained models: forward validation',
    lead: 'We tested whether models using regime type, economy, neighbours and history predict better than the current base rates. The rules were written in advance (docs/validation-rules.md): for every year from 2005 the model learns only from the past and predicts the next year.',
    type: 'Event type', events: 'Test events', bss: 'Accuracy gain (Brier skill score)', aucpr: 'Discrimination (AUC-PR): model / base', decision: 'Decision',
    decisions: { 'switch on': 'Switched on', 'keep base rate': 'Base rate kept', 'not enough data': 'Not enough data', 'no current data': 'No current data', 'no data': 'No data' } as Record<string, string>,
    names: { coup_attempt: 'Coup attempt', internal_armed_conflict: 'Internal conflict onset', mass_protest: 'Mass protests (10,000+ people)' } as Record<string, string>,
    explain: 'A model is switched on only if the gain is reliably above zero (the whole 95% interval above zero). None has passed yet: base rates proved a strong benchmark, and protest data end in 2020. This is an honest result, not a failure.',
  },
};

export function trainedSection(file: TrainedFile | undefined, lang: Lang, esc: (s: string) => string) {
  if (!file) return '';
  const t = T[lang];
  const n = (v: number) => (v * 100).toFixed(1).replace('.', lang === 'ru' ? ',' : '.') + '%';
  const rows = Object.entries(file.types).map(([k, r]) => `<tr><th scope="row">${esc(t.names[k] ?? k)}</th>
    <td class="numcell">${r.test_events ?? '—'}${r.test_years ? ` <small>(${r.test_years[0]}–${r.test_years[1]})</small>` : ''}</td>
    <td class="numcell">${r.bss_vs_base ? `${n(r.bss_vs_base.value)} <small>(${n(r.bss_vs_base.ci95[0])} … ${n(r.bss_vs_base.ci95[1])})</small>` : '—'}</td>
    <td class="numcell">${r.auc_pr?.model != null && r.auc_pr?.base_rate != null ? `${r.auc_pr.model.toFixed(2)} / ${r.auc_pr.base_rate.toFixed(2)}` : '—'}</td>
    <td>${esc(t.decisions[r.decision] ?? r.decision)}</td></tr>`).join('');
  return `<section class="section"><div class="section-head"><h2>${t.title}</h2><p>${t.lead}</p></div>
    <div class="table-wrap"><table class="table"><thead><tr><th>${t.type}</th><th>${t.events}</th><th>${t.bss}</th><th>${t.aucpr}</th><th>${t.decision}</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted-text">${t.explain}</p></section>`;
}
