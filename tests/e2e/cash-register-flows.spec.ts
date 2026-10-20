// Every flow of Cash register with a screen, in Chrome and in three sizes (apps/cash_register/WORKBOOK.md,
// CASH_REGISTER-F01 to F17), against the real apps it reads: Sales (charges, voids, refunds, open checks),
// Kitchen (tickets not served) and Printing (its queue and its receipt printer). Each test sets up what it
// needs through the apps' own APIs (setup, never the check), looks at the screen, and takes its screenshots
// `APP-CASH_REGISTER-<flow>-{390,834,1440}`. What this file creates is deleted after it: its sessions and
// their lines and counts, its sales and checks, its kitchen tickets, its print jobs and printer, its product;
// the settings it changes go back as they were.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shot, shown } from './helpers';
import { createProduct, dialog, fill, type Product } from './inventory-helpers';
import { cleanDocumentsOf, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-CRF-${RUN}`;
const LABEL = `e2e crf ${RUN}`;
let shirt: Product;
let methods: Record<string, string>;
/** The sessions this file opened: the only ones its cleanup deletes. */
const mine = new Set<string>();
/** The printers this file made. */
const printers = new Set<string>();

/** The three sizes of every flow's screenshots (390×844, 834×1112, 1440×900). */
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** `APP-CASH_REGISTER-<flow>-<size>` in the three sizes, each once `ready` says it painted. */
async function flowShots(page: Page, flow: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready(page);
    // A new size relays the shell out (menu, tabs): one page header on screen once it settled, never a
    // second copy of the page under the first (hub#1987 saw one on Android).
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            [...document.querySelectorAll('ion-header')].filter((header) => {
              const box = header.getBoundingClientRect();
              const inside = box.bottom > 0 && box.top < window.innerHeight && box.right > 0 && box.left < window.innerWidth;
              return !header.closest('ion-modal, ion-menu') && box.height > 0 && inside;
            }).length,
        ),
      )
      .toBe(1);
    await page.screenshot({ path: shot(`APP-CASH_REGISTER-${flow}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

interface Current {
  required: boolean;
  session: { id: string; number: string; expected_balance: number | null } | null;
  unassigned_count: number;
}
interface Detail {
  id: string;
  number: string;
  status: string;
  auto_closed: boolean;
  expected_balance: number | null;
  summary: { expected_cash: number | null };
}

const settingsBefore: Record<string, unknown> = {};

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/cash_register/sessions');
  shirt = await createProduct(context, { name: `E2E Shirt ${RUN}`, sku: SKU, price: 1210, tax_category_key: 'product.generic' });
  const list = await api<{ rows: { id: string; type: string }[] }>(context, A, 'GET', '/sale/payment_methods');
  methods = Object.fromEntries(list.data.rows.map((row) => [row.type, row.id]));
  const settings = await api<Record<string, unknown>>(context, A, 'GET', '/cash_register/settings');
  for (const key of ['enable_cash_register', 'require_blind_count', 'auto_close_enabled', 'auto_close_time']) settingsBefore[key] = settings.data[key];
  await closeLeftOpen(context);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/cash_register/sessions');
  await api(context, A, 'POST', '/cash_register/settings', settingsBefore);
  await context.close();
  const ids = [...mine].map((id) => `'${id}'`).join(',');
  if (ids) {
    psql(`delete from printing_printjob where source_app = 'cash_register' and reference in (select number from cash_register_session where id in (${ids}))`);
    psql(`delete from cash_register_count where session_id in (${ids})`);
    psql(`delete from cash_register_movement where session_id in (${ids})`);
    psql(`delete from cash_register_session where id in (${ids})`);
  }
  psql(`delete from printing_printjob where reference like '${LABEL}%'`);
  const made = [...printers].map((id) => `'${id}'`).join(',');
  if (made) {
    psql(`update printing_settings set receipt_printer_id = null where receipt_printer_id in (${made})`);
    psql(`delete from printing_printjob where printer_id in (${made})`);
    psql(`delete from printing_printer where id in (${made})`);
  }
  psql(`delete from kitchen_logentry where ticket_id in (select id from kitchen_ticket where label like '${LABEL}%')`);
  psql(`delete from kitchen_ticketitem where ticket_id in (select id from kitchen_ticket where label like '${LABEL}%')`);
  psql(`delete from kitchen_ticket where label like '${LABEL}%'`);
  cleanSalesAndProduct();
});

