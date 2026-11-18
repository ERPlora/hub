// flow: KITCHEN-F10, KITCHEN-F11, KITCHEN-F12, KITCHEN-F13, KITCHEN-F14, KITCHEN-F15, KITCHEN-F16, KITCHEN-F29 — Kitchen →
// Display in Chrome, with the real Sales, Kitchen and Inventory apps: rounds fired by Sales come in by themselves and
// the display rings once for each new one, never for what was already there (F16, a Web Audio that counts its notes
// instead of sounding); a tap marks a dish ready and another tap takes it back, «⋮» → «Recall» brings back the struck
// dishes, «Ready» finishes the ticket and «⋮» → «Recall» on the pass returns it (F11, F12); «Served» hands it over
// (F13); «⋮» → «Mark rush» jumps a round to the front of the board, rings, and «Remove rush» puts it back (F14); «All day» adds up
// what is left to cook, all stations or one (F15); a dish the till voids is struck with «Voided» and its reason,
// does not answer a tap and leaves «All day» (F29); the board orders rush first and the oldest first, and a station
// shows only its own dishes, remembered on the device (F10). Each screen in 390×844, 834×1112 and 1440×900
// (`APP-KITCHEN-<flow>-<size>`). What a run creates — products `E2E-KBD-<run>-…`, the station «E2E KBD <run> Grill»,
// checks «e2e kbd <run> …» and their tickets — is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, collectProblems, psql, shown, untilStill } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { capture } from './kitchen-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { ownerPage } from './service-helpers';

const RUN = stamp();
const STATION = `E2E KBD ${RUN} Grill`;
const CHECK = `e2e kbd ${RUN}`;
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
async function fireRound(
  context: BrowserContext,
  n: number,
  products: Product[],
  label = `${CHECK} ${n}`,
): Promise<{ order: string; lines: string[] }> {
  const order = await post<{ id: string }>(context, '/sale/orders', { label }, 201);
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

/** Opens a card's «⋮» and gives one of its steps, in Ionic's popover. */
async function step(page: Page, id: string, name: 'rush' | 'recall'): Promise<Locator> {
  await shown(page).locator(`[data-testid=kitchen-card-${id}-more]`).click();
  const item = page.locator(`[data-testid=kitchen-card-${id}-${name}]`);
  await expect(item).toBeVisible();
  return item;
}

/** Whether `target`'s label is cut: an ellipsis or a clip is paint, the text keeps its full width. */
function labelCut(target: Locator): Promise<boolean> {
  return target.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const text = range.getBoundingClientRect();
    const own = el.getBoundingClientRect();
    return text.width === 0 || text.left < own.left - 1 || text.right > own.right + 1;
  });
}

