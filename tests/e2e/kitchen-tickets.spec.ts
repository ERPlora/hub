// flow: KITCHEN-F09, KITCHEN-F21, KITCHEN-F22, KITCHEN-F23 — Kitchen → Tickets in Chrome, with the real Sales,
// Inventory, Kitchen and Printing apps: a round sent from a check of Sales is moved from its row — «Fire», «Ready»,
// «Recall», «Ready» again and «Served» — and «⋮ → Reprint» queues its copy (F21, F09); another is cancelled after a
// dialog that says the check in the till does not change, with its reason (F22, kitchen#166); «New ticket» makes one
// by hand from page 2 and the list comes back to page 1 to show it (F23, kitchen#133). On a tablet the ticket's
// number reads whole (kitchen#134). Each screen in 390×844, 834×1112 and 1440×900 (`APP-KITCHEN-<flow>-<size>`). What a
// run creates — the printer «e2e KTK <run>», products `E2E-KTK-<run>-…`, checks and tickets «e2e ktk <run> …» — is
// deleted after it.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { cleanSales, stamp } from './sale-helpers';
import { ownerPage, rowAction, settled } from './service-helpers';

const RUN = stamp();
const CHECK = `e2e ktk ${RUN}`;
const PRINTER = `e2e KTK ${RUN} Grill`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

interface Sent {
  id: string;
  number: string;
  short_number: string;
}

let burger: Product;
let printerBefore: string | null = null;

