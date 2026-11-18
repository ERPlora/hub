// flow: PRINTING-F10, PRINTING-F11
// The kitchen order on paper in Chrome (apps/printing/WORKBOOK.md), with the real Sales, Inventory, Kitchen and
// Printing apps: a check opened in Sales with one dish, «Send order» through Kitchen (which asks Printing by
// name for its sheet), and its «Reprint» — the queue shows both kitchen orders on the kitchen's printer, the
// reprint a copy with its own job. Screenshots of the queue in the three viewports. What a run creates is
// named «e2e PrK <stamp>» (printer), `E2E-PRK…` (product) and «e2e prk <stamp>» (check); `afterAll` removes it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shown } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { flowShots } from './printing-helpers';
import { cleanSales, stamp } from './sale-helpers';

const STAMP = stamp();
const PRINTER = `e2e PrK ${STAMP} Grill`;
const CHECK = `e2e prk ${STAMP}`;

interface Job {
  id: string;
  usage: string;
  document_type: string;
  printer_id: string | null;
  source_app: string;
  reference: string;
  job_key: string;
}

/** The kitchen tickets of this run's checks, their paper and this run's printer; then the e2e checks and products. */
function cleanUp(): void {
  const orders = "select id from sale_order where label like 'e2e prk %'";
  const tickets = `select distinct ticket_id from kitchen_ticketitem where sale_line_id in (select id from sale_orderline where order_id in (${orders})) union select id from kitchen_ticket where label like 'e2e prk %'`;
  psql(
    [
      `create temp table e2e_prk_tickets as ${tickets}`,
      "delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (select ticket_id from e2e_prk_tickets))",
      "delete from printing_printjob where printer_id in (select id from printing_printer where name like 'e2e PrK %')",
      'delete from kitchen_logentry where ticket_id in (select ticket_id from e2e_prk_tickets)',
      'delete from kitchen_ticketitem where ticket_id in (select ticket_id from e2e_prk_tickets)',
      'delete from kitchen_ticket where id in (select ticket_id from e2e_prk_tickets)',
    ].join('; '),
  );
  for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
    psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e PrK %')`);
  }
  psql("delete from printing_printer where name like 'e2e PrK %'");
  cleanSales();
  cleanInventory();
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

async function jobsOf(context: BrowserContext, reference: string): Promise<Job[]> {
  const listed = await api<{ rows: Job[] }>(context, A, 'GET', `/printing/jobs?search=${encodeURIComponent(reference)}`);
  expect(listed.status, JSON.stringify(listed.data)).toBe(200);
  return listed.data.rows.filter((job) => job.reference === reference);
}

async function jobsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-jobs-row], [data-testid=printing-jobs-empty]').first().waitFor({ state: 'visible' });
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('PRINTING-F10, F11: the order sent from the till prints in the kitchen, and its reprint is a copy', async ({ page, context }) => {
  await login(page, A, '/printing/jobs');
  // Its own kitchen printer, the hub's default for the kitchen while the run lasts: the sheet goes there.
  const printer = await post<{ id: string }>(context, '/printing/printers', { name: PRINTER, kind: 'network', address: '10.0.0.61', usage: 'kitchen' }, 201);
  const settings = (await api<{ kitchen_printer_id: string | null }>(context, A, 'GET', '/printing/settings')).data;
  await post(context, '/printing/settings', { kitchen_printer: printer.id });
  try {
    const burger = await createProduct(context, { sku: `E2E-PRK${STAMP}B`, name: `E2E PrK ${STAMP} Burger` });
    const order = await post<{ id: string }>(context, '/sale/orders', { label: CHECK }, 201);
    await post(context, '/sale/orders/add_line', { order_id: order.id, product_id: burger.id, quantity: '1' });

    // «Send order»: Kitchen opens the round and asks Printing for its sheet, in the same transaction.
    const ticket = await post<{ id: string; number: string }>(context, '/kitchen/tickets/send', { order_id: order.id, label: 'Table 4' }, 201);
    await expect.poll(async () => (await jobsOf(context, ticket.number)).length).toBe(1);
    const [sheet] = await jobsOf(context, ticket.number);
    expect(sheet).toMatchObject({ usage: 'kitchen', document_type: 'kitchen_order', source_app: 'kitchen', printer_id: printer.id });

    // «Reprint»: another sheet of the same order, with its own key (never the first one again).
    await post(context, '/kitchen/tickets/reprint', { ticket_id: ticket.id });
    await expect.poll(async () => (await jobsOf(context, ticket.number)).length).toBe(2);
    const keys = new Set((await jobsOf(context, ticket.number)).map((job) => job.job_key));
    expect(keys.size).toBe(2);

    // The queue shows both, live, as kitchen orders of the kitchen's printer.
    await jobsReady(page);
    const rows = shown(page).locator('[data-testid=printing-jobs-row]').filter({ hasText: ticket.number });
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText(/Kitchen order|Comanda de cocina/);
    await expect(rows.first()).toContainText(PRINTER);
    // F10 (the order) and F11 (its copy) are the same two rows of the queue.
    for (const key of ['PRINTING-F10', 'PRINTING-F11']) {
      await flowShots(page, key, async (p) => {
        await expect(shown(p).locator('[data-testid=printing-jobs-row]').filter({ hasText: ticket.number }).first()).toBeVisible();
      });
    }
  } finally {
    await post(context, '/printing/settings', { kitchen_printer: settings.kitchen_printer_id });
  }
});
