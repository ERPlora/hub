// Printing → Queue and Settings in Chrome (PRINTING-F01, F06, F12, F14, F15, F18; apps/printing/WORKBOOK.md): a job
// the device could not print fails after five hand-outs (the device's side by the API: claim and fail), the
// owner sends it back to the queue and then cancels it with a reason; the owner sets the ticket settings and
// the kitchen's printer, and follows the note to the receipt's texts in Sales; the employee reads them blocked.
// The barcode label asked from Inventory's product sheet waits in the «Label» card, which says it has no printer,
// until a label printer is added and its device takes it (PRINTING-F12, INVENTORY-F25).
// Screenshots of both pages, and of each flow, in the three viewports. What is made here is deleted, and the
// settings put back, after it.
// FIX-HUB-E2E-PRINTING-QUEUE-CLAIM-LEAKS-ACROSS-RUNS: on a database other runs used, the job goes to this run's
// printer by its id (a kitchen printer the settings still name, left by a run cut short, took it), the claims get
// past the older jobs waiting for any kitchen printer, each test finds or makes this run's kitchen printer (a
// failure restarts the worker with a new `RUN`), and the cleanup also runs before, so a run whose `afterAll` never
// ran leaves the next one clean.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shot, shown } from './helpers';
import { createProduct, dialog, fill, pick, productsReady, rowAction as productAction, searchProducts } from './inventory-helpers';
import { claim, fail, FLOW_VIEWPORTS, flowShots, forgetDevices } from './printing-helpers';
import { shots, stamp } from './sale-helpers';

const RUN = stamp();
const KITCHEN = `e2e Kitchen ${RUN}`;
const REF = `e2e-T-${RUN}`;
/** The device the API plays (PRINTING-F18): the owner's first claim from it sets it up. */
const DEVICE = `e2e queue device ${RUN}`;
/** The product whose label Inventory asks for (PRINTING-F12): a SKU a barcode carries. */
const LABEL_SKU = `E2E-F12-${RUN}`;
let before: Record<string, unknown> | undefined;
/** The label printers PRINTING-F12 switched off, switched back on after it. */
let switchedOff: string[] = [];

interface Job {
  id: string;
  status: string;
  attempts: number;
  cancelled_by: string;
  cancel_reason: string;
}

/**
 * Deletes what this file makes, also what a run of it cut short left (its labels by their SKU's prefix), and puts
 * the settings back when this run read them. Before and after the file.
 */
function cleanUp(): void {
  switchLabelPrintersBackOn();
  psql(`delete from printing_printjob where source_app = 'inventory' and reference like 'E2E-F12-%'`);
  psql(`delete from inventory_stockmovement where product_id in (select id from inventory_product where sku like 'E2E-F12-%')`);
  psql(`delete from inventory_product where sku like 'E2E-F12-%'`);
  psql(`delete from printing_printjob where reference like 'e2e%' or printer_id in (select id from printing_printer where name like 'e2e %')`);
  if (before && before.updated_at === null) psql('delete from printing_settings');
  else if (before) {
    psql(
      `update printing_settings set open_drawer_on_sale = ${before.open_drawer_on_sale ? 'true' : 'false'}, ` +
        `kitchen_printer_id = ${before.kitchen_printer_id ? `'${String(before.kitchen_printer_id)}'` : 'null'}`,
    );
  }
  for (const column of ['receipt_printer_id', 'kitchen_printer_id', 'bar_printer_id', 'label_printer_id']) {
    psql(`update printing_settings set ${column} = null where ${column} in (select id from printing_printer where name like 'e2e %')`);
  }
  forgetDevices('e2e %', { ids: [DEVICE] });
  psql(`delete from printing_printer where name like 'e2e %'`);
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

/**
 * This run's kitchen printer (PRINTING-F06, F18), made by the first test that asks for it: each test stands on its
 * own, also after a failure restarts the worker (a new `RUN`, so a new printer).
 */
async function kitchenPrinter(context: BrowserContext): Promise<string> {
  const found = await api<{ rows: { id: string; name: string }[] }>(context, A, 'GET', `/printing/printers?search=${encodeURIComponent(KITCHEN)}`);
  expect(found.status).toBe(200);
  const mine = found.data.rows.find((printer) => printer.name === KITCHEN);
  if (mine) return mine.id;
  const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
    name: KITCHEN,
    kind: 'network',
    address: '10.0.0.77',
    usage: 'kitchen',
  });
  expect(created.status).toBe(201);
  return created.data.id;
}

