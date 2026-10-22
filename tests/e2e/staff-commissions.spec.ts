// flow: STAFF-F21 (paso 3: la comisión del día) — Staff → Commissions in Chrome, on the real stack: two
// professionals with their commission, real sales of a real Inventory product charged by card (one line
// done by the other professional, one sale partly refunded), and the owner's «Commissions» tab: what each
// one sold «Today» with the refund taken off whoever sold it, their rate and their commission, the totals,
// a new charge painted live, «Yesterday» and a custom range whose «To» before «From» is said under «To».
// Seen at 390×844, 834×1112 and 1440×900 (`.artifacts/FIX-STAFF-COMMISSION-SCREEN-<width>.png`). An
// employee has no Commissions tab, the page tells them «You do not have permission» and the API refuses.
// Setup goes through the apps' own APIs (Staff, Inventory, Sales); what the run creates is named «E2E…»
// and removed after it (and before, if a run died half-way).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';

const TAG = 'E2E';
const SKU = `E2E-COM-${stamp()}`;
const CARD = [{ method: 'card' }];
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

interface Member {
  id: string;
  full_name: string;
}

interface ReportRow {
  member_id: string;
  sold: number;
  commission: number;
}

function cleanupStaff(): void {
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(() => {
  cleanupStaff();
  // Card charges issue tickets when the hub has an issuer: the cleanup gives their numbers back.
  snapshotSeries();
});

test.afterAll(() => {
  cleanSales();
  cleanInventory();
  cleanupStaff();
});

async function signedIn(browser: Browser, next: string, credentials?: Credentials): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

async function member(context: BrowserContext, first: string, rate: string): Promise<Member> {
  const res = await api<Member>(context, A, 'POST', '/staff/members', { first_name: `${TAG} ${first}`, last_name: `Commission${stamp()}`, commission_rate: rate });
  expect(res.status, `member ${first}`).toBe(201);
  return res.data;
}

async function refund(context: BrowserContext, sale: SaleOut, amount: number): Promise<void> {
  const res = await api(context, A, 'POST', '/sale/sales/refund', {
    sale_id: sale.id,
    reason: 'unhappy',
    allocations: [{ payment_id: sale.payments[0].id, amount }],
  });
  expect(res.status, `refund ${JSON.stringify(res.data)}`).toBe(200);
}

/** The report as the server gives it (evidence, never the check of the screen). */
async function reported(context: BrowserContext, id: string): Promise<ReportRow | undefined> {
  const res = await api<{ rows: ReportRow[] }>(context, A, 'GET', '/staff/commissions/report');
  expect(res.status).toBe(200);
  return res.data.rows.find((row) => row.member_id === id);
}

/** A professional's row (or, on a phone, their card) in the Commissions list. */
const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=staff-commissions-row][data-id="${id}"]`);

async function pickPeriod(page: Page, value: string): Promise<void> {
  await shown(page).locator(`[data-testid=staff-commissions-period-${value}]`).click();
}

test('STAFF-F21 (paso 3: la comisión del día): the owner sees what each professional sold today, refunds taken off, and their commission', async ({ browser }) => {
  test.setTimeout(180_000);
  const { context, page } = await signedIn(browser, '/staff/commissions');
  try {
    const ana = await member(context, 'Ana', '15');
    const luis = await member(context, 'Luis', '10');
    await createProduct(context, { name: 'E2E Cut', sku: SKU, price: 1800, tax_category_key: 'product.generic' });
    // Ana serves three sales of 18.00 €: Luis did the line of the second (a line's professional wins over
    // the sale's), and 10.00 € of the third go back to the customer, off Ana, who sold it.
    await chargeByApi(context, { lines: [{ product: SKU }], staff_id: ana.id, payments: CARD });
    await chargeByApi(context, { lines: [{ product: SKU, staff_id: luis.id }], staff_id: ana.id, payments: CARD });
    await refund(context, await chargeByApi(context, { lines: [{ product: SKU }], staff_id: ana.id, payments: CARD }), 1000);
    // The server: Ana 18.00 + 8.00 = 26.00 € at 15 % = 3.90 €; Luis 18.00 € at 10 % = 1.80 €.
    expect(await reported(context, ana.id)).toMatchObject({ sold: 2600, commission: 390 });
    expect(await reported(context, luis.id)).toMatchObject({ sold: 1800, commission: 180 });

    await page.goto(`${A}/staff/commissions`);
    const view = shown(page);
    await expect(view.locator('[data-testid=staff-commissions-period-today]')).toHaveClass(/segment-button-checked/);
    await expect(rowOf(page, ana.id)).toContainText('€26.00');
    await expect(rowOf(page, ana.id)).toContainText('15 %');
    await expect(rowOf(page, ana.id)).toContainText('€3.90');
    await expect(rowOf(page, luis.id)).toContainText('€18.00');
    await expect(rowOf(page, luis.id)).toContainText('€1.80');
    await expect(view.locator('ion-footer ion-segment-button', { hasText: 'Commissions' })).toHaveClass(/segment-button-checked/);

    // A new charge reaches the screen by itself, with no reload.
    await chargeByApi(context, { lines: [{ product: SKU }], staff_id: luis.id, payments: CARD });
    await expect(rowOf(page, luis.id)).toContainText('€36.00');
    await expect(rowOf(page, luis.id)).toContainText('€3.60');

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      // On a phone the rows turn into cards: what was painted is painted again, so it retries.
      await expect(async () => {
        await rowOf(page, ana.id).scrollIntoViewIfNeeded({ timeout: 2000 });
        await expect(rowOf(page, ana.id)).toBeInViewport({ timeout: 1000 });
      }, `Ana at ${viewport.label}`).toPass();
      await expect(rowOf(page, ana.id)).toContainText('€3.90');
      await page.screenshot({ path: shot(`FIX-STAFF-COMMISSION-SCREEN-${viewport.label}`) });
    }
    await page.setViewportSize({ width: 1440, height: 900 });

    // Yesterday: nothing sold by either (they are listed, with 0).
    await pickPeriod(page, 'yesterday');
    await expect(rowOf(page, ana.id)).toContainText('€0.00');
    await expect(rowOf(page, luis.id)).toContainText('€0.00');

    // Custom: «From» and «To» start at the days on screen; a «To» before «From» is said under «To».
    await pickPeriod(page, 'custom');
    const from = view.locator('[data-testid=staff-commissions-from] input');
    const to = view.locator('[data-testid=staff-commissions-to] input');
    await expect(from).not.toHaveValue('');
    await expect(to).toHaveValue(await from.inputValue());
    await to.fill('2020-01-01');
    await expect(view.locator('[data-testid=staff-commissions-to]')).toContainText('The end date cannot be before the start date.');

    await pickPeriod(page, 'today');
    await expect(rowOf(page, ana.id)).toContainText('€3.90');
  } finally {
    await context.close();
  }
});

test('STAFF-F21 (paso 3: la comisión del día): an employee has no Commissions tab, the page refuses and so does the API', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members', EMPLOYEE);
  try {
    const view = shown(page);
    await view.locator('[data-testid=staff-members-row], [data-testid=staff-members-empty]').first().waitFor({ state: 'visible' });
    await expect(view.locator('ion-footer ion-segment-button')).toHaveCount(4);
    await expect(view.locator('ion-footer ion-segment-button', { hasText: 'Commissions' })).toHaveCount(0);

    await page.goto(`${A}/staff/commissions`);
    await expect(shown(page).locator('[data-testid=staff-commissions-forbidden]')).toContainText('You do not have permission');
    const refused = await api<{ error?: { code: string } }>(context, A, 'GET', '/staff/commissions/report');
    expect([refused.status, refused.data.error?.code]).toEqual([403, 'permission_denied']);
  } finally {
    await context.close();
  }
});
