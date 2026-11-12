// flow: SALE-F28, CUSTOMER-F02, INVOICE-F16, CART_CHECKOUT-F12, the Cash register's sessions list and Inventory's
// products — hub#1196: the amount filter «from / to» of every list reads what is typed the way any amount field of the
// Hub reads it (the platform's `parseMoney`, through `filterCents` and `amountFilterErrors` of base). Before, the same
// text was read with five different rules: «1.000,50» filtered in Customers, Cash register and Carts and was «not an
// amount» in Sales and Invoicing; «1.000» was 1.000 € in Customers and refused elsewhere. Now, in a business in euros,
// at 390, 834 and 1440, in every one of those lists: «1.000» (a thousand euros or one) filters nothing and says both
// readings under its box, with the money field's words, and «1.000,50» filters: the list's live subscription asks for
// 100050 cents, nothing is said.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, saveSessionForTheSweep, shown, turnOffTurnedOn, turnOnMissing, untilStill } from './helpers';
import { signedIn, VIEWPORTS } from './cart-checkout-helpers';

const KEY = 'HUB-1196-AMOUNT-FILTER';
/** Each list with an amount filter: its table's testid, the «from» end of one of its amount ranges, and the list query
 *  that takes it with the name it gives it. */
const LISTS = [
  { app: 'customer', path: '/customer/customers', table: 'customer-list', from: 'spent_from', op: 'customer.customer.list', param: 'spent_min' },
  { app: 'invoice', path: '/invoice/invoices', table: 'invoice-list', from: 'total_amount_from', op: 'invoice.invoice.list', param: 'total_amount_from' },
  { app: 'sale', path: '/sale/sales', table: 'sales-table', from: 'total_min', op: 'sale.sale.list', param: 'total_min' },
  { app: 'cart_checkout', path: '/cart_checkout/carts', table: 'cart-checkout-carts', from: 'total_amount_from', op: 'cart_checkout.cart.list', param: 'total_amount_min' },
  { app: 'cart_checkout', path: '/cart_checkout/orders', table: 'cart-checkout-orders', from: 'total_amount_from', op: 'cart_checkout.order.list', param: 'total_amount_min' },
  { app: 'cash_register', path: '/cash_register/sessions', table: 'cash-register-sessions', from: 'opening_min', op: 'cash_register.session.list', param: 'opening_min' },
  { app: 'inventory', path: '/inventory/products', table: 'inventory-products', from: 'price_min', op: 'inventory.product.list', param: 'price_min' },
] as const;
const SIZES = [
  { label: '390', viewport: VIEWPORTS.phone },
  { label: '834', viewport: VIEWPORTS.tablet },
  { label: '1440', viewport: VIEWPORTS.desktop },
] as const;
/** What the money field says for «1.000» in euros, in English (`MoneyInput`). */
const TWO_READINGS = 'This amount can be read in two ways: «1.000» could be €1,000.00 or €1.00. Write the decimals so there is no doubt.';

const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOnMissing(context, A, [...new Set(LISTS.map((list) => list.app))], turnedOn);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

const hook = (page: Page, table: string, suffix: string): Locator => shown(page).locator(`[data-testid=${table}-${suffix}]`);

/** The params of the table's subscription to `op` (the one with an `offset`: the Cash register's figures read the same
 *  list apart) in the last live stream the tab opened with it (`/api/live?s=`, base64url JSON: `encodeSubscriptions`
 *  of @erplora/ui); `undefined` while none did. */
function lastAsked(streams: string[], op: string): Record<string, unknown> | undefined {
  for (const url of [...streams].reverse()) {
    const list = JSON.parse(Buffer.from(new URL(url).searchParams.get('s') ?? '', 'base64url').toString() || '[]') as { op: string; params?: Record<string, unknown> }[];
    const table = list.find((subscription) => subscription.op === op && subscription.params && 'offset' in subscription.params);
    if (table) return table.params;
  }
  return undefined;
}

/** The table's funnel panel, open and still. */
async function openFunnel(page: Page, table: string): Promise<Locator> {
  const panel = hook(page, table, 'filters-panel');
  if (!(await panel.isVisible())) await hook(page, table, 'filters-toggle').click();
  await expect(panel).toBeVisible();
  await untilStill(page);
  return panel;
}

/** Types `text` in the «from» end (the only filter this spec sets, so it replaces the last one) and applies it. */
async function filterFrom(page: Page, table: string, from: string, text: string): Promise<void> {
  const panel = await openFunnel(page, table);
  await panel.locator(`[data-testid=${table}-filter-${from}] input`).fill(text);
  await hook(page, table, 'filters-apply').click();
  await expect(panel, '«Apply» closes the panel').toBeHidden();
}

for (const size of SIZES) {
  test(`hub#1196 at ${size.label}: «1.000» asks and «1.000,50» filters in every list with an amount filter`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/', size.viewport);
    const streams: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/api/live') streams.push(request.url());
    });
    try {
      await saveSessionForTheSweep(context);
      for (const { path, table, from, op, param } of LISTS) {
        await test.step(`${path}: «1.000» says its two readings and filters nothing`, async () => {
          await page.goto(path);
          await expect(hook(page, table, 'filters-toggle'), `${path}: the list and its funnel`).toBeVisible();
          await filterFrom(page, table, from, '1.000');
          await expect(hook(page, table, 'filters-toggle')).toHaveAttribute('data-invalid', 'true');
          const panel = await openFunnel(page, table);
          await expect(panel.getByText(TWO_READINGS)).toBeVisible();
          expect(lastAsked(streams, op), `${op} is asked for, without a «from»`).toBeDefined();
          expect(lastAsked(streams, op)?.[param]).toBeUndefined();
          await capture(page, `${KEY}-${table}-${size.label}-ambiguous`);
        });
        await test.step(`${path}: «1.000,50» filters, and nothing is said`, async () => {
          await filterFrom(page, table, from, '1.000,50');
          await expect(hook(page, table, 'filters-toggle')).not.toHaveAttribute('data-invalid', 'true');
          await expect(hook(page, table, 'filters-count')).toHaveText('1');
          await expect.poll(() => lastAsked(streams, op)?.[param], `${op} asks from 1.000,50 €`).toBe(100050);
          const panel = await openFunnel(page, table);
          await expect(panel.getByText(TWO_READINGS)).toHaveCount(0);
          await expect(panel.locator(`[data-testid=${table}-filter-${from}] input`)).toHaveValue('1.000,50');
          await capture(page, `${KEY}-${table}-${size.label}-filters`);
          await hook(page, table, 'filters-close').click();
        });
      }
    } finally {
      await context.close();
    }
  });
}
