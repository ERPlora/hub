// A shift of the drawer in Chrome (CASH_REGISTER-F03, F05, F06, F09, F11, F13, F16; apps/cash_register/
// WORKBOOK.md), crossing the real Sales app: the owner opens the drawer with 100.00 €, charges a 12.10 €
// shirt in cash at the till (Inventory's product at Taxes' 21 %), sees it in the open shift's expected
// cash, takes 2.00 € out for a supplier, counts the drawer by notes and coins (110.00 €) and closes it from
// the count: 10 cents short, frozen. The detail shows the ticket's line, the movement and the count, and
// prints the Z report. Screenshots of the sessions and the detail in the three viewports.
// What this file creates is deleted after it (its sessions, lines and counts, the sale and the product).
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { createProduct, dialog, fill, pick, type Product } from './inventory-helpers';
import { cleanDocumentsOf, newestSaleOf, shots, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-CR-${RUN}`;
let shirt: Product;
/** The sessions this file opened: the only ones its cleanup deletes. */
const mine = new Set<string>();

interface Current {
  session: { id: string; number: string; expected_balance: number | null } | null;
}
interface Session {
  id: string;
  number: string;
  status: string;
  expected_balance: number | null;
  closing_balance: number | null;
  difference: number | null;
  summary: { cash_sales: number | null; total_cash_out: number; expected_cash: number | null };
}

test.afterAll(() => {
  const ids = [...mine].map((id) => `'${id}'`).join(',');
  if (ids) {
    psql(`delete from cash_register_count where session_id in (${ids})`);
    psql(`delete from cash_register_movement where session_id in (${ids})`);
    psql(`delete from cash_register_session where id in (${ids})`);
  }
  cleanSaleAndProduct(SKU);
});

/** Deletes the sales that sold `sku` (with their checks) and the product: only this file's own, whatever
 *  other runs left behind. The fiscal documents Invoicing issued for those sales go first, with its own
 *  cleanup: each one holds its sale (PROTECT). */
function cleanSaleAndProduct(sku: string): void {
  cleanDocumentsOf(`select distinct order_id from sale_orderline where sku = '${sku}'`);
  psql(
    [
      `create temp table cr_sales as select distinct sale_id as id from sale_saleline where sku = '${sku}'`,
      'create temp table cr_orders as select order_id as id from sale_sale where id in (select id from cr_sales) and order_id is not null',
      'delete from sale_refundline where refund_id in (select id from sale_refund where sale_id in (select id from cr_sales))',
      'delete from sale_refundpayment where refund_id in (select id from sale_refund where sale_id in (select id from cr_sales))',
      'delete from sale_refund where sale_id in (select id from cr_sales)',
      'delete from sale_orderline where order_id in (select id from cr_orders)',
      'delete from sale_salepayment where sale_id in (select id from cr_sales)',
      'delete from sale_saleline where sale_id in (select id from cr_sales)',
      'delete from sale_sale where id in (select id from cr_sales)',
      'delete from sale_order where id in (select id from cr_orders)',
      `delete from inventory_stockmovement where product_id in (select id from inventory_product where sku = '${sku}')`,
      `delete from inventory_productcategory where product_id in (select id from inventory_product where sku = '${sku}')`,
      `delete from inventory_product where sku = '${sku}'`,
    ].join('; '),
  );
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/cash_register/sessions');
  shirt = await createProduct(context, { name: `E2E Shirt ${RUN}`, sku: SKU, price: 1210, tax_category_key: 'product.generic' });
  // One drawer open per business: a shift some earlier run left open is closed (at its expected) first.
  const current = await api<Current>(context, A, 'GET', '/cash_register/sessions/current');
  const left = current.data.session;
  if (left) {
    const closed = await api(context, A, 'POST', '/cash_register/sessions/close', {
      session_id: left.id,
      closing_balance: Math.max(left.expected_balance ?? 0, 0),
      closing_notes: 'e2e: left open by an earlier run',
    });
    expect(closed.status).toBe(200);
  }
  await context.close();
});

async function sessionsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=cash-register-sessions-row], [data-testid=cash-register-sessions-empty]').first().waitFor({ state: 'visible' });
}

const rowOf = (page: Page, id: string) => shown(page).locator(`[data-testid=cash-register-sessions-row][data-id="${id}"]`);

async function current(page: Page): Promise<Current> {
  return (await api<Current>(page.context(), A, 'GET', '/cash_register/sessions/current')).data;
}

async function detailOf(page: Page, id: string): Promise<Session> {
  return (await api<Session>(page.context(), A, 'GET', `/cash_register/sessions/detail?session_id=${id}`)).data;
}

/** The till's own charge, in cash, of one shirt (the till is Sales' screen: SALE-F01). */
async function chargeAtTheTill(page: Page): Promise<void> {
  await page.goto(`${A}/sale/pos`);
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(shirt.sku);
  await search.locator(`[data-testid=pos-search-${shirt.id}]`).click();
  await expect(shown(page).locator('[data-testid=pos-total]')).toContainText(/12[.,]10/);
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  for (const key of ['2', '0']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  await expect(page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]')).toBeVisible();
}

test('CASH_REGISTER-F03, F13, F05, F06, F09: a shift from the float to the close, with a cash sale of the till', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/cash_register/sessions');
  await sessionsReady(page);
  await expect(shown(page).locator('[data-testid=cash-register-new-session]')).not.toHaveAttribute('aria-disabled', 'true');

  // F03: open with 100.00 €.
  await shown(page).locator('[data-testid=cash-register-new-session]').click();
  const open = dialog(page, 'cash-register-open');
  await expect(open).toBeVisible();
  await fill(open, 'cash-register-open-balance', '100,00');
  await open.locator('[data-testid=cash-register-open-submit]').click();
  await expect(open).toBeHidden();
  const opened = (await current(page)).session!;
  expect(opened).not.toBeNull();
  mine.add(opened.id);
  await expect(rowOf(page, opened.id)).toContainText(opened.number);
  await expect(shown(page).locator('[data-testid=cash-register-new-session]')).toHaveAttribute('aria-disabled', 'true');

  // F13: a cash sale charged at the till is in the open shift at once.
  await chargeAtTheTill(page);
  const sale = await newestSaleOf(page.context(), shirt.sku);
  expect(sale.payments.map((p) => [p.method_type, p.amount, p.tendered])).toEqual([['cash', 1210, 2000]]);
  await page.goto(`${A}/cash_register/sessions`);
  await sessionsReady(page);
  await expect(rowOf(page, opened.id)).toContainText(/112[.,]10/);

  // F05: 2.00 € out for a supplier.
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${opened.id}-movement]`).first().click();
  const movement = dialog(page, 'cash-register-movement');
  await expect(movement).toBeVisible();
  await pick(page, movement.locator('[data-testid=cash-register-movement-type]'), /Cash out|Salida/);
  await fill(movement, 'cash-register-movement-amount', '2');
  await fill(movement, 'cash-register-movement-concept', `e2e supplier ${RUN}`);
  await movement.locator('[data-testid=cash-register-movement-submit]').click();
  await expect(movement).toBeHidden();
  await expect(rowOf(page, opened.id)).toContainText(/110[.,]10/);
  await shots(page, 'cash-register-sessions', sessionsReady);

  // F06 → F09: a closing count of 110.00 € leads to the close, which starts from it: 10 cents short.
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${opened.id}-count]`).first().click();
  const count = dialog(page, 'cash-register-count');
  await expect(count).toBeVisible();
  await fill(count, 'cash-register-count-denom-100', '1');
  await fill(count, 'cash-register-count-denom-10', '1');
  await expect(count.locator('[data-testid=cash-register-count-total]')).toContainText(/110[.,]00/);
  await page.screenshot({ path: shot('cash-register-count-1440') });
  await count.locator('[data-testid=cash-register-count-submit]').click();
  await expect(count).toBeHidden();

  const close = dialog(page, 'cash-register-close');
  await expect(close).toBeVisible();
  await expect(close.locator('[data-testid=cash-register-close-counted] input')).toHaveValue(/110[.,]00/);
  await expect(close.locator('[data-testid=cash-register-close-expected]')).toContainText(/110[.,]10/);
  await expect(close.locator('[data-testid=cash-register-close-expected]')).toContainText(/-\s?0[.,]10|-€0\.10/);
  await page.screenshot({ path: shot('cash-register-close-1440') });
  const submit = close.locator('[data-testid=cash-register-close-submit]');
  await submit.click();
  // Another session's open checks may be on the hub: then the first press warns and the second closes.
  if (await close.isVisible() && (await close.locator('[data-testid=cash-register-review-confirm]').count())) await submit.click();
  await expect(close).toBeHidden();

  const closed = await detailOf(page, opened.id);
  expect([closed.status, closed.expected_balance, closed.closing_balance, closed.difference]).toEqual(['closed', 11010, 11000, -10]);
  expect([closed.summary.cash_sales, closed.summary.total_cash_out]).toEqual([1210, 200]);
  await expect(rowOf(page, opened.id)).toContainText(/Closed|Cerrada/);
  await expect(shown(page).locator('[data-testid=cash-register-new-session]')).not.toHaveAttribute('aria-disabled', 'true');
});

test('CASH_REGISTER-F11, F16: the detail of the closed shift names the ticket and prints the Z report', async ({ page }) => {
  const [id] = [...mine];
  test.skip(!id, 'the shift of the first test did not open');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/cash_register/sessions');
  await sessionsReady(page);
  await rowOf(page, id).click();
  await expect(page).toHaveURL(new RegExp(`/cash_register/sessions/${id}$`));
  const detail = shown(page);
  await expect(detail.locator('[data-testid=cash-register-detail-title]')).toBeVisible();
  await expect(detail.locator('[data-testid=cash-register-summary-cashSales]')).toContainText(/12[.,]10/);
  await expect(detail.locator('[data-testid=cash-register-summary-difference]')).toContainText(/-\s?0[.,]10|-€0\.10/);
  const lines = detail.locator('[data-testid=cash-register-session-movements-row]');
  await expect(lines).toHaveCount(2);
  const sale = await newestSaleOf(page.context(), shirt.sku);
  await expect(lines.filter({ hasText: sale.number })).toContainText(/Ticket|Tique/);
  await expect(lines.filter({ hasText: `e2e supplier ${RUN}` })).toContainText(/-\s?2[.,]00|-€2\.00/);
  await expect(detail.locator('[data-testid=cash-register-session-counts-row]')).toHaveCount(1);
  await shots(page, 'cash-register-detail', async (p) => {
    await shown(p).locator('[data-testid=cash-register-summary]').waitFor({ state: 'visible' });
  });

  // «Print»: the Z report alone, through the browser's dialog (stubbed: a headless browser has none).
  await page.evaluate(() => {
    (window as unknown as { printed: string[] }).printed = [];
    window.print = () => {
      const root = document.querySelector('body > .cash-register-print-root');
      (window as unknown as { printed: string[] }).printed.push(root?.textContent ?? '');
    };
  });
  await detail.locator('[data-testid=cash-register-detail-print]').click();
  const printed = await page.evaluate(() => (window as unknown as { printed: string[] }).printed);
  expect(printed).toHaveLength(1);
  expect(printed[0]).toMatch(/Cash closing \(Z\)|Cierre de caja \(Z\)/);
});
