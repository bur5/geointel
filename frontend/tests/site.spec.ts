import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';

const fixture = readFileSync(new URL('./fixture-risk.json', import.meta.url), 'utf8');

test.beforeEach(async ({ page }) => {
  await page.route('**/data/risk.json', (route) => route.fulfill({ body: fixture, contentType: 'application/json' }));
});

test('overview renders live snapshot with map and ranking', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('Глобальный обзор');
  await expect(page.locator('#map path.country.active').first()).toBeVisible();
  await expect(page.locator('.watchlist button')).not.toHaveCount(0);
  await page.getByRole('button', { name: '10 лет' }).click();
  await expect(page.getByRole('button', { name: '10 лет' })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('[data-field="type"]').selectOption('major_earthquake');
  await expect(page.locator('#map-heading')).toBeVisible();
  expect(errors).toEqual([]);
});

test('country, changes and method pages; language switch', async ({ page }) => {
  await page.goto('/#country');
  await page.locator('[data-field="country"]').selectOption('SDN');
  await expect(page.locator('.risk-table tbody tr').first()).toBeVisible();
  await page.goto('/#changes');
  await expect(page.locator('.changes li')).toHaveCount(1);
  await page.goto('/#method');
  await expect(page.getByRole('heading', { name: 'Источники данных' })).toBeVisible();
  await page.getByRole('button', { name: 'EN' }).click();
  await expect(page.getByRole('heading', { name: 'Data sources' })).toBeVisible();
});
