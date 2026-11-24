// Links between countries and the impact chains they carry: "an event in X → consequences in Y".
import type { Lang, LinksFile } from './data';
import { BLOCS } from './groups';

export type ChainEvent = 'conflict' | 'political' | 'economic' | 'disaster' | 'migration';
export type LinkKind = 'border' | 'bloc' | 'market' | 'supplier' | 'diaspora' | 'route';

export const CHAIN_EVENTS: ChainEvent[] = ['conflict', 'political', 'economic', 'disaster', 'migration'];

export interface LinkReason { kind: LinkKind; strength: number; ru: string; en: string }
export interface CountryLink { iso3: string; reasons: LinkReason[]; score: number }

const RELEVANCE: Record<ChainEvent, Record<LinkKind, number>> = {
  conflict: { border: 1, bloc: 1, market: 0.6, supplier: 0.6, diaspora: 0.9, route: 0.8 },
  political: { border: 0.5, bloc: 0.8, market: 0.6, supplier: 0.5, diaspora: 0.6, route: 0.5 },
  economic: { border: 0.4, bloc: 0.7, market: 1, supplier: 0.9, diaspora: 0.4, route: 0.3 },
  disaster: { border: 0.6, bloc: 0.4, market: 0.5, supplier: 0.8, diaspora: 0.5, route: 0.3 },
  migration: { border: 0.9, bloc: 0.6, market: 0.1, supplier: 0.1, diaspora: 1, route: 1 },
};

// What travels along each kind of link, per event type.
const EFFECTS: Record<ChainEvent, Record<LinkKind, { ru: string; en: string }>> = {
  conflict: {
    border: { ru: 'беженцы, закрытие границы, риск переноса боёв и падения снарядов или дронов', en: 'refugees, border closures, risk of fighting, shells or drones crossing over' },
    bloc: { ru: 'союзные обязательства: военная помощь, переброска войск, санкции', en: 'alliance obligations: military aid, troop deployments, sanctions' },
    market: { ru: 'потеря экспортного рынка, неплатежи, остановка поставок', en: 'loss of an export market, unpaid contracts, halted shipments' },
    supplier: { ru: 'перебои импорта и рост цен на поставляемые товары', en: 'import disruptions and higher prices for supplied goods' },
    diaspora: { ru: 'новая волна беженцев по уже сложившимся связям', en: 'a new wave of refugees along existing community ties' },
    route: { ru: 'рост попыток пересечения по маршруту', en: 'more crossing attempts along the route' },
  },
  political: {
    border: { ru: 'нестабильность на границе, усиленный пограничный контроль', en: 'border instability, tighter border checks' },
    bloc: { ru: 'паралич решений блока, споры о бюджете, санкциях и правилах', en: 'blocked decisions in the bloc, disputes over budget, sanctions and rules' },
    market: { ru: 'снижение спроса и инвестиций, риск для контрактов', en: 'weaker demand and investment, contract risk' },
    supplier: { ru: 'неопределённость поставок и регулирования', en: 'uncertainty over supply and regulation' },
    diaspora: { ru: 'политическая эмиграция по сложившимся связям', en: 'political emigration along existing ties' },
    route: { ru: 'изменение миграционной политики меняет потоки по маршруту', en: 'migration policy changes shift flows along the route' },
  },
  economic: {
    border: { ru: 'падение приграничной торговли, трудовая миграция', en: 'falling cross-border trade, labour migration' },
    bloc: { ru: 'общие финансы и рынок: заражение через банки, бюджет, валюту', en: 'shared finances and market: contagion via banks, budget, currency' },
    market: { ru: 'падение экспорта в страну, удар по экспортёрам', en: 'falling exports to the country, exporters hit' },
    supplier: { ru: 'дефицит и подорожание импорта из страны', en: 'shortages and pricier imports from the country' },
    diaspora: { ru: 'сокращение денежных переводов, рост экономической миграции', en: 'lower remittances, more economic migration' },
    route: { ru: 'рост экономической миграции по маршруту', en: 'more economic migration along the route' },
  },
  disaster: {
    border: { ru: 'гуманитарная помощь и эвакуация через границу, общие реки и экосистемы', en: 'aid and evacuation across the border, shared rivers and ecosystems' },
    bloc: { ru: 'механизмы взаимопомощи блока, расходы на восстановление', en: 'bloc mutual-aid mechanisms, reconstruction costs' },
    market: { ru: 'временное падение спроса', en: 'a temporary fall in demand' },
    supplier: { ru: 'перебои в цепочках поставок (как с чипами после землетрясений)', en: 'supply chain disruption (as with chips after earthquakes)' },
    diaspora: { ru: 'временная эвакуация к родственникам', en: 'temporary evacuation to relatives abroad' },
    route: { ru: 'вынужденное перемещение по маршруту', en: 'forced displacement along the route' },
  },
  migration: {
    border: { ru: 'прямой приток людей через сухопутную границу', en: 'direct inflow across the land border' },
    bloc: { ru: 'вторичные перемещения внутри блока (Шенген), споры о распределении', en: 'secondary movements inside the bloc (Schengen), disputes over sharing' },
    market: { ru: 'слабая связь через торговлю', en: 'weak trade link' },
    supplier: { ru: 'слабая связь через торговлю', en: 'weak trade link' },
    diaspora: { ru: 'люди едут туда, где уже есть их сообщество', en: 'people move to where their community already lives' },
    route: { ru: 'основной маршрут перемещения', en: 'main route of movement' },
  },
};