function splitWords(target: Locator): Promise<string[]> {
  return target.evaluate((el) => {
    const broken: string[] = [];
    for (const node of el.childNodes) {
      if (node.nodeType !== Node.TEXT_NODE) continue;
      const text = node as Text;
      for (const match of text.data.matchAll(/\S+/g)) {
        const start = match.index ?? 0;
        const range = document.createRange();
        range.setStart(text, start);
        range.setEnd(text, start + match[0].length);
        if (range.getClientRects().length > 1) broken.push(match[0]);
      }
    }
    return broken;
  });
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
    const problems = await collectProblems(page);
    await page.goto('/kitchen/display');
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    await page.reload();
    const view = shown(page);
    await expect(view.locator('[data-testid=kitchen-display-views]')).toBeVisible();
    await expect(view.locator('[data-testid=kitchen-display-loading]')).toHaveCount(0);
    // The views are tabs with their names, the one open selected.
    const views = view.getByRole('tablist', { name: 'Views of the display' });
    await expect(views.getByRole('tab', { name: 'Tickets' })).toHaveAttribute('aria-selected', 'true');
    await expect(views.getByRole('tab', { name: 'Ready' })).toHaveAttribute('aria-selected', 'false');
    await expect(views.getByRole('tab', { name: 'All-Day' })).toBeVisible();
    // «Full screen» puts the display alone on the screen and a second tap gives the shell back.
    await view.locator('[data-testid=kitchen-display-fullscreen]').click();
    await expect(view.locator('[data-testid=kitchen-display]')).toHaveClass(/kds--fullscreen/);
    expect(await page.evaluate(() => document.fullscreenElement?.getAttribute('data-testid'))).toBe('kitchen-display');
    await view.locator('[data-testid=kitchen-display-fullscreen]').click();
    await expect(view.locator('[data-testid=kitchen-display]')).not.toHaveClass(/kds--fullscreen/);
    // F16: opening the display does not ring for what was already there.
    expect(await rings(page)).toBe(0);
    // The display opens without an error, nor a CSP refusal.
    const opened = await problems();
    expect([opened.page, opened.console, opened.csp]).toEqual([[], [], []]);

    const round = await fireRound(context, 1, [steak, salad]);
    const [steakLine, saladLine] = round.lines;
    const ticketId = steakLine;
    await expect(card(page, ticketId)).toBeVisible();
    await expect.poll(() => rings(page), { message: 'one ring for the new round' }).toBe(1);
    await expect(card(page, ticketId).locator(`[data-testid=kitchen-card-${ticketId}-label]`)).toHaveText(`${CHECK} 1`);
    await expect(dish(page, steakLine).locator('[data-testid$=-station]')).toHaveText(STATION);
    const dot = await dish(page, steakLine).locator('.ep-station-dot').boundingBox();
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
    // ...and «⋮» → «Recall» on the card brings back the struck ones.
    await dish(page, saladLine).click();
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', 'ready');
    // Half done, the card offers «Ready» across its foot and «⋮» beside it, with «Mark rush» and «Recall»; on a
    // phone and on a tablet upright or on its side none is cut ("Recal…") or spills out of the card, and each is a
    // 48 px touch target.
    for (const size of [{ width: 390, height: 844 }, { width: 834, height: 1112 }, { width: 1024, height: 768 }, { width: 820, height: 1180 }]) {
      await page.setViewportSize(size);
      await card(page, ticketId).scrollIntoViewIfNeeded();
      const edge = await card(page, ticketId).boundingBox();
      // The three views fit their bar whole: none is clipped or scrolled out of it.
      const views = await view.locator('[data-testid=kitchen-display-views]').boundingBox();
      for (const tab of ['tickets', 'ready', 'allday']) {
        const box = await view.locator(`[data-testid=kitchen-display-view-${tab}]`).boundingBox();
        expect(box!.x >= views!.x - 1 && box!.x + box!.width <= views!.x + views!.width + 1, `${tab} whole at ${size.width}`).toBe(true);
      }
      // The head row (type, label, clock) leads the card and its pills follow it, in iOS mode too.
      const head = await view.locator(`[data-testid=kitchen-card-${ticketId}-head]`).boundingBox();
      const pill = await view.locator(`[data-testid=kitchen-card-${ticketId}-status]`).boundingBox();
      expect(head!.y + head!.height, `the pills under the head at ${size.width}`).toBeLessThanOrEqual(pill!.y + 1);
      for (const action of ['bump', 'more']) {
        const button = view.locator(`[data-testid=kitchen-card-${ticketId}-${action}]`);
        await expect(button, `${action} at ${size.width}`).toBeVisible();
        const box = await button.boundingBox();
        expect([box!.width, box!.height].every((side) => side >= 48), `${action} at ${size.width}: 48 px`).toBe(true);
        expect(box!.x + box!.width, `${action} at ${size.width}: inside the card`).toBeLessThanOrEqual(edge!.x + edge!.width + 1);
      }
      expect(await labelCut(view.locator(`[data-testid=kitchen-card-${ticketId}-bump]`)), `Ready at ${size.width}: its label whole`).toBe(false);
      for (const name of ['rush', 'recall'] as const) {
        const item = await step(page, ticketId, name);
        // Measured once Ionic's popover has finished sliding in.
        await untilStill(page);
        const box = await item.boundingBox();
        expect(box!.height, `${name} at ${size.width}: 48 px`).toBeGreaterThanOrEqual(48);
        expect(box!.x >= 0 && box!.x + box!.width <= size.width, `${name} at ${size.width}: on the screen`).toBe(true);
        expect(await labelCut(item.locator('ion-label')), `${name} at ${size.width}: its label whole`).toBe(false);
        // Escape closes the menu without a step, as the system Back does.
        await page.keyboard.press('Escape');
        await expect(item).toBeHidden();
      }
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await (await step(page, ticketId, 'recall')).click();
    await expect(dish(page, saladLine)).toHaveAttribute('data-status', TO_DO);

    // F11: «Ready» finishes it: off «Tickets», onto «Ready».
    await view.locator(`[data-testid=kitchen-card-${ticketId}-bump]`).click();
    await expect(card(page, ticketId)).toHaveCount(0);
    await view.locator('[data-testid=kitchen-display-view-ready]').click();
    await expect(card(page, ticketId).locator(`[data-testid=kitchen-card-${ticketId}-status]`)).toHaveText('Ready');
    // F12: «⋮» → «Recall» on the pass returns it to the line, its dishes to do.
    await capture(page, 'KITCHEN-F12', async () => {
      await card(page, ticketId).scrollIntoViewIfNeeded();
      await expect(view.locator(`[data-testid=kitchen-card-${ticketId}-more]`)).toBeVisible();
    });
    await (await step(page, ticketId, 'recall')).click();
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

    // F14: «⋮» → «Mark rush» on the newer round: «Rush», at the front, and the display rings once.
    expect(await rings(page)).toBe(0);
    await expect(await step(page, newerId, 'rush')).toHaveText('Mark rush');
    await page.locator(`[data-testid=kitchen-card-${newerId}-rush]`).click();
    await expect(view.locator(`[data-testid=kitchen-card-${newerId}-priority]`)).toHaveText('Rush');
    await expect.poll(async () => (await order())[0]).toBe(`kitchen-card-${newerId}`);
    await expect.poll(() => rings(page), { message: 'a round turned rush rings' }).toBe(1);
    await capture(page, 'KITCHEN-F14', async () => {
      await card(page, newerId).scrollIntoViewIfNeeded();
      await expect(view.locator(`[data-testid=kitchen-card-${newerId}-priority]`)).toBeVisible();
    });
    const unrush = await step(page, newerId, 'rush');
    await expect(unrush).toHaveText('Remove rush');
    await unrush.click();
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
    const struck = await dish(page, saladLine).locator('.ep-order-ticket__name').evaluate((name) => getComputedStyle(name).textDecorationLine);
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

test('KITCHEN-F10: the destination and waiter keep whole words on separate lines at every board width', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/display', { width: 1280, height: 800 });
  try {
    const round = await fireRound(context, 4, [steak], 'e2e kbd 4');
    const ticketId = round.lines[0];
    const destination = card(page, ticketId).locator(`[data-testid=kitchen-card-${ticketId}-label]`);
    const waiter = card(page, ticketId).locator(`[data-testid=kitchen-card-${ticketId}-waiter]`);
    await expect(waiter).toHaveText('Waiter: owner@example.com');
    // The built sheet can put Ionic after the theme; reproduce that cascade with Ionic's own rule.
    await page.evaluate(() => {
      const ionic = Array.from(document.querySelectorAll('style')).find((style) => style.textContent?.includes('.item.sc-ion-label-ios-h'));
      if (!ionic) throw new Error('Ionic label styles not found');
      ionic.parentElement?.append(ionic);
    });

    for (const size of [
      { width: 375, height: 667, columns: 1 },
      { width: 820, height: 1180, columns: 2 },
      { width: 1280, height: 800, columns: 3 },
    ]) {
      await page.setViewportSize(size);
      await expect(card(page, ticketId)).toBeVisible();
      const columns = await card(page, ticketId).evaluate((el) => getComputedStyle(el.parentElement!).gridTemplateColumns.split(' ').length);
      expect(columns, `board columns at ${size.width}`).toBe(size.columns);
      const destinationBox = await destination.boundingBox();
      const waiterBox = await waiter.boundingBox();
      expect(waiterBox!.y, `waiter below the destination at ${size.width}`).toBeGreaterThanOrEqual(
        destinationBox!.y + destinationBox!.height - 1,
      );
      expect(await splitWords(destination), `whole destination words at ${size.width}`).toEqual([]);
      expect(await splitWords(waiter), `whole waiter words at ${size.width}`).toEqual([]);
    }
  } finally {
    await context.close();
  }
});
