// flow: KITCHEN-F10, KITCHEN-F11, KITCHEN-F12, KITCHEN-F13, KITCHEN-F14, KITCHEN-F15, KITCHEN-F16, KITCHEN-F29 — Kitchen →
// Display in Chrome, with the real Sales, Kitchen and Inventory apps: rounds fired by Sales come in by themselves and
// the display rings once for each new one, never for what was already there (F16, a Web Audio that counts its notes
// instead of sounding); a tap marks a dish ready and another tap takes it back, «Recall» brings back the struck
// dishes, «Ready» finishes the ticket and «Recall» on the pass returns it (F11, F12); «Served» hands it over (F13);
// «Mark rush» jumps a round to the front of the board, rings, and «Remove rush» puts it back (F14); «All day» adds up
// what is left to cook, all stations or one (F15); a dish the till voids is struck with «Voided» and its reason,
// does not answer a tap and leaves «All day» (F29); the board orders rush first and the oldest first, and a station
// shows only its own dishes, remembered on the device (F10). Each screen in 390×844, 834×1112 and 1440×900
// (`APP-KITCHEN-<flow>-<size>`). What a run creates — products `E2E-KBD-<run>-…`, the station «E2E KBD <run> Grill»,
// checks «e2e kbd <run> …» and their tickets — is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { ownerPage, settled } from './service-helpers';

const RUN = stamp();
const STATION = `E2E KBD ${RUN} Grill`;
const CHECK = `e2e kbd ${RUN}`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
/** A dish to do: pending, or preparing once its ticket started. */
const TO_DO = /^(pending|preparing)$/;

let steak: Product;
let salad: Product;
let stationId: string;