/** Deletes this run's sales (they sold its SKU), its checks (by their title) and its product. The fiscal
 *  documents Invoicing issued for those sales go first, with Invoicing's own cleanup. */
function cleanSalesAndProduct(): void {
  // Every column named `id`: a bare `id` in a subquery would bind to the outer table's own (and match all).
  const orders = `select distinct order_id as id from sale_orderline where sku = '${SKU}' union select id from sale_order where label like '${LABEL}%'`;
  cleanDocumentsOf(orders);
  psql(
    [
      `create temp table crf_sales as select distinct sale_id as id from sale_saleline where sku = '${SKU}'`,
      `create temp table crf_orders as ${orders}`,
      'delete from sale_refundline where refund_id in (select id from sale_refund where sale_id in (select id from crf_sales))',
      'delete from sale_refundpayment where refund_id in (select id from sale_refund where sale_id in (select id from crf_sales))',
      'delete from sale_refund where sale_id in (select id from crf_sales)',
      'delete from sale_orderline where order_id in (select id from crf_orders) or sale_id in (select id from crf_sales)',
      'delete from sale_salepayment where sale_id in (select id from crf_sales)',
      'delete from sale_saleline where sale_id in (select id from crf_sales)',
      'delete from sale_sale where id in (select id from crf_sales)',
      'delete from sale_order where id in (select id from crf_orders)',
      `delete from inventory_stockmovement where product_id in (select id from inventory_product where sku = '${SKU}')`,
      `delete from inventory_productcategory where product_id in (select id from inventory_product where sku = '${SKU}')`,
      `delete from inventory_product where sku = '${SKU}'`,
    ].join('; '),
  );
}

// ── Setup through the apps' APIs ─────────────────────────────────────────────────────────────────

async function current(context: BrowserContext): Promise<Current> {
  return (await api<Current>(context, A, 'GET', '/cash_register/sessions/current')).data;
}

async function detailOf(context: BrowserContext, id: string): Promise<Detail> {
  return (await api<Detail>(context, A, 'GET', `/cash_register/sessions/detail?session_id=${id}`)).data;
}

/** One drawer open per business: a shift an earlier run left open is closed, at its expected. */
async function closeLeftOpen(context: BrowserContext): Promise<void> {
  const left = (await current(context)).session;
  if (left) await closeByApi(context, left.id, Math.max(left.expected_balance ?? 0, 0));
}

async function openByApi(context: BrowserContext, float: number): Promise<string> {
  const opened = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: float });
  expect(opened.status, JSON.stringify(opened.data)).toBe(201);
  mine.add(opened.data.id);
  return opened.data.id;
}

async function closeByApi(context: BrowserContext, id: string, counted: number): Promise<void> {
  const closed = await api(context, A, 'POST', '/cash_register/sessions/close', { session_id: id, closing_balance: counted, closing_notes: 'e2e' });
  expect(closed.status, JSON.stringify(closed.data)).toBe(200);
}

/** A shirt charged through Sales, in `method` (cash by default). */
async function charge(context: BrowserContext, method = 'cash'): Promise<{ id: string; number: string; payments: { id: string }[] }> {
  const res = await api<{ id: string; number: string; payments: { id: string }[] }>(context, A, 'POST', '/sale/sales', {
    idempotency_key: `e2e-crf-${stamp()}`,
    lines: [{ product: shirt.sku, quantity: '1' }],
    payments: [{ method }],
  });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data;
}

async function settings(context: BrowserContext, values: Record<string, unknown>): Promise<void> {
  const saved = await api(context, A, 'POST', '/cash_register/settings', values);
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
}

// ── The screen ───────────────────────────────────────────────────────────────────────────────────

async function sessionsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=cash-register-sessions-row], [data-testid=cash-register-sessions-empty]').first().waitFor({ state: 'visible' });
}

const rowOf = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${id}"]`);

async function detailReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=cash-register-summary]').waitFor({ state: 'visible' });
}

// ── The flows ────────────────────────────────────────────────────────────────────────────────────

