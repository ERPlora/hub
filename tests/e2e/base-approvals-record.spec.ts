// flow: BASE-F85
// Employees › Approvals also keeps what somebody did by themselves because their role lets them (Toast, Lightspeed and
// Shopify list every void with who did it, and who approved it only when somebody had to). The owner adds a line to an
// item of Demo and voids a sale, which a manager would have to approve for a cashier: each one is a row with their name,
// «Their role» and nobody who approved it, with its figures when its app says them. It is searched, filtered by «With»
// and exported, and the record already on screen gets the void without a reload. In Spanish, in the three sizes.
// Everything this file creates goes with it (`afterAll`).
import { readFileSync } from 'node:fs';

import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { createItem } from './demo-items';
import { A, api, capture, OWNER, psql, saveSessionForTheSweep, shown, signedInSpanish, testid, THREE_SIZES, usernamesOf } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';
import { clearFilters, filterBy } from './service-helpers';

const KEY = 'base-approvals-record';
const SKU = `E2E-REC-${stamp()}`;
const LINE_TEXT = `Café solo ${stamp()}`;
const SAID = `Añadir una línea: 2,5 × ${LINE_TEXT}`;

test.describe.configure({ mode: 'serial' });

let context: BrowserContext;
let page: Page;
let started = '';
let itemId = '';

const rows = () => shown(page).locator('[data-testid="approvals-row"], [data-testid="approvals-card"]');

/** The record just opened: a goto to the same address with a hash would keep what was searched and filtered. */
async function open(): Promise<void> {
  await page.goto(`${A}/employees#approvals`);
  await page.reload();
  await expect(testid(page, 'approvals-search')).toBeVisible();
}

async function searchFor(words: string): Promise<void> {
  await testid(page, 'approvals-search').locator('input').fill(words);
}

async function exported(): Promise<string> {
  const [download] = await Promise.all([page.waitForEvent('download'), testid(page, 'approvals-export').click()]);
  expect(download.suggestedFilename()).toBe('approvals.csv');
  return readFileSync(await download.path(), 'utf8');
}

test.beforeAll(async ({ browser }) => {
  started = psql('SELECT now()::text');
  snapshotSeries();
  ({ context, page } = await signedInSpanish(browser, THREE_SIZES[2], '/employees'));
  await drawerOff(context);
  await createProduct(context, { name: 'E2E Approvals record', sku: SKU, price: 450, tax_category_key: 'product.generic' });
  itemId = (await createItem(context, A, `E2E approvals record ${stamp()}`)).id;
  const added = await api(context, A, 'POST', '/demo/items/add_line', { id: itemId, text: LINE_TEXT, qty: '2.5' });
  expect(added.status, JSON.stringify(added.data)).toBe(200);
});

test.afterAll(async () => {
  if (context) {
    if (itemId) await api(context, A, 'POST', '/demo/items/delete', { id: itemId });
    await saveSessionForTheSweep(context);
    await context.close();
  }
  if (started) psql(`DELETE FROM base_approval WHERE way = 'role' AND requested_by IN (${usernamesOf(OWNER.email)}) AND created_at >= '${started}'`);
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

test('BASE-F85: what the owner did by their role is a row with their name, its figures and nobody who approved it', async () => {
  for (const size of THREE_SIZES) {
    await page.setViewportSize(size);
    await open();
    await searchFor(LINE_TEXT);
    await expect(rows()).toHaveCount(1);
    await expect(rows()).toContainText(SAID);
    await expect(rows().getByTestId('approvals-way')).toHaveText('Su rol');
    await expect(rows().getByTestId('approvals-used')).toHaveText('Hecha');
    // Its last column is whole in sight, on a tablet held upright too.
    await expect(rows().getByTestId('approvals-used')).toBeInViewport({ ratio: 1 });
    await capture(page, `${KEY}-row-${size.label}`);
    await searchFor('');
    await expect(rows().first()).toBeVisible();
    await capture(page, `${KEY}-all-${size.label}`);
  }
});

test('BASE-F85: it is filtered by «With» and exported as it is seen', async () => {
  await page.setViewportSize(THREE_SIZES[2]);
  await open();
  await searchFor(LINE_TEXT);
  await filterBy(page, 'approvals', 'way', 'PIN');
  await expect(rows()).toHaveCount(0);
  await clearFilters(page, 'approvals');
  await filterBy(page, 'approvals', 'way', 'Su rol');
  await expect(rows()).toHaveCount(1);
  await capture(page, `${KEY}-filtered`);

  const [header, line, end] = (await exported()).split('\r\n');
  expect(header).toBe('\ufeffCuándo,Acción,Autorizado por,Quién,Con,Estado');
  expect(line).toMatch(/^\d{4}-\d\d-\d\d \d\d:\d\d,/);
  expect(line).toContain(LINE_TEXT);
  expect(line).toMatch(/,,[^,]+,Su rol,Hecha$/);
  expect(end).toBe('');
});

test('BASE-F85: a void the owner does elsewhere comes to the record on screen without a reload', async () => {
  await open();
  await searchFor('Anular una venta');
  const before = Number(psql("SELECT count(*) FROM base_approval WHERE operation = 'sale.sale.void'"));
  await expect(rows()).toHaveCount(before);
  const sale = await chargeByApi(context, { lines: [{ product: SKU }], payments: [{ method: 'card' }] });
  const voided = await api(context, A, 'POST', '/sale/sales/void', { sale_id: sale.id, reason: 'e2e wrong table' });
  expect(voided.status, JSON.stringify(voided.data)).toBe(200);

  await expect(rows()).toHaveCount(before + 1);
  await expect(rows().first()).toContainText('Anular una venta');
  await expect(rows().first().getByTestId('approvals-way')).toHaveText('Su rol');
});
