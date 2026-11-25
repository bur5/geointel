// Alert levels (green → red) with what each level means and what to do, by audience.
import type { Lang } from './data';

export type AlertLevel = 'green' | 'yellow' | 'orange' | 'red';
export interface AlertInfo { level: AlertLevel; p1m?: number | null; ratio?: number | null; risk?: string | null }

interface LevelText { name: string; meaning: string; residents: string[]; travel: string[]; business: string[]; relocation: string[] }

const RU: Record<AlertLevel, LevelText> = {
  green: {
    name: 'Фон',
    meaning: 'Риск как обычно для этой страны или пары стран. Новых признаков подготовки нет.',
    residents: ['Жить обычной жизнью.', 'Раз в год проверить документы и аптечку.'],
    travel: ['Обычные меры предосторожности.', 'Следить за официальными рекомендациями МИД.'],
    business: ['Обычное планирование.', 'Иметь общий план на случай перебоев (поставки, связь, расчёты).'],
    relocation: ['Переезд можно планировать в обычном порядке.', 'Сравнить долгосрочные риски на горизонтах 5 и 10 лет (ниже).'],
  },
  yellow: {
    name: 'Повышенный',
    meaning: 'Риск выше обычного примерно в полтора раза или вероятность за месяц от 3%. Это не значит, что событие скоро случится: так бывает месяцами.',
    residents: [
      'Проверить срок действия паспортов, иметь копии документов в облаке.',
      'Держать небольшой запас воды, еды и лекарств на 3 дня, зарядки для телефона.',
      'Знать ближайшие укрытия и официальные каналы оповещения.',
    ],
    travel: [
      'Покупать билеты с возможностью возврата или обмена, оформить страховку, покрывающую отмену поездки.',
      'Зарегистрироваться в консульской системе своей страны.',
    ],
    business: [
      'Проверить план непрерывности: запасные поставщики, удалённая работа, резервные копии.',
      'Оценить долю выручки и поставок, завязанных на страну, и запас ликвидности.',
    ],
    relocation: [
      'Не отказываться от переезда, но не сжигать мосты: сохранить жильё, счёт и документы для возвращения.',
      'Выбирать гибкий договор аренды, держать часть сбережений вне страны.',
    ],
  },
  orange: {
    name: 'Высокий',
    meaning: 'Риск выше обычного в 3 раза и больше или вероятность за месяц от 10%. Признаки подготовки накапливаются.',
    residents: [
      'Собрать «тревожный рюкзак»: документы, наличные, лекарства, зарядки, вода на 3 дня.',
      'Договориться с близкими о месте встречи и способе связи без мобильной сети.',
      'Держать полный бак, знать несколько маршрутов выезда.',
      'Следить за официальными заявлениями каждый день.',
    ],
    travel: [
      'Отложить необязательные поездки.',
      'Если вы уже там — иметь билет или план выезда, следить за закрытием неба и границ.',
    ],
    business: [
      'Сократить запасы и платежи, завязанные на страну, перевести критичные данные и функции в другие страны.',
      'Подготовить план эвакуации персонала, проверить страховку от политических рисков.',
    ],
    relocation: [
      'Отложить переезд, если он ещё не начат.',
      'Если вы уже переехали — держать «план Б»: куда и как уехать за 24–48 часов.',
    ],
  },
  red: {
    name: 'Тревога',
    meaning: 'Вероятность за месяц от 20%, и есть признаки последней стадии: эвакуация посольств, закрытие неба, мобилизация, развёртывание госпиталей.',
    residents: [
      'Если есть возможность — временно уехать из приграничных и стратегических районов.',
      'Выполнять указания властей, держать при себе документы и наличные.',
      'Не публиковать в сети фото и данные о военных объектах и передвижениях.',
    ],
    travel: [
      'Не ехать. Если вы на месте — уезжать, пока работают рейсы и пункты пропуска.',
      'Связаться с консульством, сообщить о своём местонахождении.',
    ],
    business: [
      'Эвакуировать персонал и семьи, остановить отгрузки и поставки.',
      'Перенести управление и расчёты за пределы страны.',
    ],
    relocation: ['Не переезжать.', 'Если вы уже там — выезжать по заранее подготовленному плану.'],
  },
};

