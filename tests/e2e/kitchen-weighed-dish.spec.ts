// flow: KITCHEN-F10, KITCHEN-F15 — a dish sold by weight sent from a check of Sales to Kitchen → Display, in Chrome with
// the real Sales, Inventory and Kitchen apps (hub#2548): its card says «0,35 kg» before the name and a dish sold by
// units «2×», each on one line and clear of its name; «All-Day» says what is left of it with its unit. In Spanish and
// in English, measured and captured in 375×667, 820×1180 and 1280×720 (`APP-KITCHEN-weighed-dish-<view>-<lang>-<size>`).
// What a run creates — the products `E2E-KWD-<run>-…` and the check «e2e kwd <run>» — is deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, psql, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { ownerPage } from './service-helpers';

const RUN = stamp();
const CHECK = `e2e kwd ${RUN}`;
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1280', width: 1280, height: 720 },
];
// «All-Day» lists the most first, and in «All» with each dish's station.
const SAID = {
  en: { card: ['0.35 kg', '2×'], allDay: [['Croquetas', 'No station', '2'], ['Gambas al peso', 'No station', '0.35 kg']] },
  es: { card: ['0,35 kg', '2×'], allDay: [['Croquetas', 'Sin estación', '2'], ['Gambas al peso', 'Sin estación', '0,35 kg']] },
};

function cleanUp(): void {
  const orders = "select id from sale_order where label like 'e2e kwd %'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (select id from sale_orderline where order_id in (${orders}))`;
  psql(
    [
      `create temp table e2e_kwd_tickets as ${tickets}`,
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_kwd_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_kwd_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_kwd_tickets)',
    ].join('; '),
  );
  cleanSales();
  cleanInventory();
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status: number): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** A check with 0.350 kg of prawns and two croquettes, sent to the kitchen from the till: its ticket's id. */
async function sendWeighedRound(context: BrowserContext): Promise<string> {
  const food = { tax_category_key: 'restaurant.food' };
  const prawns = await createProduct(context, { name: 'Gambas al peso', sku: `E2E-KWD-${RUN}-G`, price: 2400, unit: 'kg', ...food });
  const croquettes = await createProduct(context, { name: 'Croquetas', sku: `E2E-KWD-${RUN}-C`, price: 800, ...food });
  const order = await post<{ id: string }>(context, '/sale/orders', { label: CHECK }, 201);
  await post(context, '/sale/orders/add_line', { order_id: order.id, product_id: prawns.id, quantity: '0.350' }, 200);
  await post(context, '/sale/orders/add_line', { order_id: order.id, product_id: croquettes.id, quantity: '2' }, 200);
  return (await post<{ id: string }>(context, '/kitchen/tickets/send', { order_id: order.id }, 201)).id;
}

interface Dish {
  qty: string;
  /** How many lines the quantity takes. */
  qtyLines: number;
  /** Pixels the quantity runs into its name. */
  overlap: number;
  /** Pixels of the name cut on its right. */
  nameCut: number;
}

/** What each dish of `card` shows and how its quantity and its name sit beside each other. */
async function dishes(card: Locator): Promise<Dish[]> {
  return card.locator('.ep-order-ticket__dish').evaluateAll((rows) =>
    rows.map((row) => {
      const qty = row.querySelector<HTMLElement>('.ep-order-ticket__qty');
      const name = row.querySelector<HTMLElement>('.ep-order-ticket__name');
      if (!qty || !name) throw new Error('a dish without its quantity or its name');
      const box = qty.getBoundingClientRect();
      const lineHeight = Number.parseFloat(getComputedStyle(qty).lineHeight) || Number.parseFloat(getComputedStyle(qty).fontSize);
      return {
        qty: (qty.textContent ?? '').trim(),
        qtyLines: Math.round(box.height / lineHeight),
        overlap: Math.max(0, Math.round(box.right - name.getBoundingClientRect().left)),
        nameCut: Math.max(0, name.scrollWidth - name.clientWidth),
      };
    }),
  );
}

async function allDayRows(page: Page): Promise<string[][]> {
  const rows = shown(page).locator('[data-testid=kitchen-display-allday] tbody tr');
  return rows.evaluateAll((trs) => trs.map((tr) => Array.from(tr.querySelectorAll('td')).map((td) => (td.textContent ?? '').trim())));
}

/** How many lines each quantity of «All-Day» takes. */
async function allDayQuantityLines(page: Page): Promise<number[]> {
  const cells = shown(page).locator('[data-testid=kitchen-display-allday] tbody td.ep-order-board-totals__num');
  return cells.evaluateAll((tds) =>
    tds.map((td) => {
      const text = document.createRange();
      text.selectNodeContents(td);
      return new Set(Array.from(text.getClientRects(), (line) => Math.round(line.top))).size;
    }),
  );
}

/** At each size, the card of the round says each dish's quantity on one line clear of its name; then «All-Day» says
 *  what is left with its unit. Both captured at each size. */
async function seenAtEachSize(page: Page, ticket: string, lang: 'en' | 'es'): Promise<void> {
  const view = shown(page);
  const card = view.locator(`[data-testid=kitchen-card-${ticket}]`);
  await view.locator('[data-testid=kitchen-display-view-tickets]').click();
  await expect(card).toBeVisible();
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await card.scrollIntoViewIfNeeded();
    const seen = await dishes(card);
    expect(seen.map((dish) => dish.qty), `${lang} ${size.label}`).toEqual(SAID[lang].card);
    expect(seen.map(({ qtyLines, overlap, nameCut }) => ({ qtyLines, overlap, nameCut })), `${lang} ${size.label}`).toEqual(
      seen.map(() => ({ qtyLines: 1, overlap: 0, nameCut: 0 })),
    );
    await capture(page, `APP-KITCHEN-weighed-dish-card-${lang}-${size.label}`);
  }
  await view.locator('[data-testid=kitchen-display-view-allday]').click();
  await expect(view.locator('[data-testid=kitchen-display-allday]')).toBeVisible();
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await expect.poll(() => allDayRows(page), `${lang} ${size.label}`).toEqual(SAID[lang].allDay);
    expect(await allDayQuantityLines(page), `${lang} ${size.label}: a quantity and its unit on one line`).toEqual([1, 1]);
    await capture(page, `APP-KITCHEN-weighed-dish-allday-${lang}-${size.label}`);
  }
  await view.locator('[data-testid=kitchen-display-view-tickets]').click();
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('KITCHEN-F10, KITCHEN-F15: a dish sold by weight says its unit on its card and in «All-Day», in English and in Spanish', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/display', { width: 1280, height: 720 });
  let ticket = '';
  try {
    await page.evaluate(() => localStorage.removeItem('kitchen.display.station'));
    ticket = await sendWeighedRound(context);
    await saveSessionForTheSweep(context);
    await page.reload();
    await seenAtEachSize(page, ticket, 'en');
  } finally {
    await context.close();
  }

  const spanish = await signedInSpanish(browser, { width: 1280, height: 720 }, '/kitchen/display');
  try {
    await seenAtEachSize(spanish.page, ticket, 'es');
  } finally {
    await spanish.context.close();
  }
});
