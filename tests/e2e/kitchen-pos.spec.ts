// flow: KITCHEN-F18, KITCHEN-F19, KITCHEN-F20 — Kitchen's pieces in the till, in Chrome with the real Sales, Kitchen
// and Inventory apps: «Current order» sends the round urgent with the flame armed and then a normal one (F18); in
// «Check», «Tickets · 2» beside what was sent opens «Order tickets», a card per round with the newest on top, its
// time, its state and «Rush», and it changes by itself while open when the kitchen marks a round ready or the till
// voids a sent dish (struck, «Voided»; KITCHEN-F29) (F19); «Mark rush» there rushes the round that cooks and
// «Remove rush» takes it away, and a ready round offers neither (F20). Each screen in 390×844, 834×1112 and
// 1440×900 (`APP-KITCHEN-<flow>-<size>`). What a run creates — products `E2E-KPOS-<run>-…`, its checks and their
// kitchen tickets — is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, drawerOff, openTillCart, restoreDrawer, stamp } from './sale-helpers';

const RUN = stamp();
const SKU = `E2E-KPOS-${RUN}`;
const FOOD = 'restaurant.food';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

let burger: Product;
let soup: Product;
let bread: Product;

interface Ticket {
  id: string;
  order_id: string;
  round_no: number;
  priority: string;
  status: string;
  items: { id: string; name: string; status: string }[];
}

/** The kitchen tickets of this run's checks (their dishes name the lines of its products), before the sales: a
 *  ticket names the check's lines. */
