import { expect, test } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';

const fixture = readFileSync(new URL('./fixture-risk.json', import.meta.url), 'utf8');
const hazards = readFileSync(new URL('./fixture-hazards.json', import.meta.url), 'utf8');
const shots = process.env.GEOINTEL_SCREENSHOTS;
const shoot = async (page: import('@playwright/test').Page, name: string) => {
  if (!shots) return;
  mkdirSync(shots, { recursive: true });
  await page.screenshot({ path: `${shots}/${name}.png`, fullPage: true });
};

test.beforeEach(async ({ page }) => {
  await page.route('**/data/risk.json', (route) => route.fulfill({ body: fixture, contentType: 'application/json' }));
  await page.route('**/data/hazards.json', (route) => route.fulfill({ body: hazards, contentType: 'application/json' }));
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
  await shoot(page, 'country-japan');
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