/**
 * Claims for `printerId`, as the queue's device, until the job `jobId` comes out, and returns the last one that did.
 * The oldest job goes first (PRINTING-F18): one another run or another spec left waiting for any printer of the
 * same function comes out before this run's. Each one taken stays sent to this run's printer, and goes with it.
 */
async function claimUntil(context: BrowserContext, printerId: string, jobId: string): Promise<{ id: string; attempts: number } | null> {
  const waiting = Number(psql(`select count(*) from printing_printjob where status = 'pending'`));
  let taken: { id: string; attempts: number } | null = null;
  for (let turn = 0; turn < waiting && taken?.id !== jobId; turn += 1) taken = await claim(context, printerId, DEVICE);
  return taken;
}

async function jobsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-jobs-row], [data-testid=printing-jobs-empty]').first().waitFor({ state: 'visible' });
}

async function settingsReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=printing-settings-heading]').waitFor({ state: 'visible' });
}

/**
 * Switches off, by the API, every active label printer and the one the settings choose for labels, so a label
 * waits with no printer whatever the database already has. Each one is noted before its call: a failure halfway
 * still switches the earlier ones back on.
 */
async function switchOffLabelPrinters(context: BrowserContext): Promise<void> {
  const active = await api<{ rows: { id: string; usage: string }[]; total: number }>(context, A, 'GET', '/printing/printers?is_active=true&limit=100');
  expect(active.status).toBe(200);
  expect(active.data.total, 'every active printer fits in one page').toBe(active.data.rows.length);
  const settings = await api<{ label_printer_id: string | null }>(context, A, 'GET', '/printing/settings');
  expect(settings.status).toBe(200);
  for (const printer of active.data.rows.filter((p) => p.usage === 'label' || p.id === settings.data.label_printer_id)) {
    switchedOff.push(printer.id);
    const res = await api(context, A, 'POST', '/printing/printers/update', { printer_id: printer.id, is_active: false });
    expect(res.status, `printer ${printer.id} switched off`).toBe(200);
  }
}

/** Back on by the database, so it also runs after the test's time ran out and its browser context closed. */
function switchLabelPrintersBackOn(): void {
  if (switchedOff.length) psql(`update printing_printer set is_active = true where id in ('${switchedOff.join("','")}')`);
  switchedOff = [];
}

/** How far below the top edge of its card the card's title sits, in whole pixels. */
async function titleOffset(card: Locator): Promise<number> {
  const [box, title] = await Promise.all([card.boundingBox(), card.locator('header strong').boundingBox()]);
  if (!box || !title) throw new Error('the card and its title are not painted');
  return Math.round(title.y - box.y);
}

