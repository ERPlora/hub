// Inventory's flows that had no screen test yet, in Chrome against the real Taxes, Sales and Printing apps
// (apps/inventory/WORKBOOK.md), each with its screenshots `APP-INVENTORY-<flow>-<390|834|1440>`:
//   - INVENTORY-F02: «Edit» opens «Editing product — <name>» with the SKU locked; the row shows the change;
//   - INVENTORY-F03: the Status switch deactivates the product;
//   - INVENTORY-F04: «Delete» says what goes and what stays; its movements stay in Movements;
//   - INVENTORY-F08: a category picked in the form groups the product (the category counts it);
//   - INVENTORY-F16: a sale charged by Sales and handed to Inventory as the relay does reads, and is found, by
//     its number in Movements, with the time of day on a tablet;
//   - INVENTORY-F19: the settings save and say so;
//   - INVENTORY-F20: an article set to «catalog only» shows «—» as its stock;
//   - INVENTORY-F25: the sheet shows the SKU's barcode; «Print barcode» queues one label per press and says
//     where it goes (no «Label» printer yet, then one; the ones the database already has are switched off
//     for it, so it never skips);
//   - INVENTORY-F26: a quantity off the unit's step is refused under its field; by the kilo, grams are fine;
//   - on a phone (pm#478, inventory#105): a refused save is said where it can be read and «Save» is reachable.
import { execFileSync } from 'node:child_process';

import { type BrowserContext, expect, test } from '@playwright/test';

import { A, api, HUB_DIR, login, psql, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  dialog,
  fill,
  pick,
  pickCombo,
  productBySku,
  productRow,
  productsReady,
  rowAction,
  searchProducts,
  shootFlow,
  stamp,
} from './inventory-helpers';
import { chargeByApi, cleanSales } from './sale-helpers';

const printers: string[] = [];

test.afterAll(() => {
  psql(`delete from inventory_salestock where sale_id in (select id from sale_sale where order_id in (select distinct order_id from sale_orderline where sku like 'E2E-%'))`);
  cleanSales();
  psql(`delete from printing_printjob where source_app = 'inventory' and reference like 'E2E-%'`);
  for (const id of printers) psql(`delete from printing_printjob where printer_id = '${id}'; delete from printing_printer where id = '${id}'`);
  cleanInventory();
});

const RELAY = `
import os
from django.db import transaction
from live.models import OutboxEvent
from base import relay
event = OutboxEvent.objects.get(pk=os.environ["INVENTORY_EVENT"])
with transaction.atomic():
    relay.deliver("inventory", event)
`;

/** The worker's part: the newest `sale.sale.completed` of `saleId`, handed to Inventory as the outbox relay does. */
function relayToInventory(saleId: string): void {
  const event = psql(
    `select id from live_outboxevent where name = 'sale.sale.completed' and payload->>'sale_id' = '${saleId}' order by created_at desc, id desc limit 1`,
  );
  expect(event, `sale.sale.completed of ${saleId} in the outbox`).not.toBe('');
  execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '--hub', 'a', '-c', RELAY], {
    cwd: HUB_DIR,
    encoding: 'utf8',
    env: { ...process.env, INVENTORY_EVENT: event },
  });
}