function cleanUp(): void {
  const orders = "select id from sale_order where label like 'e2e ktk %'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (select id from sale_orderline where order_id in (${orders})) union select id from kitchen_ticket where label like 'e2e ktk %'`;
  psql(
    [
      `create temp table e2e_ktk_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_ktk_tickets))",
      "delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e KTK %')",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_ktk_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_ktk_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_ktk_tickets)',
    ].join('; '),
  );
  psql("update printing_settings set kitchen_printer_id = null where kitchen_printer_id in (select id from printing_printer where name like 'e2e KTK %')");
  psql("delete from printing_printer where name like 'e2e KTK %'");
  cleanSales();
  cleanInventory();
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

/** A check of Sales titled `CHECK <n>` with a burger, sent to the kitchen by Kitchen: its ticket. */
async function sendRound(context: BrowserContext, n: number): Promise<Sent> {
  const order = await post<{ id: string }>(context, '/sale/orders', { label: `${CHECK} ${n}` }, 201);
  await post(context, '/sale/orders/add_line', { order_id: order.id, product_id: burger.id, quantity: '1' });
  return post<Sent>(context, '/kitchen/tickets/send', { order_id: order.id }, 201);
}

async function statusOf(context: BrowserContext, id: string): Promise<string> {
  return (await api<{ status: string }>(context, A, 'GET', `/kitchen/tickets/detail?ticket_id=${id}`)).data.status;
}

const row = (page: Page, text: string): Locator => shown(page).locator('[data-testid=kitchen-tickets-row]').filter({ hasText: text }).first();

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
  const { context } = await ownerPage(browser, '/kitchen/tickets');
  burger = await createProduct(context, { name: `E2E KTK ${RUN} Burger`, sku: `E2E-KTK-${RUN}-BUR`, price: 1200, tax_category_key: 'restaurant.food' });
  const printer = await post<{ id: string }>(context, '/printing/printers', { name: PRINTER, kind: 'network', address: '10.0.0.62', usage: 'kitchen' }, 201);
  printerBefore = (await api<{ kitchen_printer_id: string | null }>(context, A, 'GET', '/printing/settings')).data.kitchen_printer_id;
  await post(context, '/printing/settings', { kitchen_printer: printer.id });
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/kitchen/tickets');
  await post(context, '/printing/settings', { kitchen_printer: printerBefore });
  await context.close();
  cleanUp();
});

test('KITCHEN-F21, F09: a ticket is moved from its row up to «Served», and «Reprint» queues its copy', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/tickets', { width: 1440, height: 900 });
  try {
    const sent = await sendRound(context, 1);
    await page.reload();
    const view = shown(page);
    await view.locator('[data-testid=kitchen-tickets-search] input').fill(`${CHECK} 1`);
    await expect(row(page, sent.number)).toContainText('To prepare');

    await rowAction(page, 'kitchen-tickets', sent.id, 'start');
    await expect(row(page, sent.number)).toContainText('Preparing');
    await rowAction(page, 'kitchen-tickets', sent.id, 'ready');
    await expect(row(page, sent.number)).toContainText('Ready');
    await capture(page, 'KITCHEN-F21', async () => {
      await expect(row(page, sent.number)).toBeVisible();
    });
    // Recall takes it back to the line; ready again, then served.
    await rowAction(page, 'kitchen-tickets', sent.id, 'recall');
    await expect(row(page, sent.number)).toContainText('Preparing');
    await rowAction(page, 'kitchen-tickets', sent.id, 'ready');
    await expect(row(page, sent.number)).toContainText('Ready');
    await rowAction(page, 'kitchen-tickets', sent.id, 'serve');
    await expect(row(page, sent.number)).toContainText('Served');
    expect(await statusOf(context, sent.id)).toBe('served');

    // kitchen#134: from a tablet upright to a laptop, table or cards, the number reads whole, never «20261021-00…»
    // on every row: its text fits every box that clips it, up to its row.
    for (const width of [820, 1024, 1112, 1280]) {
      await page.setViewportSize({ width, height: 834 });
      const number = row(page, sent.number).getByText(sent.number, { exact: true }).first();
      await expect(number, `${width}`).toBeVisible();
      const cut = await number.evaluate((el) => {
        const range = document.createRange();
        range.selectNodeContents(el);
        const text = range.getBoundingClientRect();
        if (el.scrollWidth > el.clientWidth + 1) return true;
        for (let box: Element | null = el; box && !box.matches('[data-testid=kitchen-tickets-row]'); box = box.parentElement) {
          const style = getComputedStyle(box);
          if (style.overflowX === 'visible' && style.textOverflow !== 'ellipsis') continue;
          const own = box.getBoundingClientRect();
          if (text.left < own.left - 1 || text.right > own.right + 1) return true;
        }
        return false;
      }, undefined, { timeout: 10_000 });
      expect(cut, `${width}: the number whole`).toBe(false);
    }
    await page.setViewportSize({ width: 1440, height: 900 });

    // F09: «⋮ → Reprint» queues a copy on the kitchen's printer and says so.
    await rowAction(page, 'kitchen-tickets', sent.id, 'reprint');
    await expect(view.locator('[data-testid=kitchen-tickets-reprinted]')).toContainText(sent.number);
    await capture(page, 'KITCHEN-F09', async () => {
      await expect(view.locator('[data-testid=kitchen-tickets-reprinted]')).toBeVisible();
    });
    const jobs = await api<{ rows: { reference: string; job_key: string }[] }>(context, A, 'GET', `/printing/jobs?search=${encodeURIComponent(sent.number)}`);
    expect(jobs.data.rows.filter((job) => job.reference === sent.number).map((job) => job.job_key).sort()).toEqual([
      expect.stringMatching(/-copy-1-/),
      expect.stringMatching(/-order-/),
    ]);
  } finally {
    await context.close();
  }
});

test('KITCHEN-F22: «Cancel» asks first, says the check in the till does not change, and keeps the reason', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/tickets', { width: 1440, height: 900 });
  try {
    const sent = await sendRound(context, 2);
    await page.reload();
    const view = shown(page);
    await view.locator('[data-testid=kitchen-tickets-search] input').fill(`${CHECK} 2`);
    await expect(row(page, sent.number)).toContainText('To prepare');

    await rowAction(page, 'kitchen-tickets', sent.id, 'cancel');
    const dialog = page.locator('ion-modal[data-testid=kitchen-tickets-cancel]');
    await expect(dialog).toContainText(`Cancel ticket ${sent.number}?`);
    // kitchen#166: what cancelling does and does not do, before doing it.
    await expect(dialog).toContainText('The check in the till does not change: its dishes stay on it.');
    await dialog.locator('[data-testid=kitchen-tickets-cancel-reason] input').fill('Guest left');
    await capture(page, 'KITCHEN-F22', async () => {
      await expect(dialog.locator('[data-testid=kitchen-tickets-cancel-submit]')).toBeInViewport();
    });
    await dialog.locator('[data-testid=kitchen-tickets-cancel-submit]').click();
    await expect(dialog).toBeHidden();
    await expect(row(page, sent.number)).toContainText('Cancelled');
    expect(await statusOf(context, sent.id)).toBe('cancelled');
    const history = await api<{ rows: { action: string; notes: string }[] }>(context, A, 'GET', `/kitchen/log?ticket_id=${sent.id}`);
    expect(history.data.rows.map((entry) => [entry.action, entry.notes])).toContainEqual(['cancelled', 'Guest left']);
  } finally {
    await context.close();
  }
});

test('KITCHEN-F23: «New ticket» from page 2 makes one by hand and the list comes back to page 1 to show it', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/tickets', { width: 1440, height: 900 });
  try {
    // More than a page of tickets of this run (25 a page), so there is a page 2.
    for (let n = 0; n < 26; n += 1) await post(context, '/kitchen/tickets', { label: `${CHECK} fill ${n}`, items: [{ name: 'Water' }] }, 201);
    await page.reload();
    const view = shown(page);
    await view.locator('[data-testid=kitchen-tickets-search] input').fill(CHECK);
    await expect(row(page, `${CHECK} fill 25`)).toBeVisible();
    await view.locator('.data-table__page-size-select').click();
    await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: /^\s*25\s*$/ }).click();
    await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
    await view.locator('[data-testid=kitchen-tickets-page-next]').click();
    await expect(row(page, `${CHECK} fill 0`)).toBeVisible();

    await view.locator('[data-testid=kitchen-tickets-primary-action]').click();
    const form = page.locator('ion-modal[data-testid=kitchen-ticket-form]');
    await expect(form).toBeVisible();
    await form.locator('[data-testid=kitchen-ticket-form-label] input').fill(`${CHECK} by hand`);
    await form.locator('[data-testid=kitchen-ticket-form-dish-0-name] input').fill('Salad');
    await capture(page, 'KITCHEN-F23', async () => {
      await expect(form.locator('[data-testid=kitchen-ticket-form-submit]')).toBeInViewport();
    });
    await form.locator('[data-testid=kitchen-ticket-form-submit]').click();
    await expect(form).toBeHidden();
    // kitchen#133: the new one is seen, newest first, on page 1.
    await expect(row(page, `${CHECK} by hand`)).toContainText('To prepare');
    await expect(row(page, `${CHECK} fill 0`)).toHaveCount(0);
  } finally {
    await context.close();
  }
});