/** This task's screenshots (`FIX-PRINTING-F12-INVENTORY-ALREADY-ASKS-<390|834|1440>`), each once `ready` says the page is painted. */
async function taskShots(page: Page, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: shot(`FIX-PRINTING-F12-INVENTORY-ALREADY-ASKS-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

async function jobByRef(context: BrowserContext): Promise<Job> {
  const listed = await api<{ rows: Job[] }>(context, A, 'GET', `/printing/jobs?search=${encodeURIComponent(REF)}`);
  return listed.data.rows[0];
}

async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const hook = `printing-jobs-row-${id}-${action}`;
  const inline = shown(page).locator(`[data-testid=${hook}]`);
  if ((await inline.count()) > 0 && (await inline.first().isVisible())) {
    await inline.first().click();
    return;
  }
  await shown(page).locator(`[data-testid=printing-jobs-row-${id}-menu]`).first().click();
  await page.locator(`ion-popover [data-testid=${hook}]`).click();
}

test('PRINTING-F18, F14: a job that fails five times is sent back, then cancelled with its reason', async ({ page, context }) => {
  await login(page, A, '/printing/jobs');
  const kitchen = await kitchenPrinter(context);
  const queued = await api<{ job: { id: string } }>(context, A, 'POST', '/printing/jobs', {
    document_type: 'kitchen_order',
    document: { order_number: 7, table: '4', items: [{ name: 'Paella', quantity: 2 }] },
    source_ref: REF,
    job_key: `e2e-${RUN}`,
    printer: kitchen,
  });
  expect(queued.status).toBe(201);
  // The device's side (base's /ws/print, by the API): five hand-outs, five failures.
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const taken = await claimUntil(context, kitchen, queued.data.job.id);
    expect(taken?.id).toBe(queued.data.job.id);
    expect(taken?.attempts).toBe(attempt);
    if (taken) await fail(context, taken, 'printer unreachable', DEVICE);
  }
  expect((await jobByRef(context)).status).toBe('failed');

  await jobsReady(page);
  const row = shown(page).locator('[data-testid=printing-jobs-row]').filter({ hasText: REF });
  await expect(row).toContainText(/Failed|Fallido/);
  await expect(row).toContainText('printer unreachable');
  await shots(page, 'printing-queue', jobsReady);
  await flowShots(page, 'PRINTING-F18', async (p) => {
    await expect(shown(p).locator('[data-testid=printing-jobs-row]').filter({ hasText: REF })).toBeVisible();
  });

  await rowAction(page, queued.data.job.id, 'retry');
  await expect.poll(async () => (await jobByRef(context)).status).toBe('pending');
  await expect(row).toContainText(/Pending|Pendiente/);

  await rowAction(page, queued.data.job.id, 'cancel');
  const modal = dialog(page, 'printing-cancel-job');
  await expect(modal).toBeVisible();
  await fill(modal, 'printing-cancel-job-reason', 'e2e reason');
  await modal.locator('[data-testid=printing-cancel-job-submit]').click();
  await expect(modal).toBeHidden();
  await expect.poll(async () => (await jobByRef(context)).status).toBe('cancelled');
  expect((await jobByRef(context)).cancel_reason).toBe('e2e reason');
  await expect(row).toContainText(/Cancelled by|Cancelado por/);
  await flowShots(page, 'PRINTING-F14', async (p) => {
    await expect(shown(p).locator('[data-testid=printing-jobs-row]').filter({ hasText: REF })).toBeVisible();
  });
});

test('PRINTING-F06: the owner opens the drawer at checkout and chooses the kitchen’s printer', async ({ page, context }) => {
  await login(page, A, '/printing/settings');
  before = (await api<Record<string, unknown>>(context, A, 'GET', '/printing/settings')).data;
  const kitchen = await kitchenPrinter(context);
  await settingsReady(page);
  await shots(page, 'printing-settings', settingsReady);
  await shown(page).locator('[data-testid=printing-setting-open_drawer_on_sale]').click();
  await pick(page, shown(page).locator('[data-testid=printing-setting-kitchen_printer]'), KITCHEN);
  const save = shown(page).locator('[data-testid=printing-settings-save]');
  await expect(save).not.toHaveAttribute('aria-disabled', 'true');
  await save.click();
  await expect
    .poll(async () => (await api<{ open_drawer_on_sale: boolean; kitchen_printer_id: string | null }>(context, A, 'GET', '/printing/settings')).data)
    .toMatchObject({ open_drawer_on_sale: !before?.open_drawer_on_sale });
  expect((await api<{ kitchen_printer_id: string | null }>(context, A, 'GET', '/printing/settings')).data.kitchen_printer_id).toBe(kitchen);
  await flowShots(page, 'PRINTING-F06', settingsReady);
});

test('PRINTING-F15: the receipt’s texts are the till’s, and the note leads there', async ({ page }) => {
  await login(page, A, '/printing/settings');
  await settingsReady(page);
  await expect(shown(page).locator('[data-testid=printing-settings-receipt-text]')).toContainText(/till settings|ajustes de Ventas/);
  await flowShots(page, 'PRINTING-F15', async (p) => {
    await expect(shown(p).locator('[data-testid=printing-settings-receipt-link]')).toBeVisible();
  });
  await shown(page).locator('[data-testid=printing-settings-receipt-link]').click();
  await expect(page).toHaveURL(/\/sale\/settings$/);
  await expect(shown(page).locator('[data-testid=sale-settings-heading], [data-testid=sale-settings-form]').first()).toBeVisible();
});

test('PRINTING-F06: the employee reads the settings blocked', async ({ page }) => {
  await login(page, A, '/printing/settings', EMPLOYEE);
  await settingsReady(page);
  await expect(shown(page).locator('[data-testid=printing-settings-read-only]')).toBeVisible();
  await expect(shown(page).locator('[data-testid=printing-settings-save]')).toHaveCount(0);
  await expect(shown(page).locator('[data-testid=printing-setting-open_drawer_on_sale]')).toBeDisabled();
});

test('PRINTING-F12: the label asked from the product sheet waits in the «Label» card, which says so, until a label printer takes it', async ({
  page,
  context,
}) => {
  // flow: PRINTING-F12 (INVENTORY-F25 asks for it; printing#62: the warning of a label with no printer shows)
  await login(page, A, '/inventory/products');
  try {
    await switchOffLabelPrinters(context);
    const product = await createProduct(context, { name: `E2E Label ${RUN}`, sku: LABEL_SKU, price: 1210 });

    // Inventory: «Print barcode» on the product sheet asks Printing for the label; no printer has the «Label» function.
    await productsReady(page);
    await searchProducts(page, LABEL_SKU);
    await productAction(page, product.id, 'detail');
    const sheet = dialog(page, 'inventory-product-detail');
    await sheet.locator('[data-testid=inventory-product-detail-print-label]').click();
    await expect(sheet.locator('[data-testid=inventory-product-detail-label]')).toContainText(/(waiting in the print queue|espera en la cola)/);
    const mine = psql(
      `select id from printing_printjob where source_app = 'inventory' and reference = '${LABEL_SKU}' and usage = 'label' and status = 'pending' and printer_id is null`,
    );
    expect(mine, 'one label waiting with no printer').toMatch(/^[0-9a-f-]{36}$/);

    // Printing: the «Label» card of the print queue says the label waits with no printer.
    const till = await api(context, A, 'POST', '/printing/printers', {
      // Long enough for «Prints on» to take two lines: «Receipt» is the taller card of the row.
      name: `e2e Till ${RUN} by the front door`,
      kind: 'network',
      address: '192.168.1.252',
      usage: 'receipt',
    });
    expect(till.status).toBe(201);
    await page.goto(`${A}/printing/printers`);
    const card = shown(page).locator('[data-testid=printing-summary-card-label]');
    await expect(card).toContainText(/(Waiting, no printer|En cola, sin impresora)/);
    await expect(card).toContainText(/(Waiting|En cola): [1-9]/);
    // Side by side, each card starts at its top: the shorter «Label» is not spread to the height of «Receipt».
    await page.setViewportSize({ width: 1440, height: 900 });
    const receipt = shown(page).locator('[data-testid=printing-summary-card-receipt]');
    await expect(receipt.locator('[data-testid=printing-summary-prints-on-receipt]')).toBeVisible();
    expect(await titleOffset(card)).toBe(await titleOffset(receipt));
    await taskShots(page, async (p) => {
      await expect(shown(p).locator('[data-testid=printing-summary-card-label]')).toContainText(/(Waiting, no printer|En cola, sin impresora)/);
    });

    // A label printer arrives: the card turns ready and names it, and the device next to it takes the label.
    const labels = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
      name: `e2e Labels ${RUN}`,
      kind: 'network',
      address: '192.168.1.251',
      usage: 'label',
    });
    expect(labels.status).toBe(201);
    await expect(card).toContainText(/(Ready|Listo)/);
    await expect(card).toContainText(`e2e Labels ${RUN}`);
    // The oldest label goes first: one another run left waiting comes out before this one.
    expect((await claimUntil(context, labels.data.id, mine))?.id).toBe(mine);
    expect(psql(`select concat_ws(' ', document->>'product_name', document->>'barcode', document->>'price') from printing_printjob where id = '${mine}'`)).toBe(
      `E2E Label ${RUN} ${LABEL_SKU} 12.1`,
    );
  } finally {
    switchLabelPrintersBackOn();
  }
});
