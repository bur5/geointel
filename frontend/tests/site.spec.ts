import { expect, test } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';

const fixture = readFileSync(new URL('./fixture-risk.json', import.meta.url), 'utf8');
const hazards = readFileSync(new URL('./fixture-hazards.json', import.meta.url), 'utf8');
const scenarios = readFileSync(new URL('./fixture-scenarios.json', import.meta.url), 'utf8');
const links = readFileSync(new URL('./fixture-links.json', import.meta.url), 'utf8');
const signals = readFileSync(new URL('./fixture-signals.json', import.meta.url), 'utf8');
const backtest = readFileSync(new URL('./fixture-backtest.json', import.meta.url), 'utf8');
const accuracy = readFileSync(new URL('./fixture-accuracy.json', import.meta.url), 'utf8');
const shots = process.env.GEOINTEL_SCREENSHOTS;
const shoot = async (page: import('@playwright/test').Page, name: string) => {
  if (!shots) return;
  mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};

test.beforeEach(async ({ page }) => {
  await page.route('**/data/risk.json', (route) => route.fulfill({ body: fixture, contentType: 'application/json' }));
  await page.route('**/data/hazards.json', (route) => route.fulfill({ body: hazards, contentType: 'application/json' }));
  await page.route('**/data/scenarios.json', (route) => route.fulfill({ body: scenarios, contentType: 'application/json' }));
  await page.route('**/data/links.json', (route) => route.fulfill({ body: links, contentType: 'application/json' }));
  await page.route('**/data/signals.json', (route) => route.fulfill({ body: signals, contentType: 'application/json' }));
  await page.route('**/data/backtest.json', (route) => route.fulfill({ body: backtest, contentType: 'application/json' }));
  await page.route('**/data/accuracy.json', (route) => route.fulfill({ body: accuracy, contentType: 'application/json' }));
});

test('overview renders live snapshot with map and ranking', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Где в мире сейчас опаснее всего');
  await expect(page.locator('#map path.country.active').first()).toBeVisible();
  await expect(page.locator('.ranking button')).not.toHaveCount(0);
  await shoot(page, 'overview-desktop');
  await page.getByRole('button', { name: '10 лет' }).click();
  await expect(page.getByRole('button', { name: '10 лет' })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('[data-field="type"]').selectOption('major_earthquake');
  await expect(page.locator('#map')).toBeVisible();
  await page.locator('[data-field="type"]').selectOption('view_travel');
  await expect(page.locator('#map path.country.v-critical').first()).toBeVisible();
  await shoot(page, 'overview-travel');
  await page.locator('[data-field="type"]').selectOption('internal_armed_conflict');
  await page.getByRole('button', { name: 'Блокам' }).click();
  await expect(page.locator('.group-card').first()).toBeVisible();
  await shoot(page, 'overview-blocs');
  await page.setViewportSize({ width: 390, height: 844 });
  await shoot(page, 'overview-mobile');
  expect(errors).toEqual([]);
});

test('country, changes, assistant and method pages; language switch', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/#country');
  await page.locator('[data-field="country"]').selectOption('SDN');
  await expect(page.locator('.risk-block').first()).toBeVisible();
  await expect(page.locator('#hazards')).toContainText('Серьёзных стихийных бедствий');
  await shoot(page, 'country');
  await page.locator('[data-field="country"]').selectOption('JPN');
  await expect(page.locator('.hazard-card').first()).toBeVisible();
  await expect(page.locator('.country-map circle').first()).toBeVisible();
  await expect(page.locator('.verdict')).toHaveCount(3);
  await expect(page.locator('.ctx')).not.toHaveCount(0);
  await shoot(page, 'country-japan');
  await page.locator('[data-field="country"]').selectOption('USA');
  await expect(page.locator('.verdict').first()).not.toContainText('Не ехать');
  await page.goto('/#changes');
  await expect(page.locator('.changes li')).toHaveCount(1);
  await shoot(page, 'changes');
  await page.goto('/#assistant');
  await expect(page.locator('.notice')).toBeVisible();
  await page.goto('/#method');
  await expect(page.getByRole('heading', { name: 'Источники данных' })).toBeVisible();
  await shoot(page, 'method');
  await page.getByRole('button', { name: 'English' }).click();
  await expect(page.getByRole('heading', { name: 'Data sources' })).toBeVisible();
});

test('scenarios, links graph and migration', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/#scenarios');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Сценарии');
  await expect(page.locator('.scenario-tabs button')).toHaveCount(7);
  await page.locator('[data-scenario="russia_nato"]').first().click();
  await expect(page.locator('#scenario-detail h2')).toHaveText('Военное нападение России на страну НАТО');
  await expect(page.locator('.table.comp tbody tr')).not.toHaveCount(0);
  await expect(page.locator('.indicators li')).not.toHaveCount(0);
  await expect(page.locator('#scenario-map path.country.role-party').first()).toBeVisible();
  await expect(page.locator('.role-group')).toHaveCount(4);
  await expect(page.locator('#scenario-tree tbody tr')).not.toHaveCount(0);
  await shoot(page, 'scenarios');
  await page.locator('[data-scenario="china_taiwan"]').first().click();
  await expect(page.locator('.table.comp')).toContainText('Polymarket');
  await shoot(page, 'scenarios-taiwan');

  await page.goto('/#country');
  await page.locator('[data-field="country"]').selectOption('DEU');
  await expect(page.locator('#country-scenarios .sc-card').first()).toBeVisible();
  await expect(page.locator('.link-graph .node').first()).toBeVisible();
  await page.locator('[data-chain="migration"]').click();
  await expect(page.locator('[data-chain="migration"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#country-migration .ctx').first()).toBeVisible();
  await shoot(page, 'country-germany-links');
  await page.locator('[data-field="country"]').selectOption('UKR');
  await expect(page.locator('.link-list li').first()).toBeVisible();
  await shoot(page, 'country-ukraine-links');

  await page.goto('/#migration');
  await expect(page.locator('#migration-map path.country.critical, #migration-map path.country.high, #migration-map path.country.elevated').first()).toBeVisible();
  await expect(page.locator('.routes li')).not.toHaveCount(0);
  await page.locator('[data-migmode="abroad"]').click();
  await expect(page.locator('[data-migmode="abroad"]')).toHaveAttribute('aria-pressed', 'true');
  await shoot(page, 'migration');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#scenarios');
  await shoot(page, 'scenarios-mobile');
  expect(errors).toEqual([]);
});

test('warning signs: signals page, country section and backtest', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('/#signals');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Сигналы');
  await expect(page.locator('#signals-map path.country.elevated').first()).toBeVisible();
  await expect(page.locator('.table tbody tr')).not.toHaveCount(0);
  await shoot(page, 'signals');
  await page.goto('/#country');
  await page.locator('[data-field="country"]').selectOption('UKR');
  await expect(page.locator('#country-signals .sig').first()).toBeVisible();
  await expect(page.locator('#country-signals .adjusted li').first()).toBeVisible();
  await shoot(page, 'country-ukraine-signals');
  await page.goto('/#accuracy');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Насколько мы точны');
  await expect(page.locator('.bt-chart path.bt-month')).toBeVisible();
  await expect(page.locator('svg.spark').first()).toBeVisible();
  await shoot(page, 'accuracy');
  expect(errors).toEqual([]);
});
