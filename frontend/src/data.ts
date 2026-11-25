export type Lang = 'ru' | 'en';
export type HorizonKey = '1m' | '1y' | '5y' | '10y';

export interface Probability { p: number; low: number; high: number }
export interface Risk {
  question: 'onset_within' | 'active_at_end';
  active: boolean | null;
  state_as_of: number;
  confidence: 'low' | 'medium' | 'high';
  horizons: Record<HorizonKey, Probability>;
  basis: { exposure_years: number; event_years: number; last_event_year: number | null };
}
export interface Advisory { level: 1 | 2 | 3 | 4; title: string; url: string | null; updated: string | null; summary: string }
export type Profile = Record<string, { value: number; year: number }>;
export interface AdvisoryUK { level: 1 | 2 | 3 | 4; partial: boolean; statuses: string[]; url: string | null; updated: string | null; restrictions: string[] }
export interface Outlook { growth?: Record<string, number>; inflation?: Record<string, number>; debt?: Record<string, number>; projects_crisis: string[] }
export interface Gpr { latest_month: string; latest: number; baseline_mean: number; ratio_12m: number | null; months: string[]; values: number[] }
export interface Election { date: string; precision: 'day' | 'month' | 'year'; kind: 'presidential' | 'parliamentary' | 'referendum'; name_en: string; name_ru: string | null; wikidata: string }
export interface CountryEntry {
  iso3: string; iso2: string; numeric: string | null; name: string;
  risks: Record<string, Risk>;
  advisory?: Advisory | null;
  advisory_uk?: AdvisoryUK | null;
  profile?: Profile | null;
  outlook?: Outlook | null;
  democracy?: { value: number; year: number } | null;
  gpr?: Gpr | null;
  elections?: Election[];
}
export interface EventTypeEntry {
  key: string; label_en: string; label_ru: string; resolution_en: string; resolution_ru: string;
  modeled: boolean; available: boolean; group?: 'conflict' | 'natural' | 'society';
  source?: string; data_window?: [number, number];
  records?: number; unresolved_labels?: number;
}
export interface SourceEntry {
  key: string; name: string; url: string | null; version: string | null;
  retrieved_at: string | null; status: 'ok' | 'failed'; error: string | null;
}
export interface Change {
  iso3: string; event_type: string; kind: 'probability_change' | 'state_change';
  horizon?: HorizonKey; from: number | string | null; to: number | string; delta?: number;
}
export interface Snapshot {
  schema: string;
  generated_at: string;
  previous_generated_at: string | null;
  method: { name: string; calibration: string; interval: string; description_en: string; description_ru: string };
  horizons: { key: HorizonKey; years: number; label_en: string; label_ru: string }[];
  event_types: EventTypeEntry[];
  sources: SourceEntry[];
  countries: CountryEntry[];
  changes: Change[];
}

export async function loadSnapshot(signal?: AbortSignal): Promise<Snapshot> {
  const response = await fetch(import.meta.env.BASE_URL + 'data/risk.json', { signal, cache: 'no-cache' });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  const data = await response.json() as Snapshot;
  if (data.schema !== 'geointel-risk-snapshot-v1' || !Array.isArray(data.countries)) {
    throw new Error('Unexpected snapshot format');
  }
  return data;
}

// Probability bands used for colouring (share of probability, 0–1).
export type Band = 'minimal' | 'low' | 'elevated' | 'high' | 'critical';
export function band(p: number): Band {
  if (p >= 0.5) return 'critical';
  if (p >= 0.2) return 'high';
  if (p >= 0.05) return 'elevated';
  if (p >= 0.01) return 'low';
  return 'minimal';
}

export function percent(p: number, lang: Lang): string {
  const value = p * 100;
  const digits = value < 1 && value > 0 ? 1 : 0;
  const text = value > 0 && value < 0.1 ? '<0.1' : value.toFixed(digits);
  return (lang === 'ru' ? text.replace('.', ',') : text) + '%';
}

// "Since your last visit": the previous visit's probabilities are kept in this browser only.
const VISIT_KEY = 'geointel.lastVisit.v1';
export interface VisitMemory { generated_at: string; values: Record<string, number> }

export function flatten(snapshot: Snapshot): Record<string, number> {
  const values: Record<string, number> = {};
  for (const country of snapshot.countries) {
    for (const [type, risk] of Object.entries(country.risks)) {
      for (const [horizon, value] of Object.entries(risk.horizons)) {
        values[country.iso3 + '|' + type + '|' + horizon] = value.p;
      }
      values[country.iso3 + '|' + type + '|state'] = risk.question === 'active_at_end' ? 1 : 0;
    }
  }
  return values;
}