test('CASH_REGISTER-F01, F02: the settings and the drawers, in three sizes', async ({ page }) => {
  await login(page, A, '/cash_register/settings');
  const ready = async (p: Page) => {
    await shown(p).locator('[data-testid=cash-register-settings-heading]').waitFor({ state: 'visible' });
  };
  await ready(page);
  await expect(shown(page).locator('ion-toggle')).toHaveCount(6);
  await flowShots(page, 'CASH_REGISTER-F01', ready);
  await shown(page).locator('[data-testid=cash-register-registers-heading]').scrollIntoViewIfNeeded();
  await shown(page).locator('[data-testid=cash-register-registers-add]').click();
  const modal = dialog(page, 'cash-register-register');
  await expect(modal).toBeVisible();
  await flowShots(page, 'CASH_REGISTER-F02', async () => {
    await expect(modal.locator('[data-testid=cash-register-register-name]')).toBeVisible();
  });
  await modal.locator('[data-testid=cash-register-register-cancel]').click();
  await expect(modal).toBeHidden();
});

test('CASH_REGISTER-F03, F13, F05, F06, F09: the windows of a shift, in three sizes', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  await sessionsReady(page);

  // F03: «Open session», with a finger-sized button (cash_register#12).
  const openButton = shown(page).locator('[data-testid=cash-register-new-session]');
  expect((await openButton.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await openButton.click();
  const open = dialog(page, 'cash-register-open');
  await expect(open).toBeVisible();
  await fill(open, 'cash-register-open-balance', '50,00');
  await flowShots(page, 'CASH_REGISTER-F03', async () => {
    await expect(open.locator('[data-testid=cash-register-open-submit]')).toBeVisible();
  });
  expect((await open.locator('[data-testid=cash-register-open-submit]').boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await open.locator('[data-testid=cash-register-open-submit]').click();
  await expect(open).toBeHidden();
  const session = (await current(context)).session!;
  mine.add(session.id);

  // F13: a cash charge of Sales is in the shift at once, for what it covered.
  await charge(context);
  await expect(rowOf(page, session.id)).toContainText(/62[.,]10/);
  await flowShots(page, 'CASH_REGISTER-F13', sessionsReady);

  // F05: the movement window.
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${session.id}-movement]`).first().click();
  const movement = dialog(page, 'cash-register-movement');
  await expect(movement).toBeVisible();
  await flowShots(page, 'CASH_REGISTER-F05', async () => {
    await expect(movement.locator('[data-testid=cash-register-movement-submit]')).toBeVisible();
  });
  await movement.locator('[data-testid=cash-register-movement-cancel]').click();
  await expect(movement).toBeHidden();

  // F06: the count by notes and coins (cash_register#114: no face value cut on the phone).
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${session.id}-count]`).first().click();
  const count = dialog(page, 'cash-register-count');
  await expect(count).toBeVisible();
  await fill(count, 'cash-register-count-denom-50', '1');
  await fill(count, 'cash-register-count-denom-10', '1');
  await expect(count.locator('[data-testid=cash-register-count-total]')).toContainText(/60[.,]00/);
  await flowShots(page, 'CASH_REGISTER-F06', async () => {
    await expect(count.locator('[data-testid=cash-register-count-total]')).toBeVisible();
  });
  await count.locator('[data-testid=cash-register-count-cancel]').click();
  await expect(count).toBeHidden();

  // F09: the close, with the expected and the difference while typing (cash_register#83, #90).
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${session.id}-close]`).first().click();
  const close = dialog(page, 'cash-register-close');
  await expect(close).toBeVisible();
  await fill(close, 'cash-register-close-counted', '62');
  await expect(close.locator('[data-testid=cash-register-close-expected]')).toContainText(/62[.,]10/);
  await expect(close.locator('[data-testid=cash-register-close-submit]')).toBeVisible();
  await flowShots(page, 'CASH_REGISTER-F09', async () => {
    await expect(close.locator('[data-testid=cash-register-close-submit]')).toBeVisible();
  });
  const submit = close.locator('[data-testid=cash-register-close-submit]');
  await submit.click();
  if ((await close.isVisible()) && (await close.locator('[data-testid=cash-register-review-confirm]').count())) await submit.click();
  await expect(close).toBeHidden();
  const closed = await detailOf(context, session.id);
  expect([closed.status, closed.expected_balance]).toEqual(['closed', 6210]);
});

test('CASH_REGISTER-F04: with the drawer on and no session, the till refuses cash', async ({ page, context }) => {
  await login(page, A, '/sale/pos');
  await closeLeftOpen(context);
  await settings(context, { enable_cash_register: true });
  await page.reload();
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(shirt.sku);
  await search.locator(`[data-testid=pos-search-${shirt.id}]`).click();
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await sheet.locator(`[data-testid=sale-checkout-method-${methods.cash}]`).click();
  for (const key of ['2', '0']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  const refusal = sheet.locator('[data-testid=sale-checkout-error]');
  await expect(refusal).toHaveText(/The cash register is closed|La caja está cerrada/);
  await flowShots(page, 'CASH_REGISTER-F04', async () => {
    await expect(refusal).toBeVisible();
  });
});

test('CASH_REGISTER-F07: a blind count hides the expected cash from the employee, not from the owner', async ({ page, context, browser }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const id = await openByApi(context, 10000);
  await charge(context);
  await settings(context, { require_blind_count: true });
  try {
    const cashier = await browser.newContext({ baseURL: A });
    const employee = await cashier.newPage();
    await login(employee, A, '/cash_register/sessions', EMPLOYEE);
    await sessionsReady(employee);
    const row = rowOf(employee, id);
    await expect(row).toContainText(/100[.,]00/);
    await expect(row).not.toContainText(/112[.,]10/);
    await row.click();
    await detailReady(employee);
    await expect(shown(employee).locator('[data-testid=cash-register-summary-expected]')).toContainText('—');
    await expect(shown(employee).locator('[data-testid=cash-register-session-movements-row]')).toHaveCount(0);
    await expect(shown(employee).locator('[data-testid=cash-register-detail-print]')).toHaveCount(0);
    await flowShots(employee, 'CASH_REGISTER-F07', detailReady);
    await cashier.close();
    // The owner sees it all.
    await page.goto(`${A}/cash_register/sessions/${id}`);
    await detailReady(page);
    await expect(shown(page).locator('[data-testid=cash-register-summary-expected]')).toContainText(/112[.,]10/);
  } finally {
    await settings(context, { require_blind_count: false });
    await closeByApi(context, id, 11210);
  }
});

test('CASH_REGISTER-F08: the close warns of an open check, a kitchen ticket and a print not out', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const id = await openByApi(context, 10000);
  const check = await api(context, A, 'POST', '/sale/orders', { label: `${LABEL} check` });
  expect(check.status, JSON.stringify(check.data)).toBe(201);
  const ticket = await api(context, A, 'POST', '/kitchen/tickets', { label: `${LABEL} T9`, items: [{ name: 'e2e soup' }] });
  expect(ticket.status, JSON.stringify(ticket.data)).toBe(201);
  const job = await api(context, A, 'POST', '/printing/jobs', {
    document_type: 'generic',
    document: { title: `${LABEL} note` },
    source_ref: `${LABEL} job`,
  });
  expect(job.status, JSON.stringify(job.data)).toBe(201);

  await page.reload();
  await sessionsReady(page);
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${id}-close]`).first().click();
  const close = dialog(page, 'cash-register-close');
  await expect(close).toBeVisible();
  const review = close.locator('[data-testid=cash-register-review]');
  await expect(review.locator('[data-testid=cash-register-review-checks]')).toContainText(`${LABEL} check`);
  await expect(review.locator('[data-testid=cash-register-review-kitchen]')).toContainText(`${LABEL} T9`);
  await expect(review.locator('[data-testid=cash-register-review-prints]')).toContainText(/Receipts|Recibos/);
  await fill(close, 'cash-register-close-counted', '100');
  const submit = close.locator('[data-testid=cash-register-close-submit]');
  await submit.click();
  await expect(close.locator('[data-testid=cash-register-review-confirm]')).toBeVisible();
  await expect(submit).toHaveText(/Close anyway|Cerrar de todos modos/);
  await flowShots(page, 'CASH_REGISTER-F08', async () => {
    await expect(close.locator('[data-testid=cash-register-review-confirm]')).toBeVisible();
  });
  await submit.click();
  await expect(close).toBeHidden();
  expect((await detailOf(context, id)).status).toBe('closed');
});