test('INVENTORY-F02: «Edit» opens the product with its SKU locked and the row shows the new price', async ({ page, context }) => {
  // flow: INVENTORY-F02
  const sku = `E2E-EDIT-${stamp()}`;
  await login(page, A, '/inventory/products');
  const tea = await createProduct(context, { name: 'E2E Green tea', sku, price: 250 });
  await productsReady(page);
  await searchProducts(page, sku);
  await expect(productRow(page, sku)).toBeVisible();
  // inventory#108: the row's stock actions are buttons with their names, not bare icons.
  await expect(productRow(page, sku).getByRole('button', { name: /^(Receive stock|Recibir stock)$/ })).toBeVisible();
  await expect(productRow(page, sku).getByRole('button', { name: /^(Count stock|Contar stock)$/ })).toBeVisible();

  await rowAction(page, tea.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  await expect(form).toContainText(/(Editing product|Editando producto) — E2E Green tea/);
  await expect(form.locator('[data-testid=inventory-product-sku] input')).toBeDisabled();
  await fill(form, 'inventory-product-price', '3,10');
  await shootFlow(page, 'INVENTORY-F02');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(productRow(page, sku)).toContainText(/3[.,]10/);
  expect((await productBySku(context, sku)).sku).toBe(sku);
});

test('INVENTORY-F03 / INVENTORY-F20: the switch deactivates; an article set to «catalog only» shows «—» as its stock', async ({ page, context }) => {
  // flow: INVENTORY-F03, INVENTORY-F20
  const sku = `E2E-SWITCH-${stamp()}`;
  await login(page, A, '/inventory/products');
  const salt = await createProduct(context, { name: 'E2E Salt', sku, initial_stock: '4' });
  await productsReady(page);
  await searchProducts(page, sku);
  const row = productRow(page, sku);
  await expect(row.locator('[data-testid=inventory-product-stock]')).toHaveText('4');

  await row.locator(`[data-testid=inventory-products-active-${salt.id}]`).click();
  await expect.poll(async () => (await productBySku(context, sku)).is_active).toBe(false);
  await shootFlow(page, 'INVENTORY-F03');

  await rowAction(page, salt.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  const track = form.locator('[data-testid=inventory-product-track-stock]');
  await expect(form.locator('[data-testid=inventory-product-track-note]')).toHaveText(/(Following the hub setting|Sigue el ajuste del hub)/);
  await track.click();
  await expect(form.locator('[data-testid=inventory-product-track-note]')).toHaveText(/(Catalog only|Solo catálogo)/);
  await shootFlow(page, 'INVENTORY-F20');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();
  await expect(row.locator('[data-testid=inventory-product-stock]')).toHaveText('—');
});

test('INVENTORY-F04: «Delete» says what goes and what stays; the product leaves the list and its movements stay', async ({ page, context }) => {
  // flow: INVENTORY-F04
  const sku = `E2E-GONE-${stamp()}`;
  await login(page, A, '/inventory/products');
  const gone = await createProduct(context, { name: 'E2E Old soap', sku, initial_stock: '2' });
  await productsReady(page);
  await searchProducts(page, sku);
  await expect(productRow(page, sku)).toBeVisible();

  await rowAction(page, gone.id, 'delete');
  const confirm = page.locator('ion-modal.ep-form-modal').filter({ hasText: /Delete product|Eliminar producto/ });
  await expect(confirm).toContainText(`E2E Old soap (${sku})`);
  await shootFlow(page, 'INVENTORY-F04');
  await confirm.locator('.ep-form-modal__submit').click();
  await expect(confirm).toBeHidden();
  await expect(productRow(page, sku)).toHaveCount(0);

  await page.goto(`${A}/inventory/movements`);
  await shown(page).locator('[data-testid=inventory-movements-search] input').fill(sku);
  await expect(shown(page).locator('[data-testid=inventory-movements-row]')).toHaveCount(1);
  await expect(shown(page).locator('[data-testid=inventory-movements-row]')).toContainText('E2E Old soap');
});

test('INVENTORY-F08: a category picked in the form groups the product, and the category counts it', async ({ page, context }) => {
  // flow: INVENTORY-F08
  const sku = `E2E-CAT-${stamp()}`;
  const category = `E2E Teas ${stamp()}`;
  await login(page, A, '/inventory/products');
  expect((await api(context, A, 'POST', '/inventory/categories', { name: category })).status).toBe(201);
  const mint = await createProduct(context, { name: 'E2E Mint tea', sku });
  await productsReady(page);
  await searchProducts(page, sku);

  await rowAction(page, mint.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  await pickCombo(page, form.locator('[data-testid=inventory-product-categories]'), category, category);
  await expect(form.locator('[data-testid^=inventory-product-categories-chip-]')).toHaveText([category]);
  await shootFlow(page, 'INVENTORY-F08');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();

  await page.goto(`${A}/inventory/categories`);
  await shown(page).locator('[data-testid=inventory-categories-search] input').fill(category);
  const row = shown(page).locator('[data-testid=inventory-categories-row]', { hasText: category });
  await expect(row).toBeVisible();
  // The slug ends the row's text before the count: «…e2e-teas-<stamp>» then «1».
  await expect(row).toContainText(new RegExp(`${category.toLowerCase().replace(/ /g, '-')}\\s*1$`));
});

test('INVENTORY-F16: a sale reads, and is found, by its number in Movements, with its time on a tablet', async ({ page, context }) => {
  // flow: INVENTORY-F16, INVENTORY-F21
  const sku = `E2E-SOLD-${stamp()}`;
  await login(page, A, '/inventory/movements');
  await createProduct(context, { name: 'E2E Sold shampoo', sku, initial_stock: '6' });
  const sale = await chargeByApi(context, { lines: [{ product: sku, quantity: '2' }], payments: [{ method: 'card' }] });
  relayToInventory(sale.id);
  expect((await productBySku(context, sku)).stock).toBe('4.000');
  const number = sale.invoice_number || sale.number;

  await shown(page).locator('[data-testid=inventory-movements-search] input').fill(number);
  const rows = shown(page).locator('[data-testid=inventory-movements-row]');
  await expect(rows).toHaveCount(1);
  await expect(rows.first().locator('[data-testid=inventory-movement-type]')).toHaveText(/^(Sale|Venta)$/);
  await expect(rows.first()).toContainText(number);
  await expect(rows.first()).not.toContainText(sale.id);
  await shootFlow(page, 'INVENTORY-F16');
  // inventory#130, inventory#139, inventory#144: on a tablet the date keeps its time of day and the ticket number
  // is whole: neither cell is cut (what is in the page is also what can be read).
  await page.setViewportSize({ width: 834, height: 1112 });
  const cut = async (text: string | RegExp) =>
    rows
      .first()
      .locator('.data-table__text', { hasText: text })
      .first()
      .evaluate((cell) => cell.scrollWidth > cell.clientWidth + 1);
  await expect.poll(() => cut(/\d{1,2}:\d{2}/)).toBe(false);
  await expect.poll(() => cut(number)).toBe(false);
});

test('INVENTORY-F19: the settings save and say so', async ({ page, context }) => {
  // flow: INVENTORY-F19
  await login(page, A, '/inventory/settings');
  const before = await api<{ low_stock_threshold: number }>(context, A, 'GET', '/inventory/config');
  expect(before.status).toBe(200);
  try {
    const threshold = shown(page).locator('[data-testid=inventory-settings-threshold] input');
    await expect(threshold).toBeVisible();
    await threshold.fill('7');
    await threshold.blur();
    // hub#2224: on a phone the threshold keeps a field's width, never one letter per line.
    await page.setViewportSize({ width: 390, height: 844 });
    expect((await threshold.boundingBox())!.width).toBeGreaterThan(200);
    await shootFlow(page, 'INVENTORY-F19');
    await shown(page).locator('[data-testid=inventory-settings-save]').click();
    await expect(page.locator('ion-toast')).toContainText(/Settings saved\.|Ajustes guardados\./);
    const after = await api<{ low_stock_threshold: number }>(context, A, 'GET', '/inventory/config');
    expect(after.data.low_stock_threshold).toBe(7);
  } finally {
    await api(context, A, 'POST', '/inventory/config', { low_stock_threshold: before.data.low_stock_threshold });
  }
});

/**
 * INVENTORY-F25 starts where no printer takes a label, whatever the database already holds (a run cut short
 * leaves its «Label» printer behind): the active «Label» printers, and the one Printing's settings pick for
 * labels, are switched off through Printing. The function returned switches them back on straight in the
 * database, so it still works in a `finally` after the test's time ran out and its browser context closed.
 */
async function switchOffLabelPrinters(context: BrowserContext): Promise<() => void> {
  const active = await api<{ rows: { id: string; usage: string }[]; total: number }>(
    context,
    A,
    'GET',
    '/printing/printers?is_active=true&limit=100',
  );
  expect(active.status).toBe(200);
  expect(active.data.total, 'every active printer fits in one page').toBe(active.data.rows.length);
  const settings = await api<{ label_printer_id: string | null }>(context, A, 'GET', '/printing/settings');
  expect(settings.status).toBe(200);
  const labels = active.data.rows
    .filter((printer) => printer.usage === 'label' || printer.id === settings.data.label_printer_id)
    .map((printer) => printer.id);
  // All of them were on: switching every one back on is right even when only some went off.
  const switchBackOn = () => {
    if (labels.length) psql(`update printing_printer set is_active = true where id in ('${labels.join("','")}')`);
  };
  try {
    for (const id of labels) {
      const res = await api(context, A, 'POST', '/printing/printers/update', { printer_id: id, is_active: false });
      expect(res.status, `printer ${id} switched off`).toBe(200);
    }
  } catch (error) {
    // The test's `finally` is not armed yet: the ones already off go back on here.
    switchBackOn();
    throw error;
  }
  return switchBackOn;
}

test('INVENTORY-F25: the sheet shows the barcode and each press queues one label, said where it goes', async ({ page, context }) => {
  // flow: INVENTORY-F25
  const sku = `E2E-LABEL-${stamp()}`;
  await login(page, A, '/inventory/products');
  const switchBackOn = await switchOffLabelPrinters(context);
  try {
    expect(psql(`select count(*) from printing_printer where usage = 'label' and is_active`)).toBe('0');
    const wax = await createProduct(context, { name: 'E2E Hair wax', sku, price: 1210 });
    await productsReady(page);
    await searchProducts(page, sku);
    await rowAction(page, wax.id, 'detail');
    const sheet = dialog(page, 'inventory-product-detail');
    await expect(sheet.locator('[data-testid=inventory-barcode] svg')).toHaveAttribute('aria-label', new RegExp(sku));
    await expect(sheet.locator('[data-testid=inventory-barcode-text]')).toHaveText(sku);

    // No printer has the «Label» function yet: the label waits in the queue and the sheet says what to do.
    await sheet.locator('[data-testid=inventory-product-detail-print-label]').click();
    await expect(sheet.locator('[data-testid=inventory-product-detail-label]')).toContainText(/(waiting in the print queue|espera en la cola)/);
    const created = await api<{ id: string }>(context, A, 'POST', '/printing/printers', {
      name: `E2E Labels ${stamp()}`,
      kind: 'network',
      address: '192.168.1.250',
      usage: 'label',
    });
    expect(created.status).toBe(201);
    printers.push(created.data.id);
    await sheet.locator('[data-testid=inventory-product-detail-print-label]').click();
    await expect(sheet.locator('[data-testid=inventory-product-detail-label]')).toContainText(/E2E Labels/);
    await shootFlow(page, 'INVENTORY-F25');
    expect(psql(`select count(*) from printing_printjob where document_type = 'barcode_label' and reference = '${sku}'`)).toBe('2');
    expect(psql(`select document->>'price' from printing_printjob where reference = '${sku}' order by created_at desc limit 1`)).toBe('12.1');
  } finally {
    switchBackOn();
  }
});

test('INVENTORY-F26: a quantity off its unit\'s step is refused under its field; grams fit the kilo', async ({ page }) => {
  // flow: INVENTORY-F26
  const sku = `E2E-KG-${stamp()}`;
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await fill(form, 'inventory-product-name', 'E2E Flour by weight');
  await fill(form, 'inventory-product-sku', sku);
  await fill(form, 'inventory-product-price', '1,20');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
  await fill(form, 'inventory-product-initial-stock', '1,5');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form.locator('[data-testid=inventory-product-initial-stock]')).toContainText(/(step allowed for this unit|incremento permitido)/);
  await shootFlow(page, 'INVENTORY-F26');

  await pick(page, form.locator('[data-testid=inventory-product-unit]'), /(Kilogram|Kilogramo)/);
  await fill(form, 'inventory-product-initial-stock', '1,532');
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();
  await searchProducts(page, sku);
  await expect(productRow(page, sku).locator('[data-testid=inventory-product-stock]')).toHaveText(/1[.,]532/);
});

test('on a phone a refused save is said where it can be read, and «Save» is never under the tabbar', async ({ page, context }) => {
  // flow: INVENTORY-F01 (pm#478, pm#513, inventory#105)
  const sku = `E2E-PHONE-${stamp()}`;
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, A, '/inventory/products');
  await createProduct(context, { name: 'E2E Taken on phone', sku });
  await productsReady(page);
  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await fill(form, 'inventory-product-name', 'E2E Another');
  await fill(form, 'inventory-product-sku', sku);
  await fill(form, 'inventory-product-price', '1');
  await pickCombo(page, form.locator('[data-testid=inventory-product-tax]'), 'generic', /(Product — generic|Producto — general).*21/);
  const save = form.locator('[data-testid=inventory-product-form-submit]');
  await save.scrollIntoViewIfNeeded();
  await expect(save).toBeInViewport();
  await save.click();
  const refusal = form.locator('[data-testid=inventory-product-sku]');
  await expect(refusal).toContainText(/(That SKU already exists|Ese SKU ya existe)/);
  await refusal.scrollIntoViewIfNeeded();
  await expect(refusal).toBeInViewport();
  await shootFlow(page, 'INVENTORY-F01-refused', { width: 390, height: 844 });
});
