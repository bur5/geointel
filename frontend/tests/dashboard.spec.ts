import { expect, test } from '@playwright/test';

const prefix = '/api/v1/dashboard';
const pageEnvelope = (items: unknown[]) => ({
  items, offset: 0, limit: 20, availability: items.length ? 'available' : 'missing', next_offset: null,
});
const assessment = {
  id: 'e25a07dc-1835-4c6e-896c-ad9324ec1ad4',
  kind: 'forecast_assessment', freshness: 'stale',
  geography: { name: '<em data-audit-marker>Spain</em>', iso3: 'ESP', region: 'southern-europe', unit: 'country' },
  provenance: {
    provider: 'GEOINTEL', analysis_run_id: 'ac66759c-20f5-4eab-bb13-c4dff12a8301',
    version: 'test', source_record_id: null, retrieved_at: null,
  },
  conflict_type: 'internal_armed_conflict', issued_at: '2025-02-28T08:00:00Z',
  horizon_months: 3, forecast_version: 2, probability_low: null, probability_high: .26, confidence: 'low',
};

test('API is the default and failed or malformed series can be retried independently', async ({ page }) => {
  let responses = 0;
  await page.route('**/api/v1/dashboard/forecasts?*', (route) => route.fulfill({ json: pageEnvelope([]) }));
  await page.route('**/api/v1/dashboard/assessments?*', async (route) => {
    responses += 1;
    if (responses === 1) await route.fulfill({ status: 503, json: {} });
    else if (responses === 2) await route.fulfill({ json: pageEnvelope([{ ...assessment, probability_low: .9 }]) });
    else await route.fulfill({ json: pageEnvelope([assessment]) });
  });
  await page.goto('/#forecasts');
  const predictions = page.locator('[data-dashboard="predictions"]');
  const assessments = page.locator('[data-dashboard="assessments"]');
  await expect(predictions.getByText('No records')).toBeVisible();
  await expect(assessments.getByRole('alert')).toBeVisible();
  await assessments.getByRole('button', { name: 'Retry' }).click();
  await expect(assessments.getByRole('alert')).toBeVisible();
  await expect(assessments.locator('article')).toHaveCount(0);
  await assessments.getByRole('button', { name: 'Retry' }).click();
  await expect(assessments.getByRole('heading', { name: assessment.geography.name })).toBeVisible();
  await expect(page.locator('[data-audit-marker], .synthetic')).toHaveCount(0);
  await expect(assessments.locator('dd', { hasText: /^0\.26$/ })).toBeVisible();
  await expect(assessments.locator('dd', { hasText: /^stale$/ })).toBeVisible();
  await expect(assessments).toContainText(assessment.provenance.analysis_run_id);
  await expect(predictions.getByText('No records')).toBeVisible();
  expect(responses).toBe(3);
});

for (const invalid of [
  { id: 'bad' }, { horizon_months: '3' }, { probability_low: undefined },
  { issued_at: '2025-02-30T08:00:00Z' }, { probability_high: 1.1 },
  { geography: { ...assessment.geography, iso3: '123' } },
]) {
  test('rejects malformed assessment ' + Object.keys(invalid)[0], async ({ page }) => {
    await page.route('**/api/v1/dashboard/forecasts?*', (route) => route.fulfill({ json: pageEnvelope([]) }));
    await page.route('**/api/v1/dashboard/assessments?*', (route) =>
      route.fulfill({ json: pageEnvelope([assessment, { ...assessment, ...invalid }]) }));
    await page.goto('/#forecasts');
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.locator('article, .synthetic')).toHaveCount(0);
  });
}

