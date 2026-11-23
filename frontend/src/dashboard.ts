type Check = (value: unknown) => boolean;
type Fields = Record<string, Check>;

const string: Check = (value) => typeof value === 'string';
const number: Check = (value) => typeof value === 'number' && Number.isFinite(value);
const integer: Check = (value) => typeof value === 'number' && Number.isSafeInteger(value);
const boolean: Check = (value) => typeof value === 'boolean';
const nullable = (check: Check): Check => (value) => value === null || check(value);
const oneOf = (...values: string[]): Check => (value) => typeof value === 'string' && values.includes(value);
const uuid: Check = (value) => typeof value === 'string' &&
  /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value);
const iso3: Check = (value) => typeof value === 'string' && /^[A-Z]{3}$/.test(value);
const timestamp: Check = (value) => {
  if (typeof value !== 'string') return false;
  const parts = /^(\d{4}-\d{2}-\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!parts || !Number.isFinite(Date.parse(value))) return false;
  const day = new Date(parts[1] + 'T00:00:00Z');
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0, 10) === parts[1];
};
const scalar = nullable(string);
const quantity = nullable(number);
const date = nullable(timestamp);
const freshness = oneOf('recent', 'stale', 'unknown');
const probability = nullable((value) => typeof value === 'number' && value >= 0 && value <= 1);

function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function shape(fields: Fields): Check {
  return (value) => object(value) && Object.entries(fields).every(([key, check]) => check(value[key]));
}

const point = {
  id: uuid,
  geography: shape({ name: scalar, iso3: nullable(iso3), region: scalar, unit: scalar }),
  provenance: shape({
    provider: scalar, source_record_id: scalar, analysis_run_id: nullable(uuid),
    version: scalar, retrieved_at: date,
  }),
  freshness,
};

export const series = {
  observations: ['Operational observations', 'observations', {
    kind: oneOf('observed_event'), occurred_at: date, event_type: string,
    reported_fatalities: nullable(integer), temporal_classification: scalar, confidence: string,
  }],
  ucdp_observations: ['UCDP observations', 'ucdp-observations', {
    kind: oneOf('observed_event'), occurred_at: date, ended_at: date, dataset: scalar,
    temporal_role: string, coverage_end: date, violence_type_code: nullable(integer),
    gw_country_code: nullable(integer), reported_fatalities_best: nullable(integer),
    reported_fatalities_low: nullable(integer), reported_fatalities_high: nullable(integer),
    reliability: string,
  }],
  indicators: ['Country indicators', 'indicators', {
    kind: oneOf('derived_indicator'), observed_at: date, name: string, value: quantity, unit: scalar,
  }],
  predictions: ['Provider forecasts', 'forecasts', {
    kind: oneOf('model_prediction'), issued_at: timestamp, target_start: timestamp, target_end: timestamp,
    horizon_months: nullable(integer), model: string, target_variable: string, prediction: quantity,
    unit: scalar, scale: scalar, alignment_status: string,
    target_period_status: oneOf('upcoming', 'active', 'ended', 'invalid'),
  }],
  assessments: ['GEOINTEL assessments', 'assessments', {
    kind: oneOf('forecast_assessment'), issued_at: timestamp, horizon_months: integer,
    forecast_version: integer, conflict_type: string, probability_low: probability,
    probability_high: probability, confidence: string,
  }],
} satisfies Record<string, [string, string, Fields]>;

export type Series = keyof typeof series;
export const seriesKeys = Object.keys(series) as Series[];

const coverageEntry = shape({
  availability: oneOf('available', 'missing'), freshness, latest_at: date,
  latest_record_has_country_id: nullable(boolean),
});
const coverageShape = shape({
  country: nullable(iso3), region: scalar, as_of: timestamp, stale_after_days: integer,
  ...Object.fromEntries(seriesKeys.map((key) => [key, coverageEntry])),
});

interface CoverageEntry {
  availability: 'available' | 'missing';
  freshness: string;
  latest_at: string | null;
  latest_record_has_country_id: boolean | null;
}
type Coverage = Record<Series, CoverageEntry> & { as_of: string; stale_after_days: number };

type RecordValue = string | number | null;
export type DashboardRow = Record<string, unknown> & {
  id: string;
  geography: Record<'name' | 'iso3' | 'region' | 'unit', string | null>;
  provenance: Record<'provider' | 'source_record_id' | 'analysis_run_id' | 'version' | 'retrieved_at', string | null>;
  freshness: string;
};
interface DashboardPage {
  items: DashboardRow[];
  availability: 'available' | 'missing' | 'end_of_results';
  next_offset: number | null;
}

export const pageSize = 20;

