import { expect, test } from '@playwright/test';

async function demo(page: import('@playwright/test').Page) {
  await page.goto('/markets');
  await expect(page.getByRole('heading', { name: 'Private investment research' })).toBeVisible();
  await page.getByRole('button', { name: 'Explore demo' }).click();
  await expect(page.getByRole('heading', { name: 'Markets' })).toBeVisible();
}

test('demo entry and four research routes render', async ({ page }) => {
  await demo(page);
  await page.getByRole('link', { name: 'Stock analysis' }).click();
  await expect(page.getByRole('heading', { name: 'Stock analysis' })).toBeVisible();
  await page.getByRole('link', { name: 'Fundamentals' }).click();
  await expect(page.getByRole('heading', { name: 'Fundamentals' })).toBeVisible();
  await page.getByRole('link', { name: 'Portfolio' }).click();
  await expect(page.getByRole('heading', { name: 'Portfolio' })).toBeVisible();
});

test('portfolio prevents an incomplete draft from running', async ({ page }) => {
  await demo(page);
  await page.getByRole('link', { name: 'Portfolio' }).click();
  await page.getByRole('button', { name: 'New portfolio' }).click();
  await expect(page.getByText('Add at least one position.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run portfolio analysis' })).toBeDisabled();
});

test('mobile navigation remains keyboard operable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await demo(page);
  await page.getByRole('button', { name: 'Open navigation' }).press('Enter');
  await expect(page.getByRole('dialog', { name: 'Navigate' })).toBeVisible();
  await page.getByRole('link', { name: 'Portfolio' }).click();
  await expect(page.getByRole('heading', { name: 'Portfolio' })).toBeVisible();
});
