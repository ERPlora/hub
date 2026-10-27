// flow: business-currency (FIX-HUB-SALE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY; apps/sale/WORKBOOK.md «Antes de empezar»)
// The till and the sales are in the business's currency: its country's, as erplora.com registered it
// (`PUT /internal/hubs/{id}`, signed the way the SaaS sends it), never a fixed euro. Hub `a` moves to Poland: the check,
// the charge with its change, the ticket and the sale in «Sales» are in złoty, in 390, 834 and 1440 (captures
// `FIX-HUB-SALE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY-<width>`). Back in Spain the till is in euros and the sale charged in
// Poland keeps its złoty (`…-es-1440`). What the run creates is deleted after it and `a`'s registration put back.
import { expect, type Page, test } from '@playwright/test';

import { A, login, registerBusinessIn, registrationOf, type Registration, shot, shown } from './helpers';
import { cleanInventory, createProduct, type Product } from './inventory-helpers';
import { snapshotSeries } from './invoice-helpers';
import { cleanSales, drawerOff, newestSaleOf, restoreDrawer, stamp } from './sale-helpers';

const KEY = 'FIX-HUB-SALE-CHARGES-IN-EUR-WHATEVER-THE-COUNTRY';
const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;
const RUN = stamp();
/** Złoty as a till in Poland writes them: «12,50 zł», «zł 12.50». */
const ZLOTY = /zł/;
const EURO = /€/;

/** `a`'s registration as the run found it (put back after). */
let original: Registration;
let shirt: Product;
/** The sale charged in Poland, which keeps its złoty. */
let polish = { id: '', number: '' };

test.describe.configure({ mode: 'serial' });
test.use({ actionTimeout: 30_000 });

test.beforeAll(async ({ browser }) => {
  original = registrationOf('a');
  // Card and cash charges issue tickets when the hub has an issuer: the cleanup gives their numbers back.
  snapshotSeries();
  const context = await browser.newContext({ baseURL: A });
  await login(await context.newPage(), A, '/sale/pos');
  // Cash without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  shirt = await createProduct(context, { name: `E2E Shirt ${RUN}`, sku: `E2E-CUR-S-${RUN}`, price: 1250, tax_category_key: 'product.generic' });
  await context.close();
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  cleanSales();
  cleanInventory();
  restoreDrawer();
});

async function tillReady(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid^=pos-product-], [data-testid=pos-grid-empty]').first().waitFor({ state: 'visible' });
}

/** Adds the shirt the way a person finds it: the magnifier, its SKU, the result. */
async function addShirt(page: Page): Promise<void> {
  await shown(page).locator('[data-testid=pos-search-trigger]').click();
  const search = page.locator('[data-testid=pos-search]');
  await search.locator('input').fill(shirt.sku);
  await search.locator(`[data-testid=pos-search-${shirt.id}]`).click();
}

/** The total of the check, on the cart's foot (behind the button on a phone). */
async function checkTotal(page: Page): Promise<string> {
  const fab = shown(page).locator('[data-testid=pos-cart-fab]');
  if (await fab.isVisible()) await fab.click();
  const total = shown(page).locator('[data-testid=pos-total]');
  await expect(total).toContainText(/12[.,]50/);
  return (await total.textContent()) ?? '';
}

/** Charges the check in cash with 50 handed over: the charge sheet's tendered and change, then the ticket. */
async function chargeInCash(page: Page, size: string): Promise<void> {
  await shown(page).locator('[data-testid=pos-charge]').click();
  const sheet = page.locator('[data-testid=sale-checkout-modal]');
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('[data-testid=sale-checkout-total]')).toContainText(ZLOTY);
  for (const key of ['5', '0']) await sheet.locator(`[data-testid=sale-checkout-keypad-${key}]`).click();
  await expect(sheet.locator('[data-testid=sale-checkout-tendered]')).toContainText(ZLOTY);
  await expect(sheet.locator('[data-testid=sale-checkout-change]')).toContainText(/37[.,]50/);
  await expect(sheet.locator('[data-testid=sale-checkout-change]')).toContainText(ZLOTY);
  await expect(sheet).not.toContainText(EURO);
  await page.screenshot({ path: shot(`${KEY}-${size}`) });
  await sheet.locator('[data-testid=sale-checkout-confirm]').click();
  await expect(sheet).toBeHidden();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt).toContainText(/12[.,]50/);
  await expect(receipt).toContainText(ZLOTY);
  await expect(receipt).not.toContainText(EURO);
  await page.screenshot({ path: shot(`${KEY}-ticket-${size}`) });
  await page.locator('[data-testid=sale-document-modal] [data-testid=sale-document-close]').click();
  await expect(receipt).toBeHidden();
}

/** The row of the sale `number` in «Sales», found by its number. */
async function salesRow(page: Page, number: string) {
  await login(page, A, '/sale/sales');
  await shown(page).locator('[data-testid=sales-table-row], [data-testid=sales-empty]').first().waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=sales-table-search] input').fill(number);
  await expect.poll(() => shown(page).locator('[data-testid=sales-table-row]').count()).toBe(1);
  return shown(page).locator('[data-testid=sales-table-row]').first();
}

test(`${KEY}: a business in Poland sells, charges and keeps its sales in złoty in 390, 834 and 1440 (flow business-currency)`, async ({ page, context }) => {
  await registerBusinessIn(original, 'PL');
  await login(page, A, '/sale/pos');
  // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await login(page, A, '/sale/pos');
    await tillReady(page);
    await addShirt(page);
    const total = await checkTotal(page);
    expect(total).toMatch(ZLOTY);
    expect(total).not.toMatch(EURO);
    await chargeInCash(page, size.name);

    const sale = await newestSaleOf(context, shirt.sku);
    expect((({ currency, total, change_total }) => ({ currency, total, change_total }))(sale)).toEqual({ currency: 'PLN', total: 1250, change_total: 3750 });
    polish = { id: sale.id, number: sale.number };
    const row = await salesRow(page, sale.number);
    await expect(row).toContainText(ZLOTY);
    await expect(row).not.toContainText(EURO);
    await page.screenshot({ path: shot(`${KEY}-sales-${size.name}`) });
  }
});

test(`${KEY}: back in Spain the till is in euros, and the sale charged in Poland keeps its złoty (flow business-currency)`, async ({ page }) => {
  await registerBusinessIn(original, 'ES');
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/sale/pos');
  await tillReady(page);
  await addShirt(page);
  const total = await checkTotal(page);
  expect(total).toMatch(EURO);
  expect(total).not.toMatch(ZLOTY);
  // The check is left open: the cleanup deletes it with the run's sales.

  const row = await salesRow(page, polish.number);
  await expect(row).toContainText(ZLOTY);
  await shown(page).locator(`[data-testid=sales-table-row-${polish.id}-document]`).first().click();
  const receipt = page.locator('[data-testid=sale-document-modal] [data-testid=sale-receipt]');
  await expect(receipt).toBeVisible();
  await expect(receipt).toContainText(ZLOTY);
  await expect(receipt).not.toContainText(EURO);
  await page.screenshot({ path: shot(`${KEY}-es-1440`) });
});