async function request(path: string, params: URLSearchParams, signal: AbortSignal): Promise<unknown> {
  const response = await fetch('/api/v1/dashboard/' + path + '?' + params, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(12000)]),
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error('Dashboard request failed');
  return response.json();
}

export async function loadCoverage(country: string, signal: AbortSignal): Promise<Coverage> {
  const params = new URLSearchParams(country ? { country } : {});
  const data = await request('coverage', params, signal);
  if (!object(data) || !coverageShape(data) || data.country !== (country || null) || data.region !== null) {
    throw new Error('Invalid dashboard coverage');
  }
  return data as Coverage;
}

export async function loadSeries(key: Series, country: string, offset: number, signal: AbortSignal): Promise<DashboardPage> {
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
  if (country) params.set('country', country);
  const [, path, fields] = series[key];
  const data = await request(path, params, signal);
  const validRow = shape({ ...point, ...fields });
  if (!object(data) || data.offset !== offset || data.limit !== pageSize ||
    !Array.isArray(data.items) || data.items.length > pageSize ||
    data.availability !== (data.items.length ? 'available' : offset ? 'end_of_results' : 'missing') ||
    (data.next_offset !== null && (data.next_offset !== offset + pageSize ||
      data.next_offset > 10000 || data.items.length !== pageSize)) ||
    !data.items.every((row) => validRow(row) && (!country || row.geography.iso3 === country) &&
      (key !== 'assessments' || row.probability_low === null || row.probability_high === null ||
        row.probability_low <= row.probability_high))) {
    throw new Error('Invalid dashboard page');
  }
  return data as unknown as DashboardPage;
}

const labels: Record<string, string> = {
  name: 'Name', occurred_at: 'Occurred at', ended_at: 'Ended at', event_type: 'Event type',
  reported_fatalities: 'Reported fatalities', temporal_classification: 'Temporal classification',
  confidence: 'Reported confidence', dataset: 'Dataset', temporal_role: 'Temporal role',
  coverage_end: 'Dataset coverage end', violence_type_code: 'Violence type code',
  gw_country_code: 'Gleditsch–Ward country code', reported_fatalities_best: 'Reported fatalities (best)',
  reported_fatalities_low: 'Reported fatalities (low)', reported_fatalities_high: 'Reported fatalities (high)',
  reliability: 'Reported reliability', observed_at: 'Observed at', value: 'Value', unit: 'Native unit',
  issued_at: 'Issued at', target_start: 'Target start', target_end: 'Target end',
  horizon_months: 'Horizon (months)', model: 'Model', target_variable: 'Target variable',
  prediction: 'Prediction', scale: 'Native scale', alignment_status: 'Geographic alignment',
  target_period_status: 'Target period status', forecast_version: 'Forecast version',
  conflict_type: 'Conflict type', probability_low: 'Probability lower bound', probability_high: 'Probability upper bound',
};

const display = (value: RecordValue) => value === null ? 'Unavailable' : String(value);

function details(entries: [string, RecordValue][], escape: (value: string) => string) {
  return '<dl>' + entries.map(([label, value]) => `<dt>${label}</dt><dd>${escape(display(value))}</dd>`).join('') + '</dl>';
}

export function rowCard(key: Series, row: DashboardRow, escape: (value: string) => string) {
  const geography = row.geography;
  const provenance = row.provenance;
  const fields: [string, RecordValue][] = Object.keys(series[key][2])
    .filter((field) => field !== 'kind')
    .map((field) => [labels[field], field === 'target_period_status' && row[field] === 'ended'
      ? 'Expired (target period ended)' : row[field] as RecordValue]);
  return `<article class="panel section-body forecast"><h3>${escape(geography.name ?? geography.iso3 ?? 'Unmapped geography')}</h3>
    ${details([
      ['ISO alpha-3', geography.iso3], ['Region', geography.region], ['Geographic unit', geography.unit],
      ['Freshness', row.freshness], ...fields, ['Provider', provenance.provider], ['Source record', provenance.source_record_id],
      ['Analysis run', provenance.analysis_run_id], ['Source version', provenance.version],
      ['Retrieved at', provenance.retrieved_at], ['Record ID', row.id],
    ], escape)}</article>`;
}

export function coverageCard(coverage: Coverage, escape: (value: string) => string) {
  return `<p>As of ${escape(coverage.as_of)} · Stale after ${coverage.stale_after_days} days</p>` +
    seriesKeys.map((key) => {
      const entry = coverage[key];
      return `<h3>${series[key][0]}</h3>` + details([
        ['Availability', entry.availability], ['Freshness', entry.freshness], ['Latest stored record', entry.latest_at],
        ['Latest record has country ID', entry.latest_record_has_country_id === null ? null :
          entry.latest_record_has_country_id ? 'Yes' : 'No'],
      ], escape);
    }).join('');
}
