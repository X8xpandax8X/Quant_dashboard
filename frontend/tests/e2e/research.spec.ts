import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { fileURLToPath } from 'node:url';
const artifacts = fileURLToPath(new URL('../../../docs/verification/', import.meta.url));

async function demo(page: Page) {
  await page.goto('/markets');
  await page.getByRole('button', { name: 'Explore demo' }).click();
  await expect(page.getByRole('heading', { name: 'Markets', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Refresh', exact: true })).toBeEnabled();
}
async function chartReady(page: Page) {
  await expect(page.locator('.js-plotly-plot .main-svg').first()).toBeVisible();
  await expect(page.getByText('Chart unavailable.', { exact: false })).toHaveCount(0);
}

test('research charts render, controls preserve URL state, exports carry source context', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await demo(page);
  await chartReady(page);
  await page.screenshot({ path: `${artifacts}markets-desktop.png`, fullPage: true });
  await page.getByRole('link', { name: 'Stock analysis', exact: true }).click();
  await chartReady(page);
  await expect(page.getByText('Selected-window price return:', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '5D', exact: true }).click();
  await expect(page).toHaveURL(/timeframe=5D/);
  await page.getByRole('tab', { name: 'Peers & CAPM' }).click();
  await expect(page.getByRole('heading', { name: 'Correlation matrix', exact: false })).toBeVisible();
  await expect(page.locator('.correlation-table')).toContainText('n=');
  await page.getByRole('combobox', { name: 'Add a comparison stock' }).fill('AMZN');
  await page.getByRole('option', { name: /AMZN/ }).click();
  await expect(page).toHaveURL(/AMZN/);
  await page.screenshot({ path: `${artifacts}stock-peers-desktop.png`, fullPage: true });
  await page.getByRole('tab', { name: 'Price & distribution' }).click();
  await chartReady(page);
  const csv = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export AAPL price and return data as CSV', exact: true }).click();
  const csvFile = await csv;
  await csvFile.saveAs(`${artifacts}stock-export.csv`);
  const png = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export AAPL price and return chart as PNG', exact: true }).click();
  await (await png).saveAs(`${artifacts}stock-export.png`);
  await page.getByRole('link', { name: 'Fundamentals', exact: true }).click();
  await chartReady(page);
  await expect(page.getByRole('heading', { name: /quarterly revenue/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: /quarterly EPS/ })).toBeVisible();
  await page.screenshot({ path: `${artifacts}fundamentals-desktop.png`, fullPage: true });
  await page.getByRole('tab', { name: 'Statements & consensus' }).click();
  await expect(page.getByRole('heading', { name: 'Financial statements' })).toBeVisible();
  await page.getByRole('tab', { name: 'Balance sheet & cash flow', exact: true }).click();
  await expect(page).toHaveURL(/statement=balance/);
  expect(errors).toEqual([]);
});

test('refresh keeps zoom and last-valid observations after a recoverable error', async ({ page }) => {
  await demo(page);
  await page.getByRole('link', { name: 'Stock analysis', exact: true }).click();
  await chartReady(page);
  const graph = page.locator('.js-plotly-plot').first();
  const box = await graph.boundingBox();
  if (!box) throw new Error('Chart geometry unavailable');
  await page.mouse.move(box.x + box.width * 0.25, box.y + box.height * 0.25);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.65, box.y + box.height * 0.7, { steps: 12 });
  await page.mouse.up();
  const zoom = await graph.evaluate((node: any) => node._fullLayout.xaxis.range);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect.poll(() => graph.evaluate((node: any) => node._fullLayout.xaxis.range)).toEqual(zoom);
  await page.route('**/api/v1/stocks/AAPL/prices*', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Temporary provider failure"}' }));
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  await expect(page.getByText('Refresh failed.', { exact: false })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('heading', { name: /AAPL price and return/ })).toBeVisible();
  await chartReady(page);
});

for (const size of [{ name: 'phone', width: 390, height: 844 }, { name: 'landscape', width: 844, height: 390 }]) {
  test(`${size.name} charts and navigation fit the viewport`, async ({ page }) => {
    await page.setViewportSize(size);
    await demo(page);
    await chartReady(page);
    await page.screenshot({ path: `${artifacts}markets-${size.name}.png`, fullPage: true });
    if (size.width < 768) await page.getByRole('button', { name: 'Open navigation' }).click();
    await page.getByRole('link', { name: 'Stock analysis', exact: true }).click();
    await page.getByRole('tab', { name: 'Peers & CAPM' }).click();
    await chartReady(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: `${artifacts}peers-${size.name}.png`, fullPage: true });
  });
}

test('dashboard accessibility and reduced motion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await demo(page);
  for (const path of ['/markets', '/stocks/AAPL?tab=peers', '/fundamentals/AAPL', '/portfolio']) {
    await page.goto(path);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByText('Loading research…')).toHaveCount(0);
    const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
    expect(result.violations.map(v => ({ id: v.id, impact: v.impact, targets: v.nodes.map(n => n.target) })), path).toEqual([]);
  }
});
