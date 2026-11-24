// World regions and political/economic blocs (membership as of 2026; edit here when it changes).
import type { Lang } from './data';

export interface Group { key: string; kind: 'region' | 'bloc'; ru: string; en: string; members: string[]; note_ru?: string; note_en?: string }

const list = (codes: string) => codes.trim().split(/\s+/);

export const REGIONS: Group[] = [
  { key: 'europe', kind: 'region', ru: 'Европа', en: 'Europe', members: list('ALB AND AUT BLR BEL BIH BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN ISL IRL ITA XKX LVA LIE LTU LUX MLT MDA MCO MNE NLD MKD NOR POL PRT ROU RUS SMR SRB SVK SVN ESP SWE CHE UKR GBR') },
  { key: 'north_america', kind: 'region', ru: 'Северная Америка', en: 'North America', members: list('CAN USA') },
  { key: 'latam', kind: 'region', ru: 'Латинская Америка и Карибы', en: 'Latin America & Caribbean', members: list('ATG ARG BHS BRB BLZ BOL BRA CHL COL CRI CUB DMA DOM ECU SLV GRD GTM GUY HTI HND JAM MEX NIC PAN PRY PER KNA LCA VCT SUR TTO URY VEN') },
  { key: 'mena', kind: 'region', ru: 'Ближний Восток и Северная Африка', en: 'Middle East & North Africa', members: list('BHR EGY IRN IRQ ISR JOR KWT LBN OMN PSE QAT SAU SYR TUR ARE YEM DZA LBY MAR TUN') },
  { key: 'ssa', kind: 'region', ru: 'Африка южнее Сахары', en: 'Sub-Saharan Africa', members: list('AGO BEN BWA BFA BDI CPV CMR CAF TCD COM COG COD CIV DJI GNQ ERI SWZ ETH GAB GMB GHA GIN GNB KEN LSO LBR MDG MWI MLI MRT MUS MOZ NAM NER NGA RWA STP SEN SYC SLE SOM ZAF SSD SDN TZA TGO UGA ZMB ZWE') },
  { key: 'central_asia', kind: 'region', ru: 'Центральная Азия и Кавказ', en: 'Central Asia & Caucasus', members: list('ARM AZE GEO KAZ KGZ TJK TKM UZB') },
  { key: 'south_asia', kind: 'region', ru: 'Южная Азия', en: 'South Asia', members: list('AFG BGD BTN IND MDV NPL PAK LKA') },
  { key: 'east_asia', kind: 'region', ru: 'Восточная Азия', en: 'East Asia', members: list('CHN JPN KOR PRK MNG TWN') },
  { key: 'southeast_asia', kind: 'region', ru: 'Юго-Восточная Азия', en: 'Southeast Asia', members: list('BRN KHM IDN LAO MYS MMR PHL SGP THA TLS VNM') },
  { key: 'oceania', kind: 'region', ru: 'Океания', en: 'Oceania', members: list('AUS FJI KIR MHL FSM NRU NZL PLW PNG WSM SLB TON TUV VUT') },
];

export const BLOCS: Group[] = [
  { key: 'eu', kind: 'bloc', ru: 'Европейский союз', en: 'European Union', members: list('AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE'),
    note_ru: 'Статья 42.7 Договора о ЕС: обязательство помощи при вооружённом нападении на члена.', note_en: 'TEU Article 42.7: mutual assistance obligation if a member is attacked.' },
  { key: 'nato', kind: 'bloc', ru: 'НАТО', en: 'NATO', members: list('ALB BEL BGR CAN HRV CZE DNK EST FIN FRA DEU GRC HUN ISL ITA LVA LTU LUX MNE NLD MKD NOR POL PRT ROU SVK SVN ESP SWE TUR GBR USA'),
    note_ru: 'Статья 5: нападение на одного члена рассматривается как нападение на всех.', note_en: 'Article 5: an attack on one member is considered an attack on all.' },
  { key: 'brics', kind: 'bloc', ru: 'БРИКС', en: 'BRICS', members: list('BRA RUS IND CHN ZAF EGY ETH IRN ARE IDN'),
    note_ru: 'Экономическое объединение без военных обязательств. Статус Саудовской Аравии не определён.', note_en: 'Economic grouping without military commitments. Saudi Arabia’s status is unclear.' },
  { key: 'sco', kind: 'bloc', ru: 'ШОС', en: 'SCO', members: list('CHN RUS IND PAK KAZ KGZ TJK UZB IRN BLR') },
  { key: 'csto', kind: 'bloc', ru: 'ОДКБ', en: 'CSTO', members: list('RUS BLR ARM KAZ KGZ TJK'),
    note_ru: 'Военный союз (статья 4). Армения заморозила участие.', note_en: 'Military alliance (Article 4). Armenia has frozen its participation.' },
  { key: 'g7', kind: 'bloc', ru: 'G7', en: 'G7', members: list('CAN FRA DEU ITA JPN GBR USA') },
  { key: 'asean', kind: 'bloc', ru: 'АСЕАН', en: 'ASEAN', members: list('BRN KHM IDN LAO MYS MMR PHL SGP THA VNM TLS') },
  { key: 'opec', kind: 'bloc', ru: 'ОПЕК', en: 'OPEC', members: list('DZA COG GNQ GAB IRN IRQ KWT LBY NGA SAU ARE VEN') },
  { key: 'gcc', kind: 'bloc', ru: 'Совет сотрудничества стран Залива', en: 'Gulf Cooperation Council', members: list('BHR KWT OMN QAT SAU ARE') },
];

export const groupName = (g: Group, lang: Lang) => (lang === 'ru' ? g.ru : g.en);
export const groupNote = (g: Group, lang: Lang) => (lang === 'ru' ? g.note_ru : g.note_en);
export const groupsOf = (iso3: string) => [...REGIONS, ...BLOCS].filter((g) => g.members.includes(iso3));
