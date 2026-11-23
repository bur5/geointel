export const fixtureDate = '2025-03-01';
export const provenance = 'GEOINTEL synthetic fixture v0.1';
export const months = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar'];

export interface Fixture {
  id: string;
  region: string;
  history: number[];
  events: { date: string; title: string }[];
  projection?: { low: number; high: number };
}

const regionalData: [string, string, number[], string, string][] = [
  ['804', 'Eastern Europe', [61, 65, 64, 70, 73, 78], 'Reporting volume increases', 'New synthetic event cluster'],
  ['729', 'Northern Africa', [72, 74, 80, 82, 80, 84], 'Coverage expands across reporting areas', 'Simulated disruption recorded'],
  ['104', 'Southeast Asia', [60, 63, 59, 64, 68, 71], 'Reporting pattern shifts', 'Synthetic incident count rises'],
  ['170', 'South America', [43, 47, 45, 44, 51, 54], 'Synthetic incident levels fluctuate', 'Additional fixture reports recorded'],
  ['586', 'Southern Asia', [55, 57, 54, 58, 56, 62], 'Brief increase in fixture activity', 'Synthetic reporting volume rises'],
  ['566', 'Western Africa', [41, 44, 45, 47, 48, 50], 'Reporting coverage improves', 'Moderate synthetic change recorded'],
  ['076', 'South America', [25, 29, 28, 33, 30, 32], 'Synthetic series shows a brief rise', 'Fixture observations stabilize'],
  ['250', 'Western Europe', [16, 19, 18, 17, 22, 20], 'Minor synthetic change recorded', 'Fixture observations decline'],
];

export const fixtures: Fixture[] = regionalData.map(([id, region, history, earlier, latest], index) => ({
  id, region, history,
  events: [{ date: '2025-02-26', title: latest }, { date: '2025-01-14', title: earlier }],
  projection: index < 4 ? { low: history[5] - 9, high: history[5] + 12 } : undefined,
}));

export function band(score: number) {
  if (score >= 70) return 'High';
  if (score >= 45) return 'Elevated';
  return 'Low';
}

export interface Forecast {
  id: string;
  analysis_run_id: string;
  conflict_type: string;
  question: string;
  horizon_months: number;
  version: number;
  probability_low: number | null;
  probability_high: number | null;
  confidence: string;
  rationale: string;
  evidence_for: string[];
  evidence_against: string[];
  unknowns: string[];
  resolution_criteria: string[];
  change_conditions: string[];
  created_at: string;
}

function validBound(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && value >= 0 && value <= 1);
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const conflictTypes = new Set<unknown>([
  'interstate_armed_conflict', 'internal_armed_conflict', 'one_sided_violence', 'major_political_violence',
]);
const confidenceLevels = new Set<unknown>(['low', 'medium', 'high']);

function validTimestamp(value: unknown): boolean {
  if (typeof value !== 'string') return false;
  // PostgreSQL emits a zone. SQLite can return the same timestamp without one.
  const parts = /^(\d{4}-\d{2}-\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})?$/.exec(value);
  if (!parts || !Number.isFinite(Date.parse(parts[2] ? value : value + 'Z'))) return false;
  // Date.parse can roll invalid calendar days into the next month.
  const day = new Date(parts[1] + 'T00:00:00Z');
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === parts[1];
}

function isForecast(value: unknown): value is Forecast {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  const low = row.probability_low;
  const high = row.probability_high;
  if (!validBound(low) || !validBound(high)) return false;
  if (low !== null && high !== null && low > high) return false;
  return typeof row.id === 'string' && uuid.test(row.id)
    && typeof row.analysis_run_id === 'string' && uuid.test(row.analysis_run_id)
    && conflictTypes.has(row.conflict_type) && confidenceLevels.has(row.confidence)
    && typeof row.question === 'string' && typeof row.rationale === 'string'
    && validTimestamp(row.created_at)
    && typeof row.version === 'number' && Number.isSafeInteger(row.version) && row.version >= 1
    && typeof row.horizon_months === 'number' && Number.isInteger(row.horizon_months)
    && row.horizon_months >= 1 && row.horizon_months <= 120
    && ['evidence_for', 'evidence_against', 'unknowns', 'resolution_criteria', 'change_conditions']
      .every((key) => Array.isArray(row[key]) && row[key].every((item) => typeof item === 'string'));
}

export async function loadForecasts(signal: AbortSignal): Promise<Forecast[]> {
  const response = await fetch('/geointel-api/forecasts', { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('Forecast service unavailable');
  const payload: unknown = await response.json();
  if (!Array.isArray(payload) || !payload.every(isForecast)) throw new Error('Invalid forecast response');
  return payload;
}
