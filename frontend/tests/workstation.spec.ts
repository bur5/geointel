import { expect, test } from '@playwright/test';

test('all navigation destinations have headings and support browser history', async ({ page }) => {
  await page.goto('/');
  for (const title of ['Country Intelligence', 'Risk Monitoring', 'Forecasts', 'Intelligence Briefings', 'AI Analyst', 'Global Overview']) {
    const link = page.getByRole('navigation').getByRole('link', { name: title, exact: true });
    await link.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
    await expect(link).toHaveAttribute('aria-current', 'page');
  }
  await page.goBack();
  await expect(page.getByRole('heading', { level: 1, name: 'AI Analyst' })).toBeVisible();
});

test('the map colors synthetic scores, supports zoom and panning, and selects a country', async ({ page }) => {
  await page.goto('/');
  const map = page.locator('#map');
  await expect(map.locator('[data-country="729"]')).toHaveClass('country high');
  await expect(map.locator('[data-country="124"]')).toHaveClass('country ');
  await expect(page.locator('.map-legend')).toContainText('Unavailable');
  await map.locator('[data-country="729"]').click();
  await expect(page.locator('#country-heading')).toHaveText('Sudan');
  await expect(map.locator('[data-country="729"]')).toHaveClass('country high selected');
  await page.getByRole('button', { name: 'Zoom in' }).click();
  const layer = map.locator('g');
  const zoomed = await layer.getAttribute('transform');
  expect(zoomed).toContain('scale(1.4)');
  await map.locator('svg').focus();
  await page.keyboard.press('ArrowRight');
  await expect(layer).not.toHaveAttribute('transform', zoomed!);
  await page.getByRole('button', { name: 'Reset map' }).click();
  await expect(layer).toHaveAttribute('transform', 'translate(0 0) scale(1)');
});

test('keyboard selection preserves focus and reports missing country data', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to workspace' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();
  const select = page.getByRole('combobox', { name: 'Select country', exact: true });
  await select.focus();
  await page.keyboard.press('Home');
  await expect(select).toBeFocused();
  await expect(page.locator('#country-heading')).toHaveText('Afghanistan');
  await expect(page.getByText('Country data unavailable')).toBeVisible();
});

test('country and period controls filter monitoring data', async ({ page }) => {
  await page.goto('/#risk');
  await page.getByRole('combobox', { name: 'Country', exact: true }).selectOption('804');
  await expect(page.getByText('New synthetic event cluster')).toBeVisible();
  await page.getByLabel('Snapshot period').selectOption('2');
  await expect(page.getByText('Reporting volume increases')).toHaveCount(0);
  await expect(page.getByText('+5 pts')).toBeVisible();
  await page.getByRole('combobox', { name: 'Country', exact: true }).selectOption('124');
  await expect(page.getByText('Country data unavailable')).toBeVisible();
});

test('briefings can filter by region, country and date and open provenance', async ({ page }) => {
  await page.goto('/#briefings');
  await page.getByLabel('Region').selectOption('South America');
  await expect(page.locator('article')).toHaveCount(2);
  await page.getByLabel('Country').selectOption('170');
  await expect(page.locator('article')).toHaveCount(1);
  await page.locator('summary').click();
  await expect(page.getByRole('heading', { name: 'Simulated observations' })).toBeVisible();
  await page.getByRole('link', { name: '[GEOINTEL synthetic fixture v0.1]' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
  await page.getByLabel('Published on or after').fill('2025-04-01');
  await expect(page.getByText('No matching briefings')).toBeVisible();
});

test('chat keeps scripted replies and the country context of each message', async ({ page }) => {
  await page.goto('/#analyst');
  await page.getByRole('button', { name: 'Describe forecast uncertainty' }).click();
  await expect(page.getByRole('log')).toContainText('69–90 index points');
  await page.getByLabel('Country context').selectOption('124');
  await page.getByLabel('Message', { exact: true }).fill('Any updates?');
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(page.getByRole('log')).toContainText('YOU · Canada');
  await expect(page.getByRole('log')).toContainText('Country data unavailable');
  await expect(page.getByRole('log')).toContainText('YOU · Ukraine');
  await page.getByLabel('Data mode').selectOption('api');
  await expect(page.getByRole('log')).toHaveCount(0);
  await expect(page.getByText('AI Analyst conversations unavailable')).toBeVisible();
});

test('API forecast failure, retry, malformed data, and empty responses never fall back to fixtures', async ({ page }) => {
  let response = 0;
  await page.route('**/geointel-api/forecasts', async (route) => {
    response += 1;
    if (response === 1) await route.fulfill({ status: 503, json: {} });
    else if (response === 2) await route.fulfill({ json: [{ id: 'bad payload' }] });
    else await route.fulfill({ json: [] });
  });
  await page.goto('/#forecasts');
  await expect(page.getByText('Illustrative index interval').first()).toBeVisible();
  expect(response).toBe(0);
  await page.getByLabel('Data mode').selectOption('api');
  await expect(page.getByRole('alert')).toContainText('Forecast API unavailable');
  await expect(page.getByText('Illustrative index interval')).toHaveCount(0);
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByRole('alert')).toContainText('Forecast API unavailable');
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText('No forecasts')).toBeVisible();
  await page.getByRole('link', { name: 'Global Overview' }).click();
  await expect(page.locator('[data-country="729"]')).not.toHaveClass(/high/);
  await expect(page.getByText('Country indicators, events and forecasts unavailable')).toBeVisible();
});

