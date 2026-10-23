// flow: CART_CHECKOUT-F12 — FIX-HUB-CART-CHECKOUT-ORDERS-FILTERS-BEHIND-FUNNEL (seen by the reviewer of
// FIX-UI-DATATABLE-RANGE-FILTER-LABELS): in the old hub Cart & Checkout › Orders and › Carts kept their column
// filters behind the toolbar's funnel, with no open row (docs/reference/old-hub/cart_checkout-{orders,carts}-
// {390,834,1440}.png), as Invoices and Sales already do here (hub#31). The new one painted the row open under the
// toolbar (Order, Email, Status, Payment, Total from / to). Now, at 390, 834 and 1440, both lists open with no row;
// the funnel opens the panel with the columns, «Apply» filters by Status and by Total, and a Total it cannot read
// says «Type an amount, like 12.50» («Escribe un importe, como 12,50») under its box and filters nothing.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, record, shot, shown, untilStill } from './helpers';
import { cleanUp, code, listShown, type Order, orderFrom, post, rowOf, signedIn, VIEWPORTS } from './cart-checkout-helpers';
import { pick } from './inventory-helpers';

const KEY = 'FIX-HUB-CART-CHECKOUT-ORDERS-FILTERS-BEHIND-FUNNEL';
const ORDERS = 'cart-checkout-orders';
const CARTS = 'cart-checkout-carts';
const ORDER_FILTERS = ['order_number', 'customer_email', 'status', 'payment_method', 'total_amount_from', 'total_amount_to'];
const CART_FILTERS = ['session_token', 'customer_email', 'status', 'total_items_from', 'total_items_to', 'total_amount_from', 'total_amount_to'];
const SIZES = [
  { label: '390', viewport: VIEWPORTS.phone },
  { label: '834', viewport: VIEWPORTS.tablet },
  { label: '1440', viewport: VIEWPORTS.desktop },
] as const;

test.beforeEach(cleanUp);
test.afterAll(cleanUp);

const hook = (page: Page, table: string, suffix: string) => shown(page).locator(`[data-testid=${table}-${suffix}]`);

/** The list opened with its filters folded (no row under the toolbar, the funnel in it); opens the panel. */
async function openFunnel(page: Page, table: string, names: string[]): Promise<Locator> {
  await expect(hook(page, table, 'filters'), `${table}: no open row of filters under the toolbar`).toHaveCount(0);
  const funnel = hook(page, table, 'filters-toggle');
  await expect(funnel).toBeVisible();
  const panel = hook(page, table, 'filters-panel');
  if (!(await panel.isVisible())) await funnel.click();
  await expect(panel).toBeVisible();
  // It slides in on a phone (0.18 s): used once it stands still.
  await untilStill(page);
  for (const name of names) await expect(panel.locator(`[data-testid=${table}-filter-${name}]`), `${table}: ${name} in the panel`).toBeVisible();
  return panel;
}

async function apply(page: Page, table: string): Promise<void> {
  await hook(page, table, 'filters-apply').click();
  await expect(hook(page, table, 'filters-panel'), '«Apply» closes the panel and shows the result').toBeHidden();
}

/** Two orders of this run through the API (the assistant's path): 25,00 € initiated and 1.234,56 € paid. */
async function seedOrders(context: BrowserContext, width: string): Promise<{ small: Order; big: Order }> {
  const small = await orderFrom(context, code(`funnel-small-${width}`), { unitPrice: 1250, quantity: '2', email: 'ana@example.com' });
  const big = await orderFrom(context, code(`funnel-big-${width}`), { unitPrice: 61728, quantity: '2', email: 'bea@example.com' });
  await post(context, '/cart_checkout/orders/mark_paid', { order_id: big.id });
  return { small, big };
}

