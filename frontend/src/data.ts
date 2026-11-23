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
