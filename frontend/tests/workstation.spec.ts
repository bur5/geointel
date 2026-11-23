import { expect, test } from '@playwright/test';

test('all navigation destinations have headings and support browser history', async ({ page }) => {
  await page.goto('/?mode=demo');
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
  await page.goto('/?mode=demo');
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
  await page.goto('/?mode=demo');
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
  await page.goto('/?mode=demo#risk');
  await page.getByRole('combobox', { name: 'Country', exact: true }).selectOption('804');
  await expect(page.getByText('New synthetic event cluster')).toBeVisible();
  await page.getByLabel('Snapshot period').selectOption('2');
  await expect(page.getByText('Reporting volume increases')).toHaveCount(0);
  await expect(page.getByText('+5 pts')).toBeVisible();
  await page.getByRole('combobox', { name: 'Country', exact: true }).selectOption('124');
  await expect(page.getByText('Country data unavailable')).toBeVisible();
});

test('briefings can filter by region, country and date and open provenance', async ({ page }) => {
  await page.goto('/?mode=demo#briefings');
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
  await page.goto('/?mode=demo#analyst');
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

test('mobile layout keeps navigation, map, and country controls within the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?mode=demo');
  await expect(page.getByRole('heading', { name: 'Global Overview' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  await page.getByRole('combobox', { name: 'Select country', exact: true }).selectOption('104');
  await expect(page.locator('#country-heading')).toHaveText('Myanmar');
});
