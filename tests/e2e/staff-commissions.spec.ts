// flow: STAFF-F21 (the day's commission) — Staff → Commissions in Chrome, on the real stack: two
// professionals with their commission, real sales of a real Inventory product charged by card (one line
// done by the other professional, one sale partly refunded), and the owner's «Commissions» tab: what each
// one sold «Today» with the refund taken off whoever sold it, their rate and their commission, the totals,
// a new charge painted live, «Yesterday» and a custom range whose «To» before «From» is said under «To».
// Seen at 390×844, 834×1112 and 1440×900. An
// employee opens Commissions too and sees only her own row: the cut she did on a colleague's sale counts in it, the
// same row the owner sees of her.
// A session of a voucher (SALE-F27) charges nothing and still counts for who did it, at its value (hub#685);
// whoever sold the voucher counts nothing for it (hub#769). One spent outside the checkout saying who did it counts
// for her too, and the screen repaints by itself when another is spent (SERVICE-F21, hub#770).
// Setup goes through the apps' own APIs (Staff, Inventory, Sales); what the run creates is named «E2E…»
// and removed after it (and before, if a run died half-way).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { cleanUp as cleanCustomers, createCard, e2eName } from './customer-helpers';
import { A, api, capture, type Credentials, EMPLOYEE, login, psql, saveSessionForTheSweep, shot, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';
import { cleanUp as cleanServices, named, post } from './service-helpers';

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
  cleanServices();
  cleanCustomers();
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

test('STAFF-F21 (paso 3: la comisión del día): who sold a voucher counts nothing for it; a session counts for who did it, at the voucher\'s price ÷ its sessions', async ({ browser }) => {
  test.setTimeout(180_000);
  const { context, page } = await signedIn(browser, '/staff/commissions');
  try {
    const ana = await member(context, 'Ana', '15');
    const bea = await member(context, 'Bea', '15');
    const cut = await post<{ id: string }>(context, '/service/services', { name: named('Corte'), price: 2500, tax_category_key: 'service.generic' });
    const lucia = await createCard(context, { name: e2eName('Lucía') });
    const voucher = await post<{ id: string }>(context, '/service/packages', { name: named('Bono 3'), max_uses: 3, items: [{ service_id: cut.id }] });
    // Charged at the till at an open price, on Ana, and granted saying that sale.
    const sold = await chargeByApi(context, {
      open_lines: [{ name: 'e2e Bono', unit_price: 10000, tax_category_key: 'service.generic', staff_id: ana.id }],
      payments: CARD,
    });
    const grant = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: lucia.id, amount: 10000, sale_id: sold.id });
    const check = await post<{ id: string; lines: { id: string }[] }>(context, '/sale/orders', {
      label: 'e2e voucher session',
      service_lines: [{ service_id: cut.id, staff_id: bea.id }],
    });
    await post(context, '/sale/orders/apply_voucher', { order_id: check.id, line_id: check.lines[0].id, grant_id: grant.id }, 200);
    const sale = await chargeByApi(context, { order_id: check.id, customer_id: lucia.id });
    expect(sale.total).toBe(0);
    // The server: 100.00 € in 3 sessions, the first 33.33 €, at 15 % = 4.9995 → 5.00 €.
    expect(await reported(context, bea.id)).toMatchObject({ sold: 3333, commission: 500 });
    expect(await reported(context, ana.id)).toMatchObject({ sold: 0, commission: 0 });

    await page.goto(`${A}/staff/commissions`);
    await expect(rowOf(page, bea.id)).toContainText('€33.33');
    await expect(rowOf(page, bea.id)).toContainText('€5.00');
    await expect(rowOf(page, ana.id)).toContainText('€0.00');
  } finally {
    await context.close();
  }
});