export function effect(event: ChainEvent, kind: LinkKind, lang: Lang) {
  return EFFECTS[event][kind][lang];
}

const pctText = (share: number, lang: Lang) =>
  (share * 100).toFixed(share >= 0.1 ? 0 : 1).replace('.', lang === 'ru' ? ',' : '.') + '%';
const people = (n: number, lang: Lang) =>
  n >= 1e6 ? (n / 1e6).toFixed(1).replace('.', lang === 'ru' ? ',' : '.') + (lang === 'ru' ? ' млн' : 'M')
    : n >= 1e3 ? Math.round(n / 1e3) + (lang === 'ru' ? ' тыс.' : 'k') : String(n);
export const formatPeople = people;

/** All countries linked to ``iso3``, with reasons and a strength score for one event type. */
export function linksOf(
  iso3: string,
  event: ChainEvent,
  neighbours: string[],
  data: LinksFile | undefined,
  name: (iso3: string) => string,
): CountryLink[] {
  const found = new Map<string, LinkReason[]>();
  const add = (code: string, reason: LinkReason) => {
    if (code === iso3) return;
    const list = found.get(code) ?? [];
    list.push(reason);
    found.set(code, list);
  };
  const self = name(iso3);
  for (const code of neighbours) add(code, { kind: 'border', strength: 3, ru: 'общая граница', en: 'shared border' });
  // One alliance reason per country, naming every shared bloc.
  const shared = new Map<string, typeof BLOCS>();
  for (const bloc of BLOCS.filter((b) => b.members.includes(iso3))) {
    for (const code of bloc.members) shared.set(code, [...(shared.get(code) ?? []), bloc]);
  }
  for (const [code, blocs] of shared) {
    const core = blocs.filter((b) => b.key === 'nato' || b.key === 'eu').length;
    add(code, { kind: 'bloc', strength: core === 2 ? 2.5 : core === 1 ? 2 : 1,
      ru: blocs.map((b) => b.ru).join(', '), en: blocs.map((b) => b.en).join(', ') });
  }
  const countries = data?.countries ?? {};
  for (const [code, entry] of Object.entries(countries)) {
    const toSelf = entry.trade?.exports_to?.find((s) => s.iso3 === iso3);
    if (toSelf && toSelf.share >= 0.02) {
      add(code, { kind: 'market', strength: Math.min(toSelf.share * 40, 6),
        ru: `${self} — рынок для ${pctText(toSelf.share, 'ru')} экспорта`, en: `${self} takes ${pctText(toSelf.share, 'en')} of its exports` });
    }
    const fromSelf = entry.trade?.imports_from?.find((s) => s.iso3 === iso3);
    if (fromSelf && fromSelf.share >= 0.03) {
      add(code, { kind: 'supplier', strength: Math.min(fromSelf.share * 35, 6),
        ru: `${pctText(fromSelf.share, 'ru')} импорта идёт из страны ${self}`, en: `${pctText(fromSelf.share, 'en')} of its imports come from ${self}` });
    }
  }
  const own = countries[iso3]?.migration;
  const abroad = own?.abroad ?? 0;
  for (const host of own?.abroad_in ?? []) {
    if (host.n < 1000) continue;
    const share = abroad ? host.n / abroad : 0;
    add(host.iso3, { kind: 'diaspora', strength: Math.min(1 + share * 8, 6),
      ru: `${people(host.n, 'ru')} беженцев и просителей убежища из страны ${self}`, en: `${people(host.n, 'en')} refugees and asylum seekers from ${self}` });
  }
  for (const route of data?.routes ?? []) {
    if (!route.from.includes(iso3)) continue;
    for (const code of route.to) add(code, { kind: 'route', strength: 3, ru: `маршрут «${route.ru}»`, en: `${route.en} route` });
  }
  const weights = RELEVANCE[event];
  return [...found.entries()]
    .map(([code, reasons]) => ({
      iso3: code,
      reasons: reasons.sort((a, b) => b.strength * weights[b.kind] - a.strength * weights[a.kind]),
      score: reasons.reduce((sum, r) => sum + r.strength * weights[r.kind], 0),
    }))
    .filter((link) => link.score >= 1)
    .sort((a, b) => b.score - a.score);
}