test('CASH_REGISTER-F10: a session forgotten past its cut-off says so and closes when the next one opens', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const id = await openByApi(context, 10000);
  psql(`update cash_register_session set opened_at = now() - interval '2 days' where id = '${id}'`);
  await settings(context, { auto_close_enabled: true, auto_close_time: '04:00' });
  try {
    await page.reload();
    await sessionsReady(page);
    const due = shown(page).locator('[data-testid=cash-register-auto-close-due]');
    await expect(due).toBeVisible();
    await expect(shown(page).locator(`[data-testid=cash-register-sessions-row-${id}-movement]`)).toHaveCount(0);
    await flowShots(page, 'CASH_REGISTER-F10', async (p) => {
      await expect(shown(p).locator('[data-testid=cash-register-auto-close-due]')).toBeVisible();
    });
    // Opening the next one closes the forgotten one first, by itself.
    await shown(page).locator('[data-testid=cash-register-new-session]').click();
    const open = dialog(page, 'cash-register-open');
    await fill(open, 'cash-register-open-balance', '100');
    await open.locator('[data-testid=cash-register-open-submit]').click();
    await expect(open).toBeHidden();
    const forgotten = await detailOf(context, id);
    expect([forgotten.status, forgotten.auto_closed]).toEqual(['closed', true]);
    const next = (await current(context)).session!;
    mine.add(next.id);
    await closeByApi(context, next.id, 10000);
  } finally {
    await settings(context, { auto_close_enabled: false });
  }
});

