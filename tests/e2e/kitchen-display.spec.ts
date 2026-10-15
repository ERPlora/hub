// Kitchen in Chrome (apps/kitchen/WORKBOOK.md), with the real Sales, Inventory and Printing apps: a station
// and its routing made through Kitchen's API, a check opened in Sales with one routed dish and one without
// a station, fired by Sales — the round shows up on the display by itself, live, split by station —, a dish
// tapped ready, the ticket marked ready and served from the pass; a round sent urgent through Kitchen jumps
// to the front with its «Rush» mark, and charging its check in Sales serves it once ready. Then the Tickets,
// Stations and History pages. Every screen in three viewports. What a run creates is named «E2E Kit <stamp>»
// (station), `E2E-KIT…` (products) and «e2e kitchen <stamp>» (checks); `afterAll` removes all of it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, psql, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales, shots, stamp } from './sale-helpers';
import { ownerPage } from './service-helpers';

const STAMP = stamp();
const STATION = `E2E Kit ${STAMP} Grill`;
const CHECK = `e2e kitchen ${STAMP}`;

interface Ticket {
  id: string;
  number: string;
  status: string;
  priority: string;
  items: { id: string; name: string; status: string; station_name: string }[];
}

/** The kitchen rows of this run (their tickets hold the lines of its checks), its station and its paper. */
function cleanKitchen(): void {
  const orders = "select id from sale_order where label like 'e2e kitchen %'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (select id from sale_orderline where order_id in (${orders})) union select id from kitchen_ticket where label like 'e2e kitchen %'`;
  const stations = "select id from kitchen_station where name like 'E2E Kit %'";
  psql(
    [
      `create temp table e2e_kit_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_kit_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_kit_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_kit_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_kit_tickets)',
      `delete from kitchen_productroute where station_id in (${stations}) or product_id in (select id from inventory_product where sku like 'E2E-%')`,
      `delete from kitchen_categoryroute where station_id in (${stations})`,
      `update kitchen_ticketitem set station_id = null where station_id in (${stations})`,
      `delete from kitchen_station where id in (${stations})`,
    ].join('; '),
  );
}

function cleanUp(): void {
  cleanKitchen();
  cleanSales();
  cleanInventory();
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** A check of Sales titled `CHECK`, with one line of each product. */
async function openCheck(context: BrowserContext, productIds: string[]): Promise<string> {
  const order = await post<{ id: string }>(context, '/sale/orders', { label: CHECK }, 201);
  for (const productId of productIds) await post(context, '/sale/orders/add_line', { order_id: order.id, product_id: productId, quantity: '1' });
  return order.id;
}

const card = (page: Page, id: string) => shown(page).locator(`[data-testid=kitchen-card-${id}]`);

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('A round fired in Sales reaches the display by itself; a dish, the ticket and the pass', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/display');
  try {
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    const station = await post<{ id: string }>(context, '/kitchen/stations', { name: STATION, color: '#E03131' }, 201);
    const burger = await createProduct(context, { sku: `E2E-KIT${STAMP}B`, name: `E2E Kit ${STAMP} Burger` });
    const soup = await createProduct(context, { sku: `E2E-KIT${STAMP}S`, name: `E2E Kit ${STAMP} Soup` });
    await post(context, '/kitchen/routing', { station_id: station.id, product_id: burger.id });
    const order = await openCheck(context, [burger.id, soup.id]);
    const fired = await post<{ order: { lines: { id: string }[] } }>(context, '/sale/orders/fire', { order_id: order });
    const [burgerLine, soupLine] = fired.order.lines.map((line) => line.id);
    const ticketId = burgerLine;

    // Live: the round appears without reloading, with its label, its dishes and their stations.
    await expect(card(page, ticketId)).toBeVisible();
    await expect(card(page, ticketId)).toContainText(CHECK);
    await expect(shown(page).locator(`[data-testid=kitchen-line-${burgerLine}-station]`)).toHaveText(STATION);
    await expect(shown(page).locator(`[data-testid=kitchen-line-${soupLine}-station]`)).toHaveText('No station');

    // The station's own view: only its dish.
    await shown(page).locator(`[data-testid=kitchen-display-station-${station.id}]`).click();
    await expect(shown(page).locator(`[data-testid=kitchen-line-${burgerLine}]`)).toBeVisible();
    await expect(shown(page).locator(`[data-testid=kitchen-line-${soupLine}]`)).toHaveCount(0);
    await shots(page, 'kitchen-display-station', async (p) => {
      await expect(card(p, ticketId)).toBeVisible();
    });

    // One tap marks the grill's dish ready: the grill has nothing left of it, so it leaves its view.
    await shown(page).locator(`[data-testid=kitchen-line-${burgerLine}]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    await shown(page).locator('[data-testid=kitchen-display-station-all]').click();
    await expect(shown(page).locator(`[data-testid=kitchen-line-${burgerLine}]`)).toHaveAttribute('data-status', 'ready');
    await shots(page, 'kitchen-display-all', async (p) => {
      await expect(card(p, ticketId)).toBeVisible();
    });

    // «Ready» marks the rest: the ticket goes to the pass; «Served» hands it over.
    await shown(page).locator(`[data-testid=kitchen-card-${ticketId}-bump]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    await shown(page).locator('[data-testid=kitchen-display-view-ready]').click();
    await expect(card(page, ticketId)).toBeVisible();
    await expect(shown(page).locator(`[data-testid=kitchen-card-${ticketId}-status]`)).toHaveText('Ready');
    await shots(page, 'kitchen-display-ready', async (p) => {
      await expect(card(p, ticketId)).toBeVisible();
    });
    await shown(page).locator(`[data-testid=kitchen-card-${ticketId}-served]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    const saved = await api<Ticket>(context, A, 'GET', `/kitchen/tickets/detail?ticket_id=${ticketId}`);
    expect(saved.data.status).toBe('served');
  } finally {
    await context.close();
  }
});

test('A round sent urgent jumps to the front; charging its check serves it once ready', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/display');
  try {
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    const salad = await createProduct(context, { sku: `E2E-KIT${STAMP}L`, name: `E2E Kit ${STAMP} Salad` });
    const first = await openCheck(context, [salad.id]);
    await post(context, '/sale/orders/fire', { order_id: first });
    const second = await openCheck(context, [salad.id]);
    const rush = await post<Ticket>(context, '/kitchen/tickets/send', { order_id: second, priority: 'rush' }, 201);
    expect(rush.priority).toBe('rush');

    await expect(card(page, rush.id)).toBeVisible();
    await expect(shown(page).locator(`[data-testid=kitchen-card-${rush.id}-priority]`)).toHaveText('Rush');
    const order = await shown(page).locator('[data-testid^=kitchen-card-][aria-label]').evaluateAll((cards) => cards.map((c) => c.getAttribute('data-testid')));
    expect(order[0]).toBe(`kitchen-card-${rush.id}`);

    await shown(page).locator(`[data-testid=kitchen-card-${rush.id}-bump]`).click();
    await expect(card(page, rush.id)).toHaveCount(0);
    await shown(page).locator('[data-testid=kitchen-display-view-ready]').click();
    await expect(card(page, rush.id)).toBeVisible();
    // Charging the whole check in Sales (card) serves what was ready: it leaves the pass by itself.
    await chargeByApi(context, { order_id: second, payments: [{ method: 'card' }] });
    await expect(card(page, rush.id)).toHaveCount(0);
  } finally {
    await context.close();
  }
});

