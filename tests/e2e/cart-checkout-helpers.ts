// Shared steps of the cart_checkout e2e (cart-checkout-*.spec.ts): a signed-in page in English, the app's
// API for setup and server-side evidence (never the check itself), a row action (a button, or inside «⋮»
// when the row folds them), the flows' captures and the cleanup every spec runs before and after it: what
// a run creates carries the session prefix «e2e-cc» and is deleted from the hub's database (phase 1: `a`
// and `b` share it), with the day counter of the orders it numbered.
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, api, capture, type Credentials, horizontalOverflow, login, psql, settled, shown } from './helpers';

/** Every session code a cart_checkout spec gives starts like this. */
export const TAG = 'e2e-cc';

/** `e2e-cc-<label>-<base36 time>`: unique per run. */
export const code = (label: string): string => `${TAG}-${label}-${Date.now().toString(36)}`;

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 834, height: 1112 },
  phone: { width: 390, height: 844 },
} as const;

/** The flows' captures, by width: `APP-CART_CHECKOUT-<flow>-<width>.png` in the artifacts. */
export const FLOW_VIEWPORTS = { 390: VIEWPORTS.phone, 834: VIEWPORTS.tablet, 1440: VIEWPORTS.desktop } as const;

/**
 * Captures what the page shows for `flow` at `width` once nothing moves (`settled`: a sheet, a dialog or a toast still
 * sliding in right after it is «visible», in its shadow root), after checking nothing scrolls sideways (`capture`).
 */
export async function snap(page: Page, flow: string, width: number | string): Promise<void> {
  await settled(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${flow} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `APP-CART_CHECKOUT-${flow}-${width}`);
}

export async function signedIn(
  browser: Browser,
  next: string,
  viewport: { width: number; height: number } = VIEWPORTS.desktop,
  credentials?: Credentials,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** POST to the hub's API with the page's session; fails the test on anything but `status`. */
export async function post<T>(context: BrowserContext, path: string, body: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** GET from the hub's API with the page's session; fails the test on anything but 200. */
export async function get<T>(context: BrowserContext, path: string): Promise<T> {
  const res = await api<T>(context, A, 'GET', path);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(200);
  return res.data;
}

/** Waits for a list of the app to have painted its first result: its rows or its empty state. */
export async function listShown(page: Page, table: 'cart-checkout-carts' | 'cart-checkout-orders'): Promise<void> {
  await shown(page).locator(`[data-testid=${table}-empty], [data-testid=${table}-row]`).first().waitFor({ state: 'visible' });
}

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
export async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

/** How many pixels of `text` the row (or card) hides: its own box cuts it («…»), or a box around it
 *  that clips (the cell) is narrower than the text. */
export async function hidden(row: Locator, text: string): Promise<number> {
  return row
    .getByText(text, { exact: true })
    .first()
    .evaluate((box) => {
      const clips = (element: Element) => getComputedStyle(element).overflowX !== 'visible';
      let cut = clips(box) ? box.scrollWidth - box.clientWidth : 0;
      const own = box.getBoundingClientRect();
      for (let up = box.parentElement; up && !up.matches('[data-testid$=-row]'); up = up.parentElement) {
        if (!clips(up)) continue;
        const edge = up.getBoundingClientRect();
        cut = Math.max(cut, own.right - edge.right, edge.left - own.left);
      }
      return Math.round(cut);
    });
}

/** The row (or card) of a table with the record `id`. */
export const rowOf = (page: Page, table: string, id: string) => shown(page).locator(`[data-testid=${table}-row][data-id="${id}"]`).first();

export interface Cart {
  id: string;
  session_token: string;
  status: string;
  total_items: string;
  total_amount: number;
  currency: string;
}

export interface Line {
  id: string;
  quantity: string;
  unit_price: number;
  line_total: number;
}

export interface LineChange {
  item: Line | null;
  removed: boolean;
  cart: Cart;
}

export interface Order {
  id: string;
  cart_id: string;
  order_number: string;
  status: string;
  total_amount: number;
  currency: string;
  customer_email: string;
  shipping_address: Record<string, string>;
  billing_address: Record<string, string>;
}

/** A cart with one line of `quantity` × `unitPrice` and an order started from it, through the API (the
 *  assistant's path: the screens have no form for lines or orders). */
export async function orderFrom(
  context: BrowserContext,
  session: string,
  { unitPrice = 1250, quantity = '2', email = 'ana@example.com' }: { unitPrice?: number; quantity?: string; email?: string } = {},
): Promise<Order> {
  await post(context, '/cart_checkout/carts', { session_token: session, customer_email: email }, 201);
  await post(context, '/cart_checkout/items', { session_token: session, product_ref: 'p-1', product_name: 'Champú', quantity, unit_price: unitPrice }, 201);
  return post<Order>(context, '/cart_checkout/checkout/initiate', { session_token: session }, 201);
}

/** The events the app left in the outbox about `id` (a cart, a line or an order), oldest first. */
export function eventsAbout(id: string): string[] {
  const rows = psql(
    `select name from live_outboxevent where name like 'cart_checkout.%' and (payload->>'id' = '${id}' or payload->>'cart_id' = '${id}' or payload->>'item_id' = '${id}') order by created_at, id`,
  );
  return rows ? rows.split('\n') : [];
}

const CARTS = `select id from cart_checkout_cart where session_token like '${TAG}%'`;

/** Deletes what the specs created; the counter of a day goes too when no order of that day is left. */
export function cleanUp(): void {
  psql(
    [
      `delete from cart_checkout_order where cart_id in (${CARTS})`,
      `delete from cart_checkout_cartitem where cart_id in (${CARTS})`,
      `delete from cart_checkout_cart where session_token like '${TAG}%'`,
      `delete from cart_checkout_ordercounter c where not exists (select 1 from cart_checkout_order o where o.order_number like 'OS-' || to_char(c.day, 'YYYYMMDD') || '-%')`,
    ].join('; '),
  );
}
