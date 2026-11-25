// "Lenses": short theses from the research literature on war, coups and forecasting (written in
// our own words, no quotations), each tied to what GeoIntel measures; plus an expert
// questionnaire that produces a block of text the Owner can send back to be added as a source.
import type { ScenarioFile } from './data';
import type { ViewContext } from './views';

interface Lens {
  author: string; work: string; year: number;
  ru: string; en: string; useRu: string; useEn: string;
}

const LENSES: Lens[] = [
  { author: 'James Fearon', work: 'Rationalist Explanations for War', year: 1995,
    ru: 'Война дорога для обеих сторон, поэтому почти всегда существует сделка лучше войны. Сделка срывается по трём причинам: стороны скрывают свою силу и решимость, не могут поверить обещаниям друг друга, когда баланс сил меняется, или спорят о неделимом.',
    en: 'War is costly to both sides, so a deal better than war almost always exists. Deals fail for three reasons: each side hides its strength and resolve, neither can trust promises when the balance of power is shifting, or the stake cannot be divided.',
    useRu: 'Маскировка и дезинформация считаются сильными признаками; дерево «Россия–НАТО» учитывает сдвиг баланса сил после прекращения огня.',
    useEn: 'Masking and deception count as strong signs; the Russia–NATO tree models the shift in the balance of power after a ceasefire.' },
  { author: 'Geoffrey Blainey', work: 'The Causes of War', year: 1973,
    ru: 'Войны начинаются, когда стороны по-разному оценивают, кто сильнее, и заканчиваются, когда бои убеждают их в одном и том же ответе.',
    en: 'Wars begin when the sides disagree about who is stronger and end when fighting convinces them of the same answer.',
    useRu: 'Учения, рост военных расходов и риторика о «слабости» противника — признаки расхождения в оценках силы.',
    useEn: 'Exercises, rising military spending and rhetoric about an opponent\'s "weakness" are signs of diverging estimates of strength.' },
  { author: 'Stephen Van Evera; Dale Copeland', work: 'Causes of War; The Origins of Major War', year: 1999,
    ru: '«Окна возможностей»: государство склонно действовать, пока его относительное преимущество не исчезло. Риск растёт, когда одна сторона видит, что скоро станет слабее.',
    en: '"Windows of opportunity": a state is tempted to act before its relative advantage disappears. Risk rises when one side sees that it will soon be weaker.',
    useRu: 'Поэтому риск в дереве «Россия–НАТО» растёт к концу 2020-х, но рост урезан: Европа перевооружается и окно сужается.',
    useEn: 'This is why risk in the Russia–NATO tree rises towards the late 2020s, with the rise trimmed because Europe is rearming and the window is narrowing.' },
  { author: 'John Mearsheimer', work: 'Conventional Deterrence', year: 1983,
    ru: 'Обычное сдерживание проваливается, когда нападающий верит в быструю и дешёвую победу. Затяжная война на истощение отпугивает сильнее.',
    en: 'Conventional deterrence fails when the attacker believes in a quick, cheap victory. The prospect of a long war of attrition deters more strongly.',
    useRu: 'Передовые силы НАТО в Прибалтике считаются сдерживающим признаком (снижает риск), а их сокращение — ослаблением гарантий.',
    useEn: 'NATO forward forces in the Baltics count as a deterrence sign (lowering risk); cutting them counts as weaker guarantees.' },
  { author: 'Thomas Schelling', work: 'Arms and Influence', year: 1966,
    ru: 'Принуждение работает через риск, который никто полностью не контролирует: провокации и инциденты повышают шанс случайной эскалации, даже если войны никто не хочет.',
    en: 'Coercion works through risk that no one fully controls: provocations and incidents raise the chance of accidental escalation even if no one wants war.',
    useRu: 'Нарушения воздушного пространства, диверсии и порча кабелей учитываются как гибридные признаки, но со слабым весом.',
    useEn: 'Airspace violations, sabotage and cable damage count as hybrid signs, but with a low weight.' },
  { author: 'Robert Jervis', work: 'Perception and Misperception in International Politics', year: 1976,
    ru: 'Лидеры склонны видеть в оборонительных шагах соседа подготовку к нападению — «дилемма безопасности» разгоняет напряжённость с обеих сторон.',
    en: 'Leaders tend to read a neighbour\'s defensive steps as preparation for attack — the "security dilemma" winds up tension on both sides.',
    useRu: 'Сдерживание снижает риск лишь умеренно (×0,85), потому что может вызвать ответное наращивание.',
    useEn: 'Deterrence lowers risk only moderately (×0.85) because it can trigger a counter-build-up.' },
  { author: 'Richard Betts; Cynthia Grabo', work: 'Surprise Attack; Anticipating Surprise', year: 1982,
    ru: 'Внезапные нападения почти никогда не бывают без признаков: войска, логистика, медицина и мобилизация видны заранее. Провал обычно в том, что признакам не верят.',
    en: 'Surprise attacks almost never come without signs: troops, logistics, medical preparations and mobilisation are visible in advance. The failure is usually disbelief.',
    useRu: 'Основа слоя предупреждающих признаков: группы «войска», «люди», «логистика», «последние признаки» и множитель за совпадение нескольких групп.',
    useEn: 'The basis of the warning-sign layer: the forces, people, logistics and final-sign groups and the extra factor when several groups coincide.' },
  { author: 'Philip Tetlock, Dan Gardner', work: 'Superforecasting', year: 2015,
    ru: 'Лучшие прогнозисты начинают с базовой частоты похожих событий, затем понемногу поправляют её по новым данным, дают точные вероятности и проверяют себя по итогам.',
    en: 'The best forecasters start from the base rate of similar events, then adjust it in small steps as evidence arrives, give precise probabilities and score themselves afterwards.',
    useRu: 'Сначала базовая частота, потом ограниченные множители признаков, потом проверка на странице «Точность».',
    useEn: 'Base rate first, then bounded sign factors, then scoring on the Accuracy page.' },
  { author: 'John Londregan, Keith Poole', work: 'Poverty, the Coup Trap, and the Seizure of Executive Power', year: 1990,
    ru: '«Ловушка переворотов»: где недавно был переворот, следующий намного вероятнее; бедность усиливает эффект.',
    en: 'The "coup trap": where a coup happened recently, another is far more likely; poverty strengthens the effect.',
    useRu: 'Сценарий по Сахелю начинается с частоты переворотов с 2012 года, а свежая попытка или раскол в армии повышают оценку (признак «раскол элит»).',
    useEn: 'The Sahel scenario starts from the coup rate since 2012, and a fresh attempt or a split in the army raises it (the "elite split" sign).' },
  { author: 'Jack Goldstone et al.', work: 'A Global Model for Forecasting Political Instability', year: 2010,
    ru: 'Нестабильность лучше всего предсказывают тип режима (особенно частичные демократии с острой фракционной борьбой), детская смертность, войны у соседей и дискриминация со стороны государства.',
    en: 'Instability is best predicted by regime type (especially partial democracies with sharp factionalism), infant mortality, wars in neighbouring states and state-led discrimination.',
    useRu: 'Данные V-Dem о режимах и войны у соседей входят в базовые оценки политического кризиса.',
    useEn: 'V-Dem regime data and wars in neighbouring states feed the base estimates of political crisis.' },
  { author: 'James Fearon, David Laitin', work: 'Ethnicity, Insurgency, and Civil War', year: 2003,
    ru: 'Гражданские войны чаще начинаются там, где повстанцам легко воевать: слабое государство, бедность, горы, большое население, — а не там, где больше всего обид.',
    en: 'Civil wars start more often where rebellion is feasible — a weak state, poverty, mountains, a large population — than where grievances are greatest.',
    useRu: 'Протесты сами по себе слабо повышают риск внутренней войны; сильнее — признаки слабости государства и раскола силовиков.',
    useEn: 'Protests alone raise the risk of internal war only a little; signs of a weak state and a split security apparatus matter more.' },
];

