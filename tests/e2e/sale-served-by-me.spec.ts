// flow: SALE-F16 (atribuir a quien tiene la sesión con «Atiende yo») — the till's «Served by me» in Chrome,
// on the real stack (Sales, Inventory, Staff), no mocks. The owner's account first has no record in Staff:
// «Who is serving this check» warns that a sale left on «Me» counts for nobody (seen at 390×844, 834×1112
// and 1440×900, `.artifacts/FIX-SALE-SERVED-BY-ME-NOT-ATTRIBUTED-<width>.png`). Then the account gets its
// record: the warning is gone, a sale charged by card with the chip still on «Me» is the record's (the till
// sends nobody: the server resolves «Me»), and Staff → Commissions counts it for that record. What the run
// creates is named «E2E…» and removed after it; a record the account already had is unlinked for the run
// and linked back after it.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, newestSaleOf, stamp } from './sale-helpers';

const RUN = stamp();
const TAG = `E2E Me ${RUN}`;
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;
const UNLINKED = 'Your account has no record in Staff: left on «Me», this sale counts for nobody.';

let product: Product;
let userId: number;
/** The live record the owner's account already had, unlinked while the spec runs. */
let kept: string | null = null;

test.use({ locale: 'en-US' });

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  const me = await api<{ user: { id: string } }>(context, A, 'GET', '/me');
  userId = Number(me.data.user.id);
  const current = await api<{ member: { id: string } | null }>(context, A, 'GET', '/staff/members/current');
  expect(current.status, 'whose record the session is').toBe(200);
  kept = current.data.member?.id ?? null;
  if (kept) psql(`update staff_member set user_id = null where id = '${kept}'`);
  product = await createProduct(context, { name: `E2E Shampoo ${RUN}`, sku: `E2E-ME-${RUN}`, price: 1210, tax_category_key: 'product.generic' });
  // The owner's session for the fleet's visual sweep of the till (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
    psql(`delete from staff_member where first_name = '${TAG}'`);
  } finally {
    if (kept) psql(`update staff_member set user_id = ${userId} where id = '${kept}'`);
  }
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${product.id}]`).waitFor({ state: 'visible' });
}

/** The check on screen: on a phone it is the drawer behind its button. */
async function cartReady(page: Page): Promise<void> {
  await tillReady(page);
  const fab = page.locator('[data-testid=pos-cart-fab]');
  if (await fab.isVisible()) await fab.click();
  await shown(page).locator('[data-testid=pos-staff-chip]').waitFor({ state: 'visible' });
}

async function openPicker(page: Page): Promise<void> {
  await cartReady(page);
  await shown(page).locator('[data-testid=pos-staff-chip]').click();
  await page.locator('[data-testid=pos-staff-me]:visible').waitFor({ state: 'visible' });
}

async function closePicker(page: Page): Promise<void> {
  await page.locator('[data-testid=pos-staff-cancel]:visible').click();
  await expect(page.locator('[data-testid=pos-staff-me]:visible')).toHaveCount(0);
}

test('SALE-F16 (atribuir a quien tiene la sesión con «Atiende yo»): without a record in Staff, «Me» warns the sale counts for nobody', async ({ page }) => {
  await login(page, A, '/sale/pos');
  await expect(shown(page).locator('[data-testid=pos-staff-chip]')).toContainText('Served by me');
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await openPicker(page);
    const warning = page.locator('[data-testid=pos-staff-unlinked]:visible');
    await expect(warning).toHaveText(UNLINKED);
    // The sheet slides up from the bottom: the shot waits until all of it, the warning and «Cancel», is in view.
    await expect(warning).toBeInViewport({ ratio: 1 });
    await expect(page.locator('[data-testid=pos-staff-cancel]:visible')).toBeInViewport({ ratio: 1 });
    await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
    await page.screenshot({ path: shot(`FIX-SALE-SERVED-BY-ME-NOT-ATTRIBUTED-${viewport.label}`) });
    await closePicker(page);
  }
});

test('SALE-F16 (atribuir a quien tiene la sesión con «Atiende yo»): a sale charged on «Me» counts in Commissions for the record of whoever charged it', async ({ page, context }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  const record = await api<{ id: string }>(context, A, 'POST', '/staff/members', {
    first_name: TAG,
    last_name: 'Till',
    user_id: userId,
    commission_rate: '10',
  });
  expect(record.status, `the record ${JSON.stringify(record.data)}`).toBe(201);

  // The picker asks whose record the session is each time it opens: no reload needed.
  await openPicker(page);
  await expect(page.locator('[data-testid=pos-staff-unlinked]')).toHaveCount(0);
  await closePicker(page);

  // The chip stays on «Me»: the till sends nobody and the server attributes the sale to the record.
  await shown(page).locator(`[data-testid=pos-product-${product.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-staff-chip]')).toContainText('Served by me');
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  const methods = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  const card = methods.data.rows.find((row) => row.type === 'card')?.id ?? '';
  await sheet.locator(`[data-testid=sale-checkout-method-${card}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  await page.locator('[data-testid=sale-document-close]').click();

  const sale = (await newestSaleOf(context, product.sku)) as Awaited<ReturnType<typeof newestSaleOf>> & { staff_id: string | null };
  expect(sale.staff_id, 'the sale is the record of whoever charged it').toBe(record.data.id);
  const report = await api<{ rows: { member_id: string; sold: number; commission: number }[] }>(context, A, 'GET', '/staff/commissions/report');
  expect(report.data.rows.find((row) => row.member_id === record.data.id)).toMatchObject({ sold: 1210, commission: 121 });

  await page.goto(`${A}/staff/commissions`);
  const row = shown(page).locator(`[data-testid=staff-commissions-row][data-id="${record.data.id}"]`);
  await expect(row).toContainText('€12.10');
  await expect(row).toContainText('€1.21');
});