function cleanRun(): void {
  const orders = "select id from sale_order where label like 'e2e kbd %'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (select id from sale_orderline where order_id in (${orders}))`;
  const stations = "select id from kitchen_station where name like 'E2E KBD %'";
  psql(
    [
      `create temp table e2e_kbd_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_kbd_tickets))",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_kbd_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_kbd_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_kbd_tickets)',
      `delete from kitchen_productroute where station_id in (${stations}) or product_id in (select id from inventory_product where sku like 'E2E-KBD-%')`,
      `update kitchen_ticketitem set station_id = null where station_id in (${stations})`,
      `delete from kitchen_station where id in (${stations})`,
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

/** A check of Sales titled `CHECK <n>`, a line per product, fired by Sales: the ids of its check and its lines. */
async function fireRound(context: BrowserContext, n: number, products: Product[]): Promise<{ order: string; lines: string[] }> {
  const order = await post<{ id: string }>(context, '/sale/orders', { label: `${CHECK} ${n}` }, 201);
  for (const product of products) await post(context, '/sale/orders/add_line', { order_id: order.id, product_id: product.id, quantity: '1' });
  const fired = await post<{ order: { lines: { id: string }[] } }>(context, '/sale/orders/fire', { order_id: order.id });
  return { order: order.id, lines: fired.order.lines.map((line) => line.id) };
}

/** A Web Audio that counts the notes it is asked to play (and plays none): what the display rings. */
async function countRings(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const scope = window as unknown as { __kitchenNotes: number; AudioContext: unknown };
    scope.__kitchenNotes = 0;
    const param = () => ({ setValueAtTime() {}, linearRampToValueAtTime() {} });
    scope.AudioContext = class {
      state = 'running';
      currentTime = 0;
      destination = {};
      resume() {
        return Promise.resolve();
      }
      createGain() {
        return { gain: param(), connect() {} };
      }
      createOscillator() {
        scope.__kitchenNotes += 1;
        return { type: 'sine', frequency: param(), connect() {}, start() {}, stop() {} };
      }
    };
  });
}

const rings = (page: Page): Promise<number> => page.evaluate(() => (window as unknown as { __kitchenNotes: number }).__kitchenNotes / 2 /* every tone rings two notes */);
const card = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=kitchen-card-${id}]`);
const dish = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=kitchen-line-${id}]`);

async function capture(page: Page, flow: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    await page.screenshot({ path: shot(`APP-KITCHEN-${flow}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

test.beforeAll(async ({ browser }) => {
  cleanUp();
  const { context } = await ownerPage(browser, '/kitchen/display');
  steak = await createProduct(context, { name: `E2E KBD Steak ${RUN}`, sku: `E2E-KBD-${RUN}-STK`, price: 1800, tax_category_key: 'restaurant.food' });
  salad = await createProduct(context, { name: `E2E KBD Salad ${RUN}`, sku: `E2E-KBD-${RUN}-SAL`, price: 700, tax_category_key: 'restaurant.food' });
  stationId = (await post<{ id: string }>(context, '/kitchen/stations', { name: STATION, color: '#1971C2' }, 201)).id;
  await post(context, '/kitchen/routing', { station_id: stationId, product_id: steak.id });
  // The factory sound: on, chime, volume 70.
  await post(context, '/kitchen/settings', { sound_enabled: true, sound_volume: 70, sound_tone: 'chime' });
  await context.close();
});

test.afterAll(cleanUp);

test('KITCHEN-F10, F11, F12, F13, F16: a new round rings once and comes in; a dish and the ticket go ready, come back and are served', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/settings', { width: 1440, height: 900 });
  try {
    await countRings(page);
    await page.goto('/kitchen/display');
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    await page.reload();
    const view = shown(page);
    await expect(view.locator('[data-testid=kitchen-display-views]')).toBeVisible();
    await expect(view.locator('[data-testid=kitchen-display-loading]')).toHaveCount(0);
    // kitchen#116: the views are tabs with their names, the one open selected.
    const views = view.getByRole('tablist', { name: 'Views of the display' });
    await expect(views.getByRole('tab', { name: 'Tickets' })).toHaveAttribute('aria-selected', 'true');
    await expect(views.getByRole('tab', { name: 'Ready' })).toHaveAttribute('aria-selected', 'false');
    await expect(views.getByRole('tab', { name: 'All-Day' })).toBeVisible();
    // kitchen#60: «Full screen» puts the display alone on the screen and a second tap gives the shell back.
    await view.locator('[data-testid=kitchen-display-fullscreen]').click();
    await expect(view.locator('[data-testid=kitchen-display]')).toHaveClass(/kds--fullscreen/);
    expect(await page.evaluate(() => document.fullscreenElement?.getAttribute('data-testid'))).toBe('kitchen-display');
    await view.locator('[data-testid=kitchen-display-fullscreen]').click();
    await expect(view.locator('[data-testid=kitchen-display]')).not.toHaveClass(/kds--fullscreen/);
    // F16: opening the display does not ring for what was already there.
    expect(await rings(page)).toBe(0);

    const round = await fireRound(context, 1, [steak, salad]);
    const [steakLine, saladLine] = round.lines;
    const ticketId = steakLine;
    await expect(card(page, ticketId)).toBeVisible();
    await expect.poll(() => rings(page), { message: 'one ring for the new round' }).toBe(1);
    await expect(card(page, ticketId).locator(`[data-testid=kitchen-card-${ticketId}-label]`)).toHaveText(`${CHECK} 1`);
    await expect(dish(page, steakLine).locator('[data-testid$=-station]')).toHaveText(STATION);
    const dot = await dish(page, steakLine).locator('.kds-line__dot').boundingBox();
    expect(dot?.width ?? 0, 'the station colour beside the dish').toBeGreaterThan(6);
    await capture(page, 'KITCHEN-F10', async () => {
      await card(page, ticketId).scrollIntoViewIfNeeded();
      await expect(card(page, ticketId)).toBeInViewport();
    });
    await capture(page, 'KITCHEN-F16', async () => {
      await expect(card(page, ticketId)).toBeVisible();
    });

    // F11: a tap marks the salad ready (struck, ✓); F12: another tap takes it back.
    await dish(page, saladLine).click();
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', 'ready');
    await capture(page, 'KITCHEN-F11', async () => {
      await card(page, ticketId).scrollIntoViewIfNeeded();
      await expect(dish(page, saladLine)).toHaveAttribute('data-status', 'ready');
    });
    await dish(page, saladLine).click();
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', TO_DO);
    // ...and «Recall» on the card brings back the struck ones.
    await dish(page, saladLine).click();
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', 'ready');
    // kitchen#156, kitchen#12: half done, the card offers «Ready», «Mark rush» and «Recall»; on a tablet upright or
    // on its side none is cut ("Recal…") or spills out of the card, and each is a 44 px touch target.
    for (const size of [{ width: 834, height: 1112 }, { width: 1112, height: 834 }, { width: 820, height: 1180 }]) {
      await page.setViewportSize(size);
      await card(page, ticketId).scrollIntoViewIfNeeded();
      const edge = await card(page, ticketId).boundingBox();
      for (const action of ['bump', 'rush', 'recall']) {
        const button = view.locator(`[data-testid=kitchen-card-${ticketId}-${action}]`);
        await expect(button, `${action} at ${size.width}`).toBeVisible();
        const box = await button.boundingBox();
        expect(box!.height, `${action} at ${size.width}: 44 px`).toBeGreaterThanOrEqual(44);
        expect(box!.x + box!.width, `${action} at ${size.width}: inside the card`).toBeLessThanOrEqual(edge!.x + edge!.width + 1);
        // The laid-out label against the button: an ellipsis or a clip is paint, the text keeps its full width.
        const cut = await button.evaluate((el) => {
          const range = document.createRange();
          range.selectNodeContents(el);
          const text = range.getBoundingClientRect();
          const own = el.getBoundingClientRect();
          return text.width === 0 || text.left < own.left - 1 || text.right > own.right + 1;
        });
        expect(cut, `${action} at ${size.width}: its label whole`).toBe(false);
      }
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await view.locator(`[data-testid=kitchen-card-${ticketId}-recall]`).click();
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', TO_DO);

    // F11: «Ready» finishes it: off «Tickets», onto «Ready».
    await view.locator(`[data-testid=kitchen-card-${ticketId}-bump]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    await view.locator('[data-testid=kitchen-display-view-ready]').click();
    await expect(card(page, ticketId).locator(`[data-testid=kitchen-card-${ticketId}-status]`)).toHaveText('Ready');
    // F12: «Recall» on the pass returns it to the line, its dishes to do.
    await capture(page, 'KITCHEN-F12', async () => {
      await card(page, ticketId).scrollIntoViewIfNeeded();
      await expect(view.locator(`[data-testid=kitchen-card-${ticketId}-recall]`)).toBeVisible();
    });
    await view.locator(`[data-testid=kitchen-card-${ticketId}-recall]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    await view.locator('[data-testid=kitchen-display-view-tickets]').click();
    await expect(dish(page, steakLine)).toHaveAttribute('data-status', TO_DO);
    expect((await api<{ status: string }>(context, A, 'GET', `/kitchen/tickets/detail?ticket_id=${ticketId}`)).data.status).toBe('preparing');

    // F13: ready again, then «Served» from the pass.
    await view.locator(`[data-testid=kitchen-card-${ticketId}-bump]`).click();
    await view.locator('[data-testid=kitchen-display-view-ready]').click();
    await capture(page, 'KITCHEN-F13', async () => {
      await card(page, ticketId).scrollIntoViewIfNeeded();
      await expect(view.locator(`[data-testid=kitchen-card-${ticketId}-served]`)).toBeVisible();
    });
    await view.locator(`[data-testid=kitchen-card-${ticketId}-served]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    expect((await api<{ status: string }>(context, A, 'GET', `/kitchen/tickets/detail?ticket_id=${ticketId}`)).data.status).toBe('served');
    // Nothing of this rang again: only new rounds and rushes ring.
    expect(await rings(page)).toBe(1);
  } finally {
    await context.close();
  }
});

test('KITCHEN-F14, F15, F29, F10: rush jumps to the front and rings, «All day» adds up, a voided dish is struck, a station sees its own', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/settings', { width: 1440, height: 900 });
  try {
    await countRings(page);
    const older = await fireRound(context, 2, [steak, salad]);
    const newer = await fireRound(context, 3, [steak]);
    await page.goto('/kitchen/display');
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    await page.reload();
    const view = shown(page);
    const olderId = older.lines[0];
    const newerId = newer.lines[0];
    await expect(card(page, newerId)).toBeVisible();
    const order = () =>
      view.locator('[data-testid^=kitchen-card-][aria-label]').evaluateAll((cards) => cards.map((c) => c.getAttribute('data-testid')));
    const before = await order();
    // F10: the oldest first.
    expect(before.indexOf(`kitchen-card-${olderId}`)).toBeLessThan(before.indexOf(`kitchen-card-${newerId}`));

    // F14: «Mark rush» on the newer round: «Rush», at the front, and the display rings once.
    expect(await rings(page)).toBe(0);
    await view.locator(`[data-testid=kitchen-card-${newerId}-rush]`).click();
    await expect(view.locator(`[data-testid=kitchen-card-${newerId}-priority]`)).toHaveText('Rush');
    await expect.poll(async () => (await order())[0]).toBe(`kitchen-card-${newerId}`);
    await expect.poll(() => rings(page), { message: 'a round turned rush rings' }).toBe(1);
    await expect(view.locator(`[data-testid=kitchen-card-${newerId}-rush]`)).toHaveText('Remove rush');
    await capture(page, 'KITCHEN-F14', async () => {
      await card(page, newerId).scrollIntoViewIfNeeded();
      await expect(view.locator(`[data-testid=kitchen-card-${newerId}-priority]`)).toBeVisible();
    });
    await view.locator(`[data-testid=kitchen-card-${newerId}-rush]`).click();
    await expect(view.locator(`[data-testid=kitchen-card-${newerId}-priority]`)).toHaveCount(0);
    await expect.poll(async () => (await order()).indexOf(`kitchen-card-${olderId}`)).toBeLessThan((await order()).indexOf(`kitchen-card-${newerId}`));

    // F15: «All day» adds up what is left to cook: two steaks at the grill and the salad without a station.
    await view.locator('[data-testid=kitchen-display-view-allday]').click();
    const allDay = view.locator('[data-testid=kitchen-display-allday]');
    const steakRow = allDay.locator('tr').filter({ hasText: steak.name });
    const saladRow = allDay.locator('tr').filter({ hasText: salad.name });
    await expect(steakRow).toContainText('2');
    await expect(steakRow).toContainText(STATION);
    await expect(saladRow).toContainText('No station');
    await capture(page, 'KITCHEN-F15', async () => {
      await expect(steakRow).toBeVisible();
    });

    // F10, F15: the grill sees only its own, and the choice is remembered on this device.
    await view.locator(`[data-testid=kitchen-display-station-${stationId}]`).click();
    await expect(steakRow).toBeVisible();
    await expect(saladRow).toHaveCount(0);
    await page.reload();
    await expect(shown(page).locator(`[data-testid=kitchen-display-station-${stationId}]`)).toHaveClass(/segment-button-checked/);
    await shown(page).locator('[data-testid=kitchen-display-view-tickets]').click();
    await expect(dish(page, older.lines[0])).toBeVisible();
    await expect(dish(page, older.lines[1])).toHaveCount(0);
    await shown(page).locator('[data-testid=kitchen-display-station-all]').click();
    await expect(dish(page, older.lines[1])).toBeVisible();

    // F29: the till voids the salad of the older round: struck, «Voided» with its reason, a tap does nothing, and
    // «All day» no longer counts it.
    const [, saladLine] = older.lines;
    await post(context, '/sale/orders/void_line', { order_id: older.order, line_id: saladLine, reason: 'Customer changed their mind' });
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', 'voided');
    await expect(dish(page, saladLine)).toContainText('Voided');
    await expect(dish(page, saladLine)).toContainText('Customer changed their mind');
    await expect(dish(page, saladLine)).toHaveAttribute('aria-disabled', 'true');
    await dish(page, saladLine).click({ force: true });
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', 'voided');
    const struck = await dish(page, saladLine).locator('.kds-line__name').evaluate((name) => getComputedStyle(name).textDecorationLine);
    expect(struck, 'the voided dish is struck').toContain('line-through');
    await capture(page, 'KITCHEN-F29', async () => {
      await card(page, olderId).scrollIntoViewIfNeeded();
      await expect(dish(page, saladLine)).toBeVisible();
    });
    await shown(page).locator('[data-testid=kitchen-display-view-allday]').click();
    await expect(shown(page).locator('[data-testid=kitchen-display-allday] tr').filter({ hasText: steak.name })).toBeVisible();
    await expect(shown(page).locator('[data-testid=kitchen-display-allday] tr').filter({ hasText: salad.name })).toHaveCount(0);
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
  } finally {
    await context.close();
  }
});