const ru = {
  title: 'Линзы и анкета эксперта',
  lead: 'Какие идеи из исследований войн, переворотов и прогнозирования заложены в модель, и как эксперт может дать свою оценку. Тезисы пересказаны своими словами; читайте первоисточники.',
  lensesTitle: 'Линзы: что мы берём из литературы',
  inModel: 'Как это используется',
  formTitle: 'Анкета экспертной оценки',
  formLead: 'Если вы специалист по региону или военному делу, дайте свою вероятность по сценариям. Ответ остаётся у вас в браузере: нажмите «Подготовить ответ» и отправьте текст владельцу сайта. После проверки он войдёт в расчёт как отдельный источник «панель экспертов» с указанием, сколько человек ответили.',
  name: 'Как вас указать (можно анонимно)',
  field: 'Область экспертизы',
  scenario: 'Сценарий', p1y: 'Вероятность за год, %', p5y: 'Вероятность за 5 лет, %', confidence: 'Уверенность', why: 'Главная причина оценки',
  conf: ['низкая', 'средняя', 'высокая'],
  prepare: 'Подготовить ответ', copied: 'Текст скопирован. Отправьте его владельцу сайта.', notCopied: 'Скопируйте текст вручную.',
  noScenarios: 'Список сценариев ещё загружается.',
  method: 'Как ответы войдут в расчёт: вероятности переводятся в годовые, объединяются средним геометрическим, вес источника — 1 (как у экспертной оценки GeoIntel). Ответы без пояснения не учитываются.',
};
type Dict = typeof ru;
const en: Dict = {
  title: 'Lenses and expert questionnaire',
  lead: 'Which ideas from research on war, coups and forecasting are built into the model, and how an expert can give their own estimate. Theses are summarised in our own words; read the originals.',
  lensesTitle: 'Lenses: what we take from the literature',
  inModel: 'How it is used',
  formTitle: 'Expert questionnaire',
  formLead: 'If you are a regional or military specialist, give your probability for the scenarios. Your answer stays in your browser: press "Prepare answer" and send the text to the site owner. After review it enters the calculation as a separate "expert panel" source, stating how many people answered.',
  name: 'How to credit you (anonymous is fine)',
  field: 'Field of expertise',
  scenario: 'Scenario', p1y: 'Probability within a year, %', p5y: 'Probability within 5 years, %', confidence: 'Confidence', why: 'Main reason for the estimate',
  conf: ['low', 'medium', 'high'],
  prepare: 'Prepare answer', copied: 'Text copied. Send it to the site owner.', notCopied: 'Copy the text by hand.',
  noScenarios: 'The scenario list is still loading.',
  method: 'How answers enter the calculation: probabilities are converted to yearly ones, combined by geometric mean, and the source gets weight 1 (like the GeoIntel expert estimate). Answers without a reason are not used.',
};
const lt = (lang: string) => (lang === 'ru' ? ru : en);