test('CASH_REGISTER-F11, F14, F15: the detail names a void and a refund, and the drawer follows the cash', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const id = await openByApi(context, 5000);
  const voided = await charge(context);
  const voiding = await api(context, A, 'POST', '/sale/sales/void', { sale_id: voided.id, reason: 'e2e wrong ticket' });
  expect(voiding.status, JSON.stringify(voiding.data)).toBe(200);
  const byCard = await charge(context, 'card');
  const refunding = await api(context, A, 'POST', '/sale/sales/refund', {
    sale_id: byCard.id,
    reason: 'e2e returned',
    allocations: [{ payment_id: byCard.payments[0].id, amount: 500, to_method_id: methods.cash }],
  });
  expect(refunding.status, JSON.stringify(refunding.data)).toBe(200);

  await page.goto(`${A}/cash_register/sessions/${id}`);
  await detailReady(page);
  await expect(shown(page).locator('[data-testid=cash-register-summary-expected]')).toContainText(/45[.,]00/);
  const lines = shown(page).locator('[data-testid=cash-register-session-movements-row]');
  await expect(lines).toHaveCount(4);
  await expect(lines.filter({ hasText: /Void|Anulación/ })).toContainText(voided.number);
  await expect(lines.filter({ hasText: /Refund|Devolución/ })).toContainText(byCard.number);
  await flowShots(page, 'CASH_REGISTER-F11', detailReady);
  for (const flow of ['CASH_REGISTER-F14', 'CASH_REGISTER-F15']) {
    await flowShots(page, flow, async () => {
      // A new size repaints the list (table or cards): scroll to it once it settled.
      await expect(async () => {
        await lines.first().scrollIntoViewIfNeeded({ timeout: 2000 });
        await expect(lines.first()).toBeInViewport();
      }).toPass();
    });
  }
  await closeByApi(context, id, 4500);
});