const apiForecast = {
  id: 'e25a07dc-1835-4c6e-896c-ad9324ec1ad4',
  analysis_run_id: 'ac66759c-20f5-4eab-bb13-c4dff12a8301',
  conflict_type: 'internal_armed_conflict',
  question: 'Test forecast',
  horizon_months: 3, version: 2, probability_low: .15, probability_high: .26,
  confidence: 'low', rationale: 'Fixture rationale', evidence_for: ['Evidence item'], evidence_against: [],
  unknowns: ['Unknown item'], resolution_criteria: [], change_conditions: [], created_at: '2025-02-28T08:00:00Z',
};

test('API forecasts retain probability bounds, timestamps, provenance, and uncertainty', async ({ page }) => {
  await page.route('**/geointel-api/forecasts', (route) => route.fulfill({ json: [apiForecast] }));
  await page.goto('/?mode=api#forecasts');
  await expect(page.getByRole('heading', { name: 'Test forecast' })).toBeVisible();
  await expect(page.getByText('15% – 26%')).toBeVisible();
  await expect(page.getByText('3 month(s) · Version 2')).toBeVisible();
  await expect(page.getByText(apiForecast.created_at)).toBeVisible();
  await expect(page.getByText(`Analysis run ${apiForecast.analysis_run_id} · Forecast ${apiForecast.id}`)).toBeVisible();
  await page.getByText('Evidence and uncertainty').click();
  await expect(page.getByText('Evidence item')).toBeVisible();
  await expect(page.getByText('Unknown item')).toBeVisible();
});

for (const [description, overrides] of [
  ['invalid forecast UUID', { id: 'forecast-01' }],
  ['invalid analysis UUID', { analysis_run_id: '' }],
  ['unknown conflict type', { conflict_type: 'civil' }],
  ['unknown confidence', { confidence: 'certain' }],
  ['negative horizon', { horizon_months: -1 }],
  ['out-of-range horizon', { horizon_months: 121 }],
  ['version zero', { version: 0 }],
  ['unsafe integer version', { version: Number.MAX_SAFE_INTEGER + 1 }],
  ['date without time', { created_at: '2025-02-28' }],
  ['invalid calendar date', { created_at: '2025-02-30T08:00:00Z' }],
  ['out-of-range probability', { probability_high: 1.01 }],
  ['reversed interval', { probability_low: .9 }],
  ['missing bound', { probability_low: undefined }],
  ['missing evidence array', { evidence_for: undefined }],
  ['structured evidence in string array', { evidence_for: [{ title: 'Evidence' }] }],
] as const) {
  test(`API rejects ${description} without rendering either row or fixtures`, async ({ page }) => {
    await page.route('**/geointel-api/forecasts', (route) =>
      route.fulfill({ json: [apiForecast, { ...apiForecast, ...overrides }] }));
    await page.goto('/?mode=api#forecasts');
    await expect(page.getByRole('alert')).toContainText('Forecast API unavailable');
    await expect(page.locator('.forecast, .synthetic')).toHaveCount(0);
  });
}

test('API renders untrusted text literally and accepts nullable bounds and stored timestamps', async ({ page }) => {
  const text = '<em data-audit-marker>Untrusted source text</em>';
  await page.route('**/geointel-api/forecasts', (route) => route.fulfill({ json: [
    { ...apiForecast, question: text, rationale: text, evidence_for: [text], probability_low: 0,
      probability_high: 1, created_at: '2025-02-28T08:00:00.123456+05:30' },
    { ...apiForecast, probability_low: null, probability_high: null, created_at: '2025-02-28T08:00:00.123456' },
    { ...apiForecast, probability_low: null, probability_high: .5 },
  ] }));
  await page.goto('/?mode=api#forecasts');
  const cards = page.locator('.forecast');
  await expect(cards).toHaveCount(3);
  await expect(cards.first().getByRole('heading', { name: text })).toBeVisible();
  await expect(cards.first().getByText('0% – 100%')).toBeVisible();
  await cards.first().getByText('Evidence and uncertainty').click();
  await expect(cards.first().locator('li').filter({ hasText: text })).toBeVisible();
  await expect(cards.nth(1).getByText('Unavailable', { exact: true }).first()).toBeVisible();
  await expect(cards.nth(2).getByText('Unavailable', { exact: true }).first()).toBeVisible();
  await expect(page.locator('[data-audit-marker], .synthetic')).toHaveCount(0);
});

test('mobile layout keeps navigation, map, and country controls within the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Global Overview' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole('combobox', { name: 'Select country', exact: true }).selectOption('104');
  await expect(page.locator('#country-heading')).toHaveText('Myanmar');
});