export function readVisit(): VisitMemory | undefined {
  try {
    const raw = localStorage.getItem(VISIT_KEY);
    return raw ? JSON.parse(raw) as VisitMemory : undefined;
  } catch {
    return undefined;
  }
}

export function writeVisit(snapshot: Snapshot) {
  try {
    localStorage.setItem(VISIT_KEY, JSON.stringify({ generated_at: snapshot.generated_at, values: flatten(snapshot) }));
  } catch {
    // Storage may be unavailable (private mode); the feature then degrades silently.
  }
}

export function changesSince(visit: VisitMemory, snapshot: Snapshot, threshold = 0.02): Change[] {
  const current = flatten(snapshot);
  const result: Change[] = [];
  for (const [key, value] of Object.entries(current)) {
    const before = visit.values[key];
    if (before === undefined) continue;
    const [iso3, eventType, horizon] = key.split('|');
    if (horizon === 'state') {
      if (before !== value) {
        result.push({ iso3, event_type: eventType, kind: 'state_change',
          from: before ? 'active_at_end' : 'onset_within', to: value ? 'active_at_end' : 'onset_within' });
      }
    } else if (Math.abs(value - before) >= threshold) {
      result.push({ iso3, event_type: eventType, kind: 'probability_change',
        horizon: horizon as HorizonKey, from: before, to: value, delta: value - before });
    }
  }
  return result.sort((a, b) => Math.abs(b.delta ?? 1) - Math.abs(a.delta ?? 1));
}

export interface HazardEvent {
  name: string; alert: 'Orange' | 'Red' | null; year: number; month: number | null;
  severity: string; lat: number | null; lon: number | null;
  region_en?: string | null; region_ru?: string | null;
}
export interface HazardSummary {
  count: number; red: number; first_year: number; last_year: number; months: number[]; events: HazardEvent[];
  regions?: { en: string; ru: string; n: number }[];
}
export interface HazardDetails {
  schema: string; generated_at: string;
  countries: Record<string, Record<string, HazardSummary>>;
}

let hazardsPromise: Promise<HazardDetails | undefined> | undefined;
export function loadHazards(): Promise<HazardDetails | undefined> {
  hazardsPromise ??= fetch(import.meta.env.BASE_URL + 'data/hazards.json', { cache: 'no-cache' })
    .then((response) => (response.ok ? response.json() as Promise<HazardDetails> : undefined))
    .catch(() => undefined);
  return hazardsPromise;
}

export interface ScenarioComponent {
  kind: 'history' | 'expert' | 'market' | 'official' | 'community'; annual: number; low: number; high: number; weight: number;
  detail_ru: string; detail_en: string; url: string | null;
}
export interface ScenarioIndicator {
  key: string; group?: string; direction: -1 | 0 | 1; lr?: number; label_ru: string; label_en: string; value: string;
  value_ru?: string; value_en?: string; source: string; url?: string | null; countries?: string[];
}
export interface ScenarioWarning { date: string; source: string; url: string; direction: -1 | 0 | 1; summary_ru: string; summary_en: string }
export type ScenarioRole = 'party' | 'frontline' | 'ally' | 'economic';
export interface ScenarioAffected { iso3: string; role: ScenarioRole; reason_ru: string; reason_en: string }
export interface Scenario {
  key: string; title_ru: string; title_en: string; event_ru: string; event_en: string; polarity: 1 | -1;
  annual: Probability; horizons: Record<HorizonKey, Probability>; confidence: 'low' | 'medium';
  indicator_factor: number; components: ScenarioComponent[]; indicators: ScenarioIndicator[];
  warnings: ScenarioWarning[]; market_candidates: { question: string; p: number; end: string; volume: number; slug: string; inverse?: boolean }[];
  market_status: 'matched' | 'no_match' | 'unavailable'; affected: ScenarioAffected[]; calibration: string;
  sign_groups?: string[]; sign_combo?: boolean;
  community_status?: 'matched' | 'no_match' | 'unavailable';
  community_candidates?: { question: string; p: number; end: string; forecasters: number; url: string }[];
  tree?: ScenarioTree;
}
export interface ScenarioTree {
  inputs: { annual_now: number; ceasefire_annual: number; us_weak_annual: number };
  yearly: { year: number; cumulative: number; annual: number }[];
  branches: { ukraine: 'war' | 'cease_early' | 'cease_late'; us: 'us_firm' | 'us_weak'; weight: number; p5y: number; p10y: number }[];
  basis_ru: string; basis_en: string;
}
export interface ScenarioFile { schema: string; generated_at: string; scenarios: Scenario[] }