test('CASH_REGISTER-F12: the drawer’s figures above the sessions, short in red and over in green', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const short = await openByApi(context, 1000);
  await closeByApi(context, short, 960);
  const over = await openByApi(context, 1000);
  await closeByApi(context, over, 1500);
  const open = await openByApi(context, 18405);
  await page.reload();
  await sessionsReady(page);
  const figures = shown(page).locator('[data-testid=cash-register-figures]');
  await expect(figures.locator('[data-testid=cash-register-figures-expected]')).toHaveText(/184[.,]05/);
  const rows = figures.locator('[data-testid=cash-register-figures-recent-row]');
  await expect(rows.first()).toContainText(/\+.?5[.,]00|5[.,]00/);
  await expect(rows.nth(1)).toContainText(/-.?0[.,]40/);
  await expect(rows.nth(1).locator('[data-testid=cash-register-figures-bar]')).toHaveClass(/is-short/);
  await expect(rows.first().locator('[data-testid=cash-register-figures-bar]')).toHaveClass(/is-over/);
  await flowShots(page, 'CASH_REGISTER-F12', async (p) => {
    await expect(shown(p).locator('[data-testid=cash-register-figures]')).toBeVisible();
  });
  // On a tablet the amount stays on one line and the card titles are whole (outfitkit#246, #248).
  await page.setViewportSize({ width: 834, height: 1112 });
  const amount = figures.locator('[data-testid=cash-register-figures-expected]');
  // One line is about 1.2–1.5 times the font size; two lines pass twice it.
  const oneLine = async (locator: Locator) => {
    const size = await locator.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect((await locator.boundingBox())!.height).toBeLessThan(size * 2);
  };
  await oneLine(amount);
  await oneLine(figures.locator('[data-testid=cash-register-figures-number]'));
  for (const title of await figures.locator('.cash-figures__title').all()) {
    expect(await title.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  // CASH_REGISTER-F11: on a desk the list says when each session opened in full, time included.
  const cells = rowOf(page, open).locator('[role=cell] > span');
  await expect(cells.first()).toBeVisible();
  for (const cell of await cells.all()) {
    expect(await cell.evaluate((el) => [el.textContent, el.scrollWidth <= el.clientWidth])).toEqual([await cell.textContent(), true]);
  }
  await closeByApi(context, open, 18405);
});

test('CASH_REGISTER-F16: «Print» sends the Z report to the receipt printer; without one, the browser prints it', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const id = await openByApi(context, 10000);
  await charge(context);
  await closeByApi(context, id, 11200);
  const printer = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: `${LABEL} till`,
    kind: 'network',
    address: '192.0.2.10',
    usage: 'receipt',
  });
  expect(printer.status, JSON.stringify(printer.data)).toBe(201);
  printers.add(printer.data.id);
  const { number } = await detailOf(context, id);

  await page.goto(`${A}/cash_register/sessions/${id}`);
  await detailReady(page);
  await shown(page).locator('[data-testid=cash-register-detail-print]').click();
  await expect(page.locator('ion-toast').filter({ hasText: /Report sent to the|Informe enviado a la/ }).first()).toBeVisible();
  const jobs = await api<{ rows: { document_type: string; reference: string; usage: string }[] }>(context, A, 'GET', '/printing/jobs?limit=50');
  expect(jobs.data.rows.filter((job) => job.reference === number).map((job) => [job.document_type, job.usage])).toEqual([['cash_session_report', 'receipt']]);
  await flowShots(page, 'CASH_REGISTER-F16', detailReady);

  // Without an active receipt printer the paper would wait for ever: the browser's dialog prints it.
  const off = await api(context, A, 'POST', '/printing/printers/update', { printer: printer.data.id, is_active: false });
  expect(off.status, JSON.stringify(off.data)).toBe(200);
  await page.evaluate(() => {
    (window as unknown as { printed: string[] }).printed = [];
    window.print = () => {
      const root = document.querySelector('body > .cash-register-print-root');
      (window as unknown as { printed: string[] }).printed.push(root?.textContent ?? '');
    };
  });
  await shown(page).locator('[data-testid=cash-register-detail-print]').click();
  await expect.poll(() => page.evaluate(() => (window as unknown as { printed: string[] }).printed.length)).toBe(1);
  const printed = await page.evaluate(() => (window as unknown as { printed: string[] }).printed[0]);
  expect(printed).toMatch(/Cash closing \(Z\)|Cierre de caja \(Z\)/);
});

test('CASH_REGISTER-F17: cash charged with the drawer closed is said, with its list', async ({ page, context }) => {
  await login(page, A, '/cash_register/sessions');
  await closeLeftOpen(context);
  const id = await openByApi(context, 1000);
  await closeByApi(context, id, 1000);
  await settings(context, { enable_cash_register: false });
  let sale;
  try {
    sale = await charge(context);
  } finally {
    await settings(context, { enable_cash_register: true });
  }
  expect((await current(context)).unassigned_count).toBeGreaterThanOrEqual(1);
  await page.reload();
  await sessionsReady(page);
  // The notice, not its window (they share the name).
  const notice = shown(page).locator('div[data-testid=cash-register-unassigned]');
  await expect(notice).toBeVisible();
  await notice.locator('[data-testid=cash-register-unassigned-view]').click();
  const list = dialog(page, 'cash-register-unassigned');
  await expect(list).toBeVisible();
  await expect(list).toContainText(sale.number);
  await flowShots(page, 'CASH_REGISTER-F17', async () => {
    await expect(list).toContainText(sale.number);
  });
});
