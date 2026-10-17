// A status pill in a narrow table cell is never cut (FIX-UI-STATUSPILL-834): in Sales → Sales at 834×1112
// the «Document pending» pill under a sale's status came out «● Document pend», clipped by its Status cell.
// The pill (`@erplora/ui` StatusPill) is now never wider than its box, and its label wraps between words:
// the whole text is on screen at 390×844 (cards), 834×1112 and 1440×900 (list), and it is the pill's
// title. Setup as in sale-pending-document.spec.ts: no issuer while the run charges by card (its ticket
// waits), put back after; what the run creates is deleted after it.
// flow: ui:DataTable
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, psql, shot, shown } from './helpers';
import { issuerNow, type IssuerOut, snapshotSeries } from './invoice-helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { chargeByApi, cleanSales, type SaleOut, stamp } from './sale-helpers';
import { FLOW_VIEWPORTS } from './tax-helpers';

const RUN = stamp();
let coffee: Product;
/** The hub's issuer before the run (its address is blanked while the run needs «no issuer»). */
let original: IssuerOut | null = null;

const quoted = (text: string): string => `'${text.replace(/'/g, "''")}'`;

test.beforeAll(async ({ browser }) => {
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/sale/sales');
  original = await issuerNow(context);
  if (original.configured) psql("update invoice_issuer set address = ''");
  expect((await issuerNow(context)).configured).toBe(false);
  coffee = await createProduct(context, { name: `E2E Pill coffee ${RUN}`, sku: `E2E-PILL-${RUN}`, price: 150, tax_category_key: 'restaurant.drink' });
  await context.close();
});

test.afterAll(() => {
  try {
    cleanSales();
    cleanInventory();
  } finally {
    if (original?.configured) psql(`update invoice_issuer set address = ${quoted(original.address)}`);
  }
});

/**
 * What cuts the pill, measured in the page: its text must lie inside the pill and inside every box that
 * clips it up to its cell (or card field), and the pill inside that cell (it never spills into the next
 * column). Empty = the whole pill is on screen.
 */
function cuts(pill: Locator): Promise<string[]> {
  return pill.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const text = range.getBoundingClientRect();
    const pillBox = el.getBoundingClientRect();
    const name = (node: Element) => `${node.tagName.toLowerCase()}.${[...node.classList].join('.')}`;
    const outside = (inner: DOMRect, outer: DOMRect) =>
      inner.left < outer.left - 0.5 || inner.right > outer.right + 0.5 || inner.top < outer.top - 0.5 || inner.bottom > outer.bottom + 0.5;
    const found: string[] = [];
    const cell = el.closest('.data-table__cell, .data-table__field-value');
    if (!cell) return ['the pill is in no table cell or card field'];
    for (let node: Element | null = el; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      const clips = node === el || style.overflowX !== 'visible' || style.overflowY !== 'visible';
      const box = node.getBoundingClientRect();
      if (clips && outside(text, box)) found.push(`text ${Math.round(text.left)}–${Math.round(text.right)} cut by ${name(node)} ${Math.round(box.left)}–${Math.round(box.right)}`);
      if (node === cell) {
        if (outside(pillBox, box)) found.push(`pill ${Math.round(pillBox.left)}–${Math.round(pillBox.right)} spills out of ${name(node)} ${Math.round(box.left)}–${Math.round(box.right)}`);
        break;
      }
    }
    return found;
  });
}

async function findSale(page: Page, sale: SaleOut): Promise<Locator> {
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(sale.number);
  // The search applies after its debounce and a new read: until then the list still holds the other sales
  // of the day, with this one among them. Measured and captured once only this sale is left.
  await expect(shown(page).locator('[data-testid=sales-table-row]')).toHaveCount(1);
  const row = shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);
  await expect(row).toBeVisible();
  return row;
}

test('ui:DataTable — the «Document pending» pill of a sale is whole in its cell at 390, 834 and 1440', async ({ page, context }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/sales');
  const sale = (await chargeByApi(context, { lines: [{ product: coffee.sku }], payments: [{ method: 'card' }] })) as SaleOut & { documents_pending: boolean };
  expect(sale.documents_pending).toBe(true);

  for (const vp of [FLOW_VIEWPORTS[1], FLOW_VIEWPORTS[0], FLOW_VIEWPORTS[2]]) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/sale/sales');
    const row = await findSale(page, sale);
    const pill = row.locator('[data-testid=sales-documents-pending]');
    await expect(pill).toHaveText(/^\s*(Document pending|Documento pendiente)\s*$/);
    // A list repaints its rows when the box settles: measured until it stops moving.
    await expect.poll(() => cuts(pill), `pill at ${vp.label}`).toEqual([]);
    // The whole text, also on hover (it is the pill's title).
    await expect(pill).toHaveAttribute('title', /^(Document pending|Documento pendiente)$/);
    await page.screenshot({ path: shot(`FIX-UI-STATUSPILL-834-${vp.label}`) });
  }

  // A single word longer than the cell cannot wrap: it ends in «…» inside the pill, never past the cell.
  // A copy of the pill beside it (same styles) carries such a word; it is removed after the screenshot.
  await page.setViewportSize({ width: 834, height: 1112 });
  await page.goto('/sale/sales');
  const pill = (await findSale(page, sale)).locator('[data-testid=sales-documents-pending]');
  await expect.poll(() => cuts(pill), 'pill at 834 before the long word').toEqual([]);
  const long = await pill.evaluate((el) => {
    const copy = el.cloneNode(true) as HTMLElement;
    copy.setAttribute('data-testid', 'fix-ui-statuspill-long-word');
    const label = copy.querySelector('.status-pill__label') ?? copy;
    label.textContent = 'Dokumentenausstellungsverfahren';
    el.after(copy);
    const cell = el.closest('.data-table__cell')!.getBoundingClientRect();
    const box = copy.getBoundingClientRect();
    return {
      insideCell: box.left >= cell.left - 0.5 && box.right <= cell.right + 0.5,
      hidesTheRest: label.scrollWidth > label.clientWidth,
      ellipsis: getComputedStyle(label).textOverflow,
    };
  });
  expect(long).toEqual({ insideCell: true, hidesTheRest: true, ellipsis: 'ellipsis' });
  const row = shown(page).locator(`[data-testid=sales-table-row][data-id="${sale.id}"]`);
  await row.screenshot({ path: shot('FIX-UI-STATUSPILL-834-long-word') });
  await page.locator('[data-testid=fix-ui-statuspill-long-word]').evaluate((el) => el.remove());
});