export function lensesPage(ctx: ViewContext, scenarios: ScenarioFile | undefined) {
  const d = lt(ctx.lang);
  const lenses = LENSES.map((l) => `<article class="lens"><h3>${ctx.esc(l.author)}, <cite>${ctx.esc(l.work)}</cite> (${l.year})</h3>
    <p>${ctx.esc(ctx.lang === 'ru' ? l.ru : l.en)}</p><p class="muted-text"><strong>${d.inModel}:</strong> ${ctx.esc(ctx.lang === 'ru' ? l.useRu : l.useEn)}</p></article>`).join('');
  const rows = scenarios ? scenarios.scenarios.map((s) => `<tr data-survey="${s.key}"><th scope="row">${ctx.esc(ctx.lang === 'ru' ? s.title_ru : s.title_en)}</th>
    <td><input type="number" min="0" max="100" step="0.1" name="p1y" aria-label="${d.p1y}"></td>
    <td><input type="number" min="0" max="100" step="0.1" name="p5y" aria-label="${d.p5y}"></td>
    <td><select name="conf" aria-label="${d.confidence}">${d.conf.map((c, i) => `<option value="${i}">${c}</option>`).join('')}</select></td>
    <td><input type="text" name="why" maxlength="300" aria-label="${d.why}"></td></tr>`).join('') : '';
  const form = scenarios ? `<form id="expert-form" class="survey">
      <label>${d.name}<input type="text" name="who" maxlength="120"></label>
      <label>${d.field}<input type="text" name="field" maxlength="160"></label>
      <div class="table-wrap"><table class="table"><thead><tr><th>${d.scenario}</th><th>${d.p1y}</th><th>${d.p5y}</th><th>${d.confidence}</th><th>${d.why}</th></tr></thead><tbody>${rows}</tbody></table></div>
      <button type="submit" class="button">${d.prepare}</button>
      <textarea id="expert-output" rows="8" readonly hidden></textarea><p id="expert-status" class="muted-text" role="status"></p>
    </form>` : `<p class="muted-text">${d.noScenarios}</p>`;
  return `<section class="page-head"><h1>${d.title}</h1><p>${d.lead}</p></section>
    <section class="section"><div class="section-head"><h2>${d.lensesTitle}</h2></div><div class="lenses">${lenses}</div></section>
    <section class="section"><div class="section-head"><h2>${d.formTitle}</h2><p>${d.formLead}</p></div>${form}<p class="caveat">${d.method}</p></section>`;
}

export function surveyAnswer(form: HTMLFormElement, lang: string): { text: string; ok: string; fail: string } {
  const d = lt(lang);
  const value = (el: Element | null) => (el as HTMLInputElement | null)?.value.trim() ?? '';
  const answers = [...form.querySelectorAll<HTMLElement>('[data-survey]')].map((row) => ({
    scenario: row.dataset.survey,
    p1y: value(row.querySelector('[name=p1y]')),
    p5y: value(row.querySelector('[name=p5y]')),
    confidence: Number(value(row.querySelector('[name=conf]'))),
    why: value(row.querySelector('[name=why]')),
  })).filter((a) => a.p1y || a.p5y);
  const payload = {
    schema: 'geointel-expert-answer-v1',
    date: new Date().toISOString().slice(0, 10),
    who: value(form.querySelector('[name=who]')) || 'anonymous',
    field: value(form.querySelector('[name=field]')),
    answers: answers.map((a) => ({ ...a, p1y: a.p1y ? Number(a.p1y) / 100 : null, p5y: a.p5y ? Number(a.p5y) / 100 : null })),
  };
  return { text: JSON.stringify(payload, null, 2), ok: d.copied, fail: d.notCopied };
}
