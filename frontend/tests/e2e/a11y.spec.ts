import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('sign-in screen has no critical accessibility violations', async ({ page }) => {
  await page.goto('/markets');
  await expect(page.getByRole('heading', { name: 'Private investment research' })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter(v => ['critical', 'serious'].includes(v.impact || '')).map(v => v.id)).toEqual([]);
});
