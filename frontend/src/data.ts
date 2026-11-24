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
export interface CountryEntry {
  iso3: string; iso2: string; numeric: string | null; name: string;
  risks: Record<string, Risk>;
}
export interface EventTypeEntry {
  key: string; label_en: string; label_ru: string; resolution_en: string; resolution_ru: string;
  modeled: boolean; available: boolean; source?: string; data_window?: [number, number];
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