for (const size of SIZES) {
  test(`CART_CHECKOUT-F12 at ${size.label}: Orders and Carts keep their column filters behind the funnel, as the old ones`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/cart_checkout/orders', size.viewport);
    try {
      const { small, big } = await seedOrders(context, size.label);

      await test.step('Orders opens with no row of filters and the funnel opens its panel', async () => {
        await page.goto('/cart_checkout/orders');
        await listShown(page, ORDERS);
        await expect(rowOf(page, ORDERS, small.id)).toBeVisible();
        await expect(rowOf(page, ORDERS, big.id)).toBeVisible();
        await expect(hook(page, ORDERS, 'filters'), 'no open row of filters under the toolbar').toHaveCount(0);
        await expect(hook(page, ORDERS, 'filters-toggle')).toBeVisible();
        await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
        await openFunnel(page, ORDERS, ORDER_FILTERS);
        await page.screenshot({ path: shot(`${KEY}-${size.label}-panel`) });
      });

      await test.step('by Status: «Paid» leaves the paid order only, and the funnel counts it', async () => {
        const panel = await openFunnel(page, ORDERS, ORDER_FILTERS);
        await pick(page, panel.locator(`[data-testid=${ORDERS}-filter-status]`), /^Paid$/);
        // A draft: nothing filters until «Apply».
        await expect(rowOf(page, ORDERS, small.id)).toBeAttached();
        await apply(page, ORDERS);
        await expect(rowOf(page, ORDERS, big.id)).toBeVisible();
        await expect(rowOf(page, ORDERS, small.id)).toHaveCount(0);
        await expect(hook(page, ORDERS, 'filters-count')).toHaveText('1');
        await expect(hook(page, ORDERS, 'filters'), 'still no row: the filter in use waits behind the funnel').toHaveCount(0);
      });

      await test.step('by Total, as it is pasted: «1.000,00» onwards leaves the big order only', async () => {
        const panel = await openFunnel(page, ORDERS, ORDER_FILTERS);
        await hook(page, ORDERS, 'filters-clear').click();
        await expect(rowOf(page, ORDERS, small.id)).toBeVisible();
        await panel.locator(`[data-testid=${ORDERS}-filter-total_amount_from] input`).fill('1.000,00');
        await apply(page, ORDERS);
        await expect(rowOf(page, ORDERS, big.id)).toBeVisible();
        await expect(rowOf(page, ORDERS, small.id)).toHaveCount(0);
        await expect(hook(page, ORDERS, 'filters-count')).toHaveText('1');
      });

      await test.step('a Total it cannot read is said under its box in the panel and filters nothing', async () => {
        const panel = await openFunnel(page, ORDERS, ORDER_FILTERS);
        await hook(page, ORDERS, 'filters-clear').click();
        // «1.250» is 1.250 € or 1,25 €: never the wrong amount.
        await panel.locator(`[data-testid=${ORDERS}-filter-total_amount_to] input`).fill('1.250');
        await apply(page, ORDERS);
        await expect(rowOf(page, ORDERS, small.id)).toBeVisible();
        await expect(rowOf(page, ORDERS, big.id)).toBeVisible();
        await expect(hook(page, ORDERS, 'filters-toggle')).toHaveAttribute('data-invalid', 'true');
        const again = await openFunnel(page, ORDERS, ORDER_FILTERS);
        await expect(again.getByText('Type an amount, like 12.50')).toBeVisible();
        await page.screenshot({ path: shot(`${KEY}-${size.label}-error`) });
        await hook(page, ORDERS, 'filters-clear').click();
        await expect(again.getByText('Type an amount, like 12.50')).toHaveCount(0);
        await hook(page, ORDERS, 'filters-close').click();
        await expect(again).toBeHidden();
      });

      await test.step('Carts opens with no row either: its panel filters by Status and by Total, and says a bad Total', async () => {
        const spare = await post<{ id: string }>(context, '/cart_checkout/carts', { session_token: code(`funnel-spare-${size.label}`) }, 201);
        await post(context, '/cart_checkout/carts/mark_abandoned', { cart_id: spare.id });
        await page.goto('/cart_checkout/carts');
        await listShown(page, CARTS);
        await expect(rowOf(page, CARTS, big.cart_id)).toBeVisible();
        await expect(hook(page, CARTS, 'filters'), 'no open row of filters under the toolbar').toHaveCount(0);
        await page.screenshot({ path: shot(`${KEY}-${size.label}-carts`) });
        let panel = await openFunnel(page, CARTS, CART_FILTERS);
        await pick(page, panel.locator(`[data-testid=${CARTS}-filter-status]`), /^Abandoned$/);
        await apply(page, CARTS);
        await expect(rowOf(page, CARTS, spare.id)).toBeVisible();
        await expect(rowOf(page, CARTS, big.cart_id)).toHaveCount(0);
        panel = await openFunnel(page, CARTS, CART_FILTERS);
        await hook(page, CARTS, 'filters-clear').click();
        await panel.locator(`[data-testid=${CARTS}-filter-total_amount_from] input`).fill('1.000,00');
        await apply(page, CARTS);
        await expect(rowOf(page, CARTS, big.cart_id)).toBeVisible();
        await expect(rowOf(page, CARTS, small.cart_id)).toHaveCount(0);
        panel = await openFunnel(page, CARTS, CART_FILTERS);
        await hook(page, CARTS, 'filters-clear').click();
        await panel.locator(`[data-testid=${CARTS}-filter-total_amount_from] input`).fill('doce');
        await apply(page, CARTS);
        await expect(rowOf(page, CARTS, small.cart_id)).toBeVisible();
        await expect(hook(page, CARTS, 'filters-toggle')).toHaveAttribute('data-invalid', 'true');
        panel = await openFunnel(page, CARTS, CART_FILTERS);
        await expect(panel.getByText('Type an amount, like 12.50')).toBeVisible();
      });

      await test.step('in Spanish the bad Total says «Escribe un importe, como 12,50» and filters nothing', async () => {
        await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
        await page.goto('/cart_checkout/orders');
        await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
        await listShown(page, ORDERS);
        const panel = await openFunnel(page, ORDERS, ORDER_FILTERS);
        await panel.locator(`[data-testid=${ORDERS}-filter-total_amount_from] input`).fill('doce');
        await apply(page, ORDERS);
        await expect(rowOf(page, ORDERS, small.id)).toBeVisible();
        await expect(rowOf(page, ORDERS, big.id)).toBeVisible();
        const again = await openFunnel(page, ORDERS, ORDER_FILTERS);
        await expect(again.getByText('Escribe un importe, como 12,50')).toBeVisible();
        record(`${KEY}-${size.label}`, { orders: [small.order_number, big.order_number] });
      });
    } finally {
      await context.close();
    }
  });
}