test('retry keeps the loaded page and repeats the failed offset', async ({ page }) => {
  const offsets: string[] = [];
  await page.route('**/api/v1/dashboard/forecasts?*', (route) => route.fulfill({ json: pageEnvelope([]) }));
  await page.route('**/api/v1/dashboard/assessments?*', async (route) => {
    const offset = new URL(route.request().url()).searchParams.get('offset')!;
    offsets.push(offset);
    if (offset === '0') {
      const items = Array.from({ length: 20 }, (_, index) => ({
        ...assessment, id: '00000000-0000-0000-0000-' + String(index).padStart(12, '0'),
      }));
      await route.fulfill({ json: { ...pageEnvelope(items), next_offset: 20 } });
    } else if (offsets.length === 2) {
      await route.fulfill({ status: 503, json: {} });
    } else {
      await route.fulfill({ json: { ...pageEnvelope([assessment]), offset: 20 } });
    }
  });
  await page.goto('/#forecasts');
  const panel = page.locator('[data-dashboard="assessments"]');
  await panel.getByRole('button', { name: 'Load more' }).click();
  await expect(panel.getByRole('alert')).toBeVisible();
  await expect(panel.getByRole('article')).toHaveCount(20);
  await panel.getByRole('button', { name: 'Retry' }).click();
  await expect(panel.getByRole('article')).toHaveCount(21);
  await expect(panel.getByText('End of results')).toBeVisible();
  expect(offsets).toEqual(['0', '20', '20']);
});

test('browser reads all series from the isolated ASGI app and paginates stored observations', async ({ page, request }) => {
  test.skip(process.env.GEOINTEL_ASGI_TEST !== '1', 'Requires an isolated PostgreSQL fixture database and dashboard_app');
  const origin = process.env.GEOINTEL_DASHBOARD_ORIGIN ?? 'http://127.0.0.1:8000';
  for (const path of ['/analysis', '/providers', '/forecasts']) {
    expect((await request.get(origin + path)).status()).toBe(404);
  }
  expect((await request.post(origin + prefix + '/observations')).status()).toBe(405);

  await page.goto('/#country');
  await expect(page.getByText('Synthetic validation database', { exact: true })).toBeVisible();
  const country = page.getByRole('combobox', { name: 'Select country', exact: true });
  await country.selectOption('724');
  await expect(page.locator('#country-heading')).toHaveText('Spain · ESP');

  const coverage = page.locator('[data-dashboard="coverage"]');
  const indicators = page.locator('[data-dashboard="indicators"]');
  const observations = page.locator('[data-dashboard="observations"]');
  const ucdp = page.locator('[data-dashboard="ucdp_observations"]');
  const forecasts = page.locator('[data-dashboard="predictions"]');
  const assessments = page.locator('[data-dashboard="assessments"]');
  await expect(coverage.locator('dd', { hasText: /^available$/ })).toHaveCount(5);
  await expect(indicators).toContainText('Synthetic indicator');
  await expect(indicators).toContainText('synthetic native unit');
  await expect(indicators.locator('dd', { hasText: /^0$/ })).toBeVisible();
  await expect(ucdp).toContainText('annual_historical');
  await expect(ucdp).toContainText('synthetic-ucdp-1');
  await expect(ucdp.locator('dd', { hasText: /^4$/ })).toBeVisible();
  await expect(forecasts).toContainText('Expired (target period ended)');
  await expect(forecasts).toContainText('stale');
  await expect(forecasts).toContainText('native event count');
  await expect(forecasts).toContainText('2020-02-01T00:00:00Z');
  await expect(forecasts).toContainText('2020-03-01T00:00:00Z');
  await expect(forecasts).toContainText('2020-05-01T00:00:00Z');
  await expect(forecasts.locator('dd', { hasText: /^3$/ })).toBeVisible();
  await expect(assessments.locator('dd', { hasText: /^0\.25$/ })).toBeVisible();
  await expect(assessments).toContainText('Unavailable');
  await expect(observations.getByRole('article')).toHaveCount(20);
  await expect(observations).toContainText('ACLED');
  const nextPage = page.waitForResponse((response) =>
    response.url().includes(prefix + '/observations?') && new URL(response.url()).searchParams.get('offset') === '20');
  await observations.getByRole('button', { name: 'Load more' }).click();
  expect((await nextPage).status()).toBe(200);
  await expect(observations.getByRole('article')).toHaveCount(21);
  await expect(observations).toContainText('End of results');
  const end = await request.get(origin + prefix + '/observations?country=ESP&offset=21');
  expect((await end.json()).availability).toBe('end_of_results');

  await country.selectOption('124');
  await expect(coverage.locator('dd', { hasText: /^missing$/ })).toHaveCount(5);
  await expect(page.getByText('No records', { exact: true })).toHaveCount(5);
  await page.goto('/#forecasts');
  await expect(page.locator('[data-dashboard="predictions"]')).toContainText('Synthetic district');
  await expect(page.locator('[data-dashboard="predictions"]')).toContainText('admin1');
});