test('STAFF-F21 (la fila propia): an employee opens Commissions and sees only her own row, with the cut she did on a colleague\'s sale', async ({ browser }) => {
  test.setTimeout(180_000);
  const employee = await signedIn(browser, '/staff/members', EMPLOYEE);
  const owner = await signedIn(browser, '/staff/members');
  try {
    // Her account (the hub user her sign-in made) linked to a record of Staff; Bea, a colleague, beside her.
    const accounts = await api<{ rows: Array<{ user_id: string; name: string }> }>(owner.context, A, 'GET', '/staff/accounts?search=employee');
    const account = accounts.data.rows.find((row) => row.name.toLowerCase().includes('employee'));
    expect(account, JSON.stringify(accounts.data)).toBeDefined();
    const linked = await api<{ rows: Member[] }>(owner.context, A, 'GET', `/staff/members?user_id=${account!.user_id}`);
    const eva =
      linked.data.rows[0] ??
      (
        await api<Member>(owner.context, A, 'POST', '/staff/members', {
          first_name: `${TAG} Eva`,
          last_name: `Commission${stamp()}`,
          commission_rate: '15',
          user_id: account!.user_id,
        })
      ).data;
    const bea = await member(owner.context, 'Bea', '10');
    const sku = `${SKU}-OWN`;
    await createProduct(owner.context, { name: 'E2E Own cut', sku, price: 1800, tax_category_key: 'product.generic' });
    // The owner charges a sale attributed to Bea whose cut Eva did: Eva cannot open it, and it is still hers.
    await chargeByApi(owner.context, { lines: [{ product: sku, staff_id: eva.id }], staff_id: bea.id, payments: CARD });

    const hers = await api<{ rows: ReportRow[] }>(employee.context, A, 'GET', '/staff/commissions/report');
    expect(hers.status).toBe(200);
    expect(hers.data.rows.map((row) => row.member_id)).toEqual([eva.id]);
    // Positive control: the owner sees Bea too, and of Eva the very row she sees.
    expect(await reported(owner.context, bea.id)).toMatchObject({ sold: 1800, commission: 180 });
    expect(await reported(owner.context, eva.id)).toEqual(hers.data.rows[0]);
    expect(hers.data.rows[0].sold).toBeGreaterThanOrEqual(1800);

    const page = employee.page;
    await page.goto(`${A}/staff/commissions`);
    const view = shown(page);
    await expect(rowOf(page, eva.id)).toBeVisible();
    await expect(view.locator('[data-testid=staff-commissions-row]')).toHaveCount(1);
    await expect(rowOf(page, bea.id)).toHaveCount(0);
    await expect(view.locator('ion-footer ion-segment-button', { hasText: 'Commissions' })).toHaveClass(/segment-button-checked/);
    await expect(view.locator('ion-footer ion-segment-button')).toHaveText(['Staff', 'Time Off', 'Schedules', 'Commissions']);
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      // On a phone the row turns into a card: what was painted is painted again, so it retries.
      await expect(async () => {
        await rowOf(page, eva.id).scrollIntoViewIfNeeded({ timeout: 2000 });
        await expect(rowOf(page, eva.id)).toBeInViewport({ timeout: 1000 });
      }, `Eva at ${viewport.label}`).toPass();
      await expect(view.locator('[data-testid=staff-commissions-row]')).toHaveCount(1);
      await page.screenshot({ path: shot(`staff-commissions-employee-${viewport.label}`) });
    }
  } finally {
    await employee.context.close();
    await owner.context.close();
  }
});

test('STAFF-F21 (paso 3: la comisión del día): a session spent outside the checkout saying who did it counts for her, painted live', async ({ browser }) => {
  // flow: SERVICE-F21, SALE-F28: the reproduction of hub#770 on the screen («Ana» did it, her production goes up).
  test.setTimeout(180_000);
  const { context, page } = await signedIn(browser, '/staff/commissions');
  try {
    const ana = await member(context, 'Ana', '15');
    const cut = await post<{ id: string }>(context, '/service/services', { name: named('Corte'), price: 2500, tax_category_key: 'service.generic' });
    const lucia = await createCard(context, { name: e2eName('Lucía') });
    const voucher = await post<{ id: string }>(context, '/service/packages', { name: named('Bono 3'), max_uses: 3, items: [{ service_id: cut.id }] });
    // Charged at the till at an open price by nobody in particular, and granted saying that sale.
    const sold = await chargeByApi(context, {
      open_lines: [{ name: 'e2e Bono', unit_price: 10000, tax_category_key: 'service.generic' }],
      payments: CARD,
    });
    const grant = await post<{ id: string }>(context, '/service/grants', { package_id: voucher.id, customer_id: lucia.id, amount: 10000, sale_id: sold.id });
    const spent = await post<{ member_id: string; member_name: string; remaining: number }>(
      context,
      '/service/grants/redeem',
      { id: grant.id, service_id: cut.id, member_id: ana.id },
      200,
    );
    expect(spent).toMatchObject({ member_id: ana.id, member_name: ana.full_name, remaining: 2 });
    // The server: 100.00 € in 3 sessions, the first 33.33 €, at 15 % = 4.9995 → 5.00 €.
    expect(await reported(context, ana.id)).toMatchObject({ sold: 3333, commission: 500 });

    await page.goto(`${A}/staff/commissions`);
    await expect(rowOf(page, ana.id)).toContainText('€33.33');
    await expect(rowOf(page, ana.id)).toContainText('€5.00');

    // Another session outside the checkout reaches the screen by itself: 33.33 + 33.34 = 66.67 €, at 15 % = 10.00 €.
    await post(context, '/service/grants/redeem', { id: grant.id, member_id: ana.id }, 200);
    await expect(rowOf(page, ana.id)).toContainText('€66.67');
    await expect(rowOf(page, ana.id)).toContainText('€10.00');
    await saveSessionForTheSweep(context);

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await expect(async () => {
        await rowOf(page, ana.id).scrollIntoViewIfNeeded({ timeout: 2000 });
        await expect(rowOf(page, ana.id)).toBeInViewport({ timeout: 1000 });
      }, `Ana at ${viewport.label}`).toPass();
      await expect(rowOf(page, ana.id)).toContainText('€66.67');
      await capture(page, `HUB-770-COMMISSIONS-OFF-TILL-${viewport.label}`);
    }
  } finally {
    await context.close();
  }
});
