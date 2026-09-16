import { expect, test, type Page } from '@playwright/test';

async function signIn(page: Page) {
  await page.goto('/portfolio');
  await expect(page.getByRole('heading', { name: 'Private investment research' })).toBeVisible();
  await page.getByRole('button', { name: 'Explore demo' }).click();
  await expect(page.getByRole('heading', { name: 'Portfolio' })).toBeVisible();
  await cleanupTestPortfolios(page);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Portfolio' })).toBeVisible();
}

async function cleanupTestPortfolios(page: Page) {
  await page.evaluate(async () => {
    const me = await fetch('/api/v1/auth/me').then(response => response.json());
    const list = await fetch('/api/v1/portfolios').then(response => response.json());
    for (const portfolio of list.items.filter((item: { name: string }) => item.name.startsWith('E2E '))) {
      await fetch(`/api/v1/portfolios/${portfolio.id}?revision=${portfolio.revision}`, {
        method: 'DELETE', headers: { 'X-CSRF-Token': me.csrf_token },
      });
    }
  });
}

async function beginDraft(page: Page, name: string) {
  await page.getByRole('button', { name: 'New portfolio' }).click();
  await page.getByLabel('Portfolio name').fill(name);
  await page.getByRole('combobox', { name: 'Search stocks' }).fill('MSFT');
  await page.getByRole('option', { name: /MSFT/ }).click();
}

async function deleteCurrent(page: Page) {
  await page.getByRole('button', { name: 'Delete', exact: true }).click();
  await page.getByRole('dialog', { name: /Delete/ }).getByRole('button', { name: 'Delete portfolio' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Portfolio deleted.' })).toBeVisible();
}

test('saves an incomplete draft, confirms destructive transitions, and runs only at 100%', async ({ page }) => {
  const name = `E2E draft ${Date.now()}`;
  await signIn(page);
  await beginDraft(page, name);

  await expect(page.getByText('0.00%', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run portfolio analysis' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Portfolio saved.' })).toBeVisible();

  await page.getByLabel('Portfolio name').fill(`${name} changed`);
  await page.getByRole('button', { name: 'Reload saved' }).click();
  const discard = page.getByRole('dialog', { name: 'Discard unsaved changes?' });
  await expect(discard).toBeVisible();
  await discard.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(`${name} changed`);
  await page.getByRole('button', { name: 'Reload saved' }).click();
  await discard.getByRole('button', { name: 'Discard changes' }).click();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(name);

  await page.getByLabel('Weight (bps)').fill('10000');
  await page.getByRole('button', { name: 'Run portfolio analysis' }).click();
  await expect(page.getByRole('heading', { name: /Portfolio analytics/ })).toBeVisible();
  await page.getByLabel('Weight (bps)').fill('9000');
  await expect(page.getByRole('heading', { name: /Portfolio analytics/ })).toHaveCount(0);
  await expect(page.getByText('Run analysis after weights total 100.00%.')).toBeVisible();

  await page.reload();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(name);
  await expect(page.getByLabel('Weight (bps)')).toHaveValue('9000');
  await deleteCurrent(page);
});

test('reuses the idempotency key after an ambiguous create failure and keeps the error inline', async ({ page }) => {
  const name = `E2E retry ${Date.now()}`;
  const keys: (string | null)[] = [];
  let creates = 0;
  await page.route('**/api/v1/portfolios', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    creates += 1;
    keys.push(await route.request().headerValue('idempotency-key'));
    if (creates === 1) return route.abort('connectionreset');
    return route.continue();
  });
  await signIn(page);
  await beginDraft(page, name);

  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('main').getByText('Failed to fetch', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Portfolio saved.' })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  await deleteCurrent(page);
});

test('preserves the local draft on a revision conflict and supports save as copy', async ({ page }) => {
  const name = `E2E conflict ${Date.now()}`;
  await signIn(page);
  await beginDraft(page, name);
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Portfolio saved.' })).toBeVisible();

  await page.evaluate(async portfolioName => {
    const me = await fetch('/api/v1/auth/me').then(response => response.json());
    const list = await fetch('/api/v1/portfolios').then(response => response.json());
    const portfolio = list.items.find((item: { name: string }) => item.name === portfolioName);
    const response = await fetch(`/api/v1/portfolios/${portfolio.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': me.csrf_token },
      body: JSON.stringify({ name: `${portfolioName} remote`, positions: portfolio.positions, revision: portfolio.revision }),
    });
    if (!response.ok) throw new Error(await response.text());
  }, name);

  await page.getByLabel('Portfolio name').fill(`${name} local`);
  await page.getByRole('button', { name: 'Save changes' }).click();
  const conflict = page.getByRole('dialog', { name: 'Portfolio changed elsewhere' });
  await expect(conflict).toBeVisible();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(`${name} local`);
  await conflict.getByRole('button', { name: 'Save as copy' }).click();
  await expect(conflict).toBeHidden();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(`${name} local copy`);
  await deleteCurrent(page);
  await cleanupTestPortfolios(page);
});

test('restores an owner-keyed draft after session expiry and refresh', async ({ page }) => {
  const name = `E2E recovery ${Date.now()}`;
  let expireNextCreate = true;
  let expired = false;
  await page.route('**/api/v1/auth/me', route => expired
    ? route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Sign in to continue' }) })
    : route.continue());
  await page.route('**/api/v1/auth/demo', async route => {
    expired = false;
    return route.continue();
  });
  await page.route('**/api/v1/portfolios', async route => {
    if (route.request().method() === 'POST' && expireNextCreate) {
      expireNextCreate = false;
      expired = true;
      return route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Sign in to continue' }) });
    }
    return route.continue();
  });
  await signIn(page);
  await beginDraft(page, name);
  await page.getByLabel('Weight (bps)').fill('1234');
  await page.reload();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(name);
  await expect(page.getByLabel('Weight (bps)')).toHaveValue('1234');

  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'Private investment research' })).toBeVisible();
  await page.getByRole('button', { name: 'Explore demo' }).click();
  await expect(page.getByRole('heading', { name: 'Portfolio' })).toBeVisible();
  await expect(page.getByLabel('Portfolio name')).toHaveValue(name);
  await expect(page.getByLabel('Weight (bps)')).toHaveValue('1234');
});