export interface Share { iso3: string; share: number }
export interface Count { iso3: string; n: number }
export interface MigrationEntry {
  year?: number; hosted?: number; hosted_from?: Count[]; abroad?: number; abroad_in?: Count[]; idps?: number;
  hosted_per_1000?: number; abroad_per_1000?: number;
  asylum_eu?: { months: string[]; values: number[]; last12: number; change: number | null };
}
export interface LinkEntry {
  trade?: { exports_usd?: number; exports_to?: Share[]; imports_usd_mirror?: number; imports_from?: Share[]; year: number | null };
  migration?: MigrationEntry;
  milex?: { value: number; year: number; change5: number | null; series: [number, number][] };
}
export interface Route { key: string; ru: string; en: string; from: string[]; to: string[] }
export interface LinksFile {
  schema: string; generated_at: string; routes: Route[];
  sources: { key: string; name: string; status: string; version?: string | null }[];
  countries: Record<string, LinkEntry>;
}

const cachedJson = <T>(name: string) => {
  let promise: Promise<T | undefined> | undefined;
  return () => (promise ??= fetch(import.meta.env.BASE_URL + 'data/' + name, { cache: 'no-cache' })
    .then((response) => (response.ok ? response.json() as Promise<T> : undefined))
    .catch(() => undefined));
};
export const loadScenarios = cachedJson<ScenarioFile>('scenarios.json');
export const loadLinks = cachedJson<LinksFile>('links.json');

export interface Sign {
  key: string; group: string; status: 'active' | 'normal' | 'no_data'; lr: number;
  value_ru: string; value_en: string; source?: string; url?: string | null; date?: string;
  strength?: number; actor?: string | null; curated?: boolean; reports?: number; chronic?: boolean;
}
export interface SignSpec {
  key: string; group: string; lr: number; applies: string[]; label_ru: string; label_en: string;
  automated: boolean; expires_days: number;
}
export interface AdjustedRisk { factor: number; signs: string[]; groups: string[]; combo: boolean; horizons?: Record<HorizonKey, Probability> }
export interface CountrySignals { signs: Sign[]; adjusted: Record<string, AdjustedRisk>; active: number; max_factor: number }
export interface SignalsFile {
  schema: string; generated_at: string; catalogue: SignSpec[];
  groups: Record<string, { ru: string; en: string }>;
  caps: { auto: [number, number]; hard: [number, number]; total: [number, number]; combo: number };
  status: Record<string, string>;
  countries: Record<string, CountrySignals>;
}
export interface BacktestPoint { date: string; factor: number; p1m: number; p1y: number; signs: string[] }
export interface BacktestFile {
  key: string; title_ru: string; title_en: string; event_date: string; base_annual: number;
  points: BacktestPoint[];
  timeline: { date: string; sign: string; summary_ru: string; summary_en: string; source: string; strength: number }[];
}
export const loadSignals = cachedJson<SignalsFile>('signals.json');
export const loadBacktest = cachedJson<BacktestFile>('backtest.json');

export interface RealCase {
  key: string; title_ru: string; title_en: string; event_date: string; risk: string; target: string;
  base_annual: number; monthly: boolean; points: BacktestPoint[]; lead_days: number; elevated_weeks: number;
  max_factor: number; brier: number | null; brier_base: number | null; radar: boolean;
}
export interface RealBacktestFile { schema: string; generated_at: string; lr: Record<string, number>; cases: RealCase[] }
export const loadRealBacktest = cachedJson<RealBacktestFile>('backtest-real.json');
export interface AccuracyFile {
  schema: string; generated_at: string; first_day: string | null; history_days: number; window_days: number;
  status: 'collecting' | 'scoring'; first_score_on: string | null; days_collected: number; resolutions_checked: string;
  titles: Record<string, { title_ru?: string; title_en?: string }>;
  series: Record<string, { date: string; p1m: number; p1y: number }[]>;
  summary: Record<string, { n: number; events: number; brier: number; mean_p: number }>;
  overall: { n: number; events: number; brier: number } | null;
}
export const loadAccuracy = cachedJson<AccuracyFile>('accuracy.json');