function cleanRun(): void {
  const lines = "select id from sale_orderline where sku like 'E2E-KPOS-%'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (${lines}) or name like 'E2E KPOS %'`;
  psql(
    [
      `create temp table e2e_kpos_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_kpos_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_kpos_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_kpos_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_kpos_tickets)',
    ].join('; '),
  );
}

function cleanUp(): void {
  cleanRun();
  cleanSales();
  cleanInventory();
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

async function ticket(context: BrowserContext, id: string): Promise<Ticket> {
  const res = await api<Ticket>(context, A, 'GET', `/kitchen/tickets/detail?ticket_id=${id}`);
  expect(res.status).toBe(200);
  return res.data;
}

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator(`[data-testid=pos-product-${burger.id}]`).waitFor({ state: 'visible' });
}

async function still(page: Page): Promise<void> {
  await page.waitForFunction(() => document.getAnimations().every((animation) => animation.playState !== 'running'));
}

const sheet = (page: Page): Locator => page.locator('ion-modal[data-testid=pos-kitchen-tickets]');
const card = (page: Page, round: number): Locator => sheet(page).locator(`[data-testid^=pos-kitchen-ticket-][data-round="${round}"]`);

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/pos');
  await drawerOff(context);
  burger = await createProduct(context, { name: `E2E KPOS Burger ${RUN}`, sku: `${SKU}-BUR`, price: 1200, tax_category_key: FOOD });
  soup = await createProduct(context, { name: `E2E KPOS Soup ${RUN}`, sku: `${SKU}-SOU`, price: 600, tax_category_key: FOOD });
  bread = await createProduct(context, { name: `E2E KPOS Bread ${RUN}`, sku: `${SKU}-BRE`, price: 150, tax_category_key: FOOD });
  await context.close();
});

test.afterAll(() => {
  cleanUp();
  restoreDrawer();
});

test('KITCHEN-F18, F19, F20: the till sends rounds, follows them in «Order tickets» and rushes one', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  const view = shown(page);

  // KITCHEN-F18: the burger, «Current order», the flame armed → «Send RUSH (1)».
  await view.locator(`[data-testid=pos-product-${burger.id}]`).click();
  await view.locator('[data-testid=pos-cart-tab-round]').click();
  const flame = view.locator('[data-testid=pos-kitchen-rush]');
  await flame.click();
  await expect(flame).toHaveAttribute('aria-pressed', 'true');
  await expect(view.locator('[data-testid=pos-kitchen-send]')).toContainText('Send RUSH (1)');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    // On a phone the check is the drawer behind the cart button, opened once the till has laid itself out for the
    // new size: read straight after the resize, at 390 the button was not there yet and the drawer stayed shut.
    await openTillCart(page);
    await expect(view.locator('[data-testid=pos-kitchen-send]')).toBeInViewport({ ratio: 1 });
    if ((await flame.getAttribute('aria-pressed')) !== 'true') await flame.click();
    await expect(view.locator('[data-testid=pos-kitchen-send]')).toContainText('Send RUSH (1)');
    await still(page);
    await page.screenshot({ path: shot(`APP-KITCHEN-KITCHEN-F18-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await view.locator('[data-testid=pos-kitchen-send]').click();
  await expect(page.locator('ion-toast').filter({ hasText: 'Order 1 sent to the kitchen.' })).toBeVisible();
  await expect(view.locator('[data-testid=pos-cart-round-empty]')).toContainText('Everything is sent');

  // A second round, the soup and the bread, normal: the flame went out with the send.
  await view.locator(`[data-testid=pos-product-${soup.id}]`).click();
  await view.locator(`[data-testid=pos-product-${bread.id}]`).click();
  await expect(flame).toHaveAttribute('aria-pressed', 'false');
  await expect(view.locator('[data-testid=pos-kitchen-send]')).toContainText('Send order (2)');
  await view.locator('[data-testid=pos-kitchen-send]').click();
  const sent = page.locator('ion-toast').filter({ hasText: 'Order 2 sent to the kitchen.' });
  await expect(sent).toBeVisible();
  // The notice goes by itself: the screenshots show the sheet, not the toast on top of it.
  await expect(sent).toBeHidden({ timeout: 15_000 });

  // KITCHEN-F19: «Check» → «Tickets · 2» beside what was sent → «Order tickets», the newest round on top.
  await view.locator('[data-testid=pos-cart-tab-check]').click();
  const chip = view.locator('[data-testid=pos-cart-sent] [data-testid=pos-kitchen-tickets-open]');
  await expect(chip).toHaveText('Tickets · 2');
  await chip.click();
  await expect(sheet(page).locator('[data-testid=pos-kitchen-tickets-title]')).toHaveText('Order tickets');
  const rounds = await sheet(page).locator('[data-testid^=pos-kitchen-ticket-][data-round]').evaluateAll((cards) => cards.map((c) => c.getAttribute('data-round')));
  expect(rounds).toEqual(['2', '1']);
  const firstId = (await card(page, 1).getAttribute('data-testid'))!.replace('pos-kitchen-ticket-', '');
  const secondId = (await card(page, 2).getAttribute('data-testid'))!.replace('pos-kitchen-ticket-', '');
  await expect(card(page, 1).locator(`[data-testid=pos-kitchen-ticket-${firstId}-round]`)).toHaveText('Order 1');
  await expect(card(page, 1).locator(`[data-testid=pos-kitchen-ticket-${firstId}-rush-mark]`)).toHaveText('Rush');
  await expect(card(page, 2).locator(`[data-testid=pos-kitchen-ticket-${secondId}-rush-mark]`)).toHaveCount(0);
  await expect(card(page, 2).locator(`[data-testid=pos-kitchen-ticket-${secondId}-status]`)).toHaveText('To prepare');
  await expect(card(page, 2).locator(`[data-testid=pos-kitchen-ticket-${secondId}-time]`)).toHaveText(/^\d{1,2}:\d{2}(\s?[AP]M)?$/);
  const first = await ticket(context, firstId);
  expect([first.round_no, first.priority, first.status]).toEqual([1, 'rush', 'pending']);

  // Live, with the sheet open: the kitchen marks round 1 ready; the till voids the bread of round 2 (KITCHEN-F29).
  await post(context, '/kitchen/tickets/ready', { ticket_id: firstId });
  await expect(card(page, 1).locator(`[data-testid=pos-kitchen-ticket-${firstId}-status]`)).toHaveText('Ready');
  const second = await ticket(context, secondId);
  const breadDish = second.items.find((item) => item.name === bread.name)!;
  await post(context, '/sale/orders/void_line', { order_id: second.order_id, line_id: breadDish.id, reason: 'Ordered by mistake' });
  await expect(sheet(page).locator(`[data-testid=pos-kitchen-dish-${breadDish.id}-voided]`)).toHaveText('Voided');
  await expect(sheet(page).locator(`[data-testid=pos-kitchen-dish-${breadDish.id}]`)).toHaveAttribute('data-status', 'voided');
  const struck = await sheet(page)
    .locator(`[data-testid=pos-kitchen-dish-${breadDish.id}] .pos-kticket__dish-name`)
    .evaluate((name) => getComputedStyle(name).textDecorationLine);
  expect(struck, 'the voided dish is struck').toContain('line-through');
  await expect(card(page, 2).locator(`[data-testid=pos-kitchen-ticket-${secondId}-status]`)).toHaveText('To prepare');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(card(page, 1)).toBeVisible();
    await still(page);
    await page.screenshot({ path: shot(`APP-KITCHEN-KITCHEN-F19-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  // KITCHEN-F20: a ready round offers no rush; the one that cooks does, both ways.
  await expect(sheet(page).locator(`[data-testid=pos-kitchen-ticket-${firstId}-rush]`)).toHaveCount(0);
  const rush = sheet(page).locator(`[data-testid=pos-kitchen-ticket-${secondId}-rush]`);
  await expect(rush).toHaveText('Mark rush');
  await rush.click();
  await expect(rush).toHaveText('Remove rush');
  await expect(rush).toHaveAttribute('aria-pressed', 'true');
  await expect(card(page, 2).locator(`[data-testid=pos-kitchen-ticket-${secondId}-rush-mark]`)).toHaveText('Rush');
  expect((await ticket(context, secondId)).priority).toBe('rush');
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect(rush).toBeVisible();
    await rush.scrollIntoViewIfNeeded();
    await still(page);
    await page.screenshot({ path: shot(`APP-KITCHEN-KITCHEN-F20-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await rush.click();
  await expect(rush).toHaveText('Mark rush');
  await expect(card(page, 2).locator(`[data-testid=pos-kitchen-ticket-${secondId}-rush-mark]`)).toHaveCount(0);
  expect((await ticket(context, secondId)).priority).toBe('normal');
  await expect(sheet(page).locator('[data-testid=pos-kitchen-tickets-error]')).toHaveCount(0);

  // ✕ closes it.
  await sheet(page).locator('[data-testid=pos-kitchen-tickets-close]').click();
  await expect(sheet(page)).toBeHidden();
});