test('Tickets, Stations and History tell what happened', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/tickets');
  try {
    const view = shown(page);
    await view.locator('[data-testid=kitchen-tickets-search] input').fill(CHECK);
    await expect(view.locator('[data-testid=kitchen-tickets-row]').filter({ hasText: CHECK }).filter({ hasText: 'Served' }).first()).toBeVisible();
    await shots(page, 'kitchen-tickets', async (p) => {
      await expect(shown(p).locator('[data-testid=kitchen-tickets-row]').filter({ hasText: CHECK }).first()).toBeVisible();
    });

    await page.goto('/kitchen/stations');
    await expect(shown(page).locator('[data-testid=kitchen-stations-row]').filter({ hasText: STATION }).first()).toBeVisible();
    await expect(shown(page).locator('[data-testid=kitchen-routing-row]').filter({ hasText: `E2E Kit ${STAMP} Burger` }).first()).toBeVisible();
    await shots(page, 'kitchen-stations', async (p) => {
      await expect(shown(p).locator('[data-testid=kitchen-stations-row]').filter({ hasText: STATION }).first()).toBeVisible();
    });

    await page.goto('/kitchen/history');
    await expect(shown(page).locator('[data-testid=kitchen-history-title]')).toHaveText('Kitchen history');
    await expect(shown(page).locator('[data-testid=kitchen-history-row]').filter({ hasText: 'Served' }).first()).toBeVisible();
    await shots(page, 'kitchen-history', async (p) => {
      await expect(shown(p).locator('[data-testid=kitchen-history-row]').filter({ hasText: 'Served' }).first()).toBeVisible();
    });

    await page.goto('/kitchen/settings');
    await expect(shown(page).locator('[data-testid=kitchen-settings-warning_minutes]')).toBeVisible();
    await shots(page, 'kitchen-settings', async (p) => {
      await expect(shown(p).locator('[data-testid=kitchen-settings-save]')).toBeVisible();
    });
  } finally {
    await context.close();
  }
});