const EN: Record<AlertLevel, LevelText> = {
  green: {
    name: 'Background',
    meaning: 'Risk is as usual for this country or pair of countries. No new signs of preparation.',
    residents: ['Live normally.', 'Once a year, check documents and the first-aid kit.'],
    travel: ['Normal precautions.', 'Follow official foreign-ministry advice.'],
    business: ['Normal planning.', 'Keep a general plan for disruptions (supplies, communications, payments).'],
    relocation: ['A move can be planned as usual.', 'Compare the long-term risks at 5 and 10 years (below).'],
  },
  yellow: {
    name: 'Elevated',
    meaning: 'Risk is about 1.5 times the usual level or at least 3% within a month. It does not mean the event is imminent: this can last for months.',
    residents: [
      'Check passport expiry dates and keep copies of documents in the cloud.',
      'Keep a small 3-day supply of water, food and medicine, and phone chargers.',
      'Know the nearest shelters and the official alert channels.',
    ],
    travel: [
      'Buy refundable or changeable tickets and insurance that covers cancellation.',
      "Register with your country's consular service.",
    ],
    business: [
      'Review the continuity plan: backup suppliers, remote work, backups.',
      'Check the share of revenue and supplies tied to the country and the liquidity buffer.',
    ],
    relocation: [
      "Don't cancel the move, but don't burn bridges: keep housing, an account and documents for a return.",
      'Choose a flexible lease and keep part of your savings outside the country.',
    ],
  },
  orange: {
    name: 'High',
    meaning: 'Risk is 3 times the usual level or more, or at least 10% within a month. Signs of preparation are accumulating.',
    residents: [
      'Pack a grab bag: documents, cash, medicine, chargers, 3 days of water.',
      'Agree with family on a meeting place and a way to communicate without the mobile network.',
      'Keep the fuel tank full and know several exit routes.',
      'Follow official statements daily.',
    ],
    travel: [
      'Postpone non-essential trips.',
      'If you are already there, have a ticket or exit plan and watch for airspace and border closures.',
    ],
    business: [
      'Reduce inventory and payments tied to the country; move critical data and functions elsewhere.',
      'Prepare a staff evacuation plan and check political-risk insurance.',
    ],
    relocation: [
      'Postpone the move if it has not started.',
      'If you have already moved, keep a plan B: where and how to leave within 24–48 hours.',
    ],
  },
  red: {
    name: 'Alert',
    meaning: 'At least 20% within a month, and last-stage signs are present: embassy evacuations, airspace closures, mobilisation, field hospitals.',
    residents: [
      'If you can, temporarily leave border and strategic areas.',
      'Follow official instructions; keep documents and cash on you.',
      "Don't post photos or details of military sites and movements online.",
    ],
    travel: [
      "Don't go. If you are there, leave while flights and border crossings work.",
      'Contact your consulate and report your location.',
    ],
    business: ['Evacuate staff and families, stop shipments.', 'Move management and payments outside the country.'],
    relocation: ["Don't move.", 'If you are already there, leave following the plan prepared in advance.'],
  },
};

const HEAD = {
  ru: { level: 'Уровень тревоги', residents: 'Жителям', travel: 'Путешественникам', business: 'Бизнесу', relocation: 'Переезжающим', month: (p: string, r: string) => `Вероятность в ближайший месяц: ${p}; относительно обычного уровня: ×${r}.`, scale: 'Шкала: фон — как обычно; повышенный — ×1,5 или от 3% за месяц; высокий — ×3 или от 10%; тревога — от 20% и признаки последней стадии.' },
  en: { level: 'Alert level', residents: 'Residents', travel: 'Travellers', business: 'Business', relocation: 'Relocating', month: (p: string, r: string) => `Probability within a month: ${p}; versus the usual level: ×${r}.`, scale: 'Scale: background — as usual; elevated — ×1.5 or 3%+ a month; high — ×3 or 10%+; alert — 20%+ and last-stage signs.' },
};

export const alertText = (lang: Lang) => (lang === 'ru' ? RU : EN);
export const alertName = (level: AlertLevel, lang: Lang) => alertText(lang)[level].name;

export function alertBadge(level: AlertLevel, lang: Lang) {
  return `<span class="alert-badge alert-${level}">${alertName(level, lang)}</span>`;
}

export function alertCard(
  info: AlertInfo | null | undefined, lang: Lang, pct: (p: number) => string, esc: (s: string) => string,
  context = '',
) {
  const level = info?.level ?? 'green';
  const t = alertText(lang)[level];
  const h = HEAD[lang];
  const list = (items: string[]) => `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>`;
  const numbers = info?.p1m != null && info.ratio != null
    ? `<p class="muted-text">${esc(h.month(pct(info.p1m), info.ratio.toFixed(1).replace('.', lang === 'ru' ? ',' : '.')))}</p>` : '';
  return `<section class="alert-card alert-${level}" id="alert-card"><div class="alert-head"><h3>${h.level}: ${alertBadge(level, lang)}</h3>
    ${context ? `<p class="muted-text">${esc(context)}</p>` : ''}<p>${esc(t.meaning)}</p>${numbers}</div>
    <div class="alert-grid"><div><h4>${h.residents}</h4>${list(t.residents)}</div><div><h4>${h.travel}</h4>${list(t.travel)}</div>
    <div><h4>${h.business}</h4>${list(t.business)}</div><div><h4>${h.relocation}</h4>${list(t.relocation)}</div></div>
    <p class="muted-text small">${h.scale}</p></section>`;
}
