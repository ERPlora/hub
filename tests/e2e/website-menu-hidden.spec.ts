// flow: INVENTORY-F36, WEBSITE-F05, WEBSITE-F10 — the owner hides a dish from the website in Products' row menu: the
// public menu leaves it out, at 375, 820 and 1440, the dish beside it still shows, and the till's sale catalog still
// offers it; its row menu offers «Hide from website», at the same sizes. The product's sheet then says it is hidden and its form's «Show on website» box is unticked, with its
// note, at the same sizes. Hub `a`'s site and its products are put back after, also when a test fails: the other
// specs expect `/` of `a` to jump to the login.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture } from './helpers';
import {
  createProduct,
  dialog,
  type Product,
  productBySku,
  productRow,
  productsReady,
  searchProducts,
  stamp,
} from './inventory-helpers';
import { PAINTED, rowAction, rowActionIcon } from './service-helpers';
import { atRest, menuSpecDone, ownerOfTheSite, PUBLIC_SIZES, publishWithMenuOf, type Site, WIDE } from './website-helpers';

const KEY = 'WEBSITE-MENU-HIDDEN';
const RUN = stamp();
const SHOWN = 'E2E Tostada';
const HIDDEN = 'E2E Comida del personal';

test.describe.configure({ mode: 'serial' });

let found: Site | undefined;
let owner: { context: BrowserContext; page: Page } | undefined;
let staffMeal: Product;

test.beforeAll(async ({ browser }) => {
  ({ owner, found } = await ownerOfTheSite(browser, WIDE));
  const { context } = owner;
  const tapas = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name: `E2E Hidden ${RUN}` });
  expect(tapas.status, JSON.stringify(tapas.data)).toBe(201);
  await createProduct(context, { name: SHOWN, sku: `E2E-HID-T-${RUN}`, price: 350, category_ids: [tapas.data.id] });
  staffMeal = await createProduct(context, { name: HIDDEN, sku: `E2E-HID-S-${RUN}`, price: 500, category_ids: [tapas.data.id] });
  await publishWithMenuOf(context, found, [tapas.data.id]);
});

test.afterAll(async () => {
  await menuSpecDone(owner, found);
});

test(`${KEY}: a dish hidden from the website in Products is not on the public menu and the till still sells it`, async ({
  browser,
}) => {
  if (!owner) throw new Error('No owner of a.');
  const { page, context } = owner;
  await page.goto(`${A}/inventory/products`);
  await productsReady(page);
  await searchProducts(page, staffMeal.sku);
  await expect(productRow(page, staffMeal.sku)).toBeVisible();
  for (const size of PUBLIC_SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    // The action lives in «⋮» alone: the first read opens it and the next ones read its entry there.
    await expect.poll(() => rowActionIcon(page, 'inventory-products', staffMeal.id, 'hide_from_website', 'globe-outline')).toEqual(PAINTED);
    const hide = page.locator(`ion-popover [data-testid=inventory-products-row-${staffMeal.id}-hide_from_website]`);
    await expect(hide).toBeVisible();
    await capture(page, `${KEY}-ROW-MENU-${size.name}`);
    await page.keyboard.press('Escape');
    await expect(hide).toBeHidden();
  }
  await page.setViewportSize(WIDE);
  await rowAction(page, 'inventory-products', staffMeal.id, 'hide_from_website');
  await expect.poll(async () => (await productBySku(context, staffMeal.sku)).show_on_website).toBe(false);

  const forSale = await api<{ rows: { sku: string }[] }>(context, A, 'GET', `/inventory/products/for_sale?search=${staffMeal.sku}`);
  expect(forSale.data.rows.map((row) => row.sku)).toEqual([staffMeal.sku]);

  for (const size of PUBLIC_SIZES) {
    const visitor = await browser.newContext({ viewport: { width: size.width, height: size.height }, locale: 'es-ES' });
    const menu = await visitor.newPage();
    expect((await menu.goto(`${A}/#catalog`))?.status()).toBe(200);
    const cards = menu.locator('[data-ep-block="catalog"] .card');
    await expect(cards.filter({ hasText: SHOWN })).toBeVisible();
    await expect(cards.filter({ hasText: HIDDEN })).toHaveCount(0);
    await atRest(menu);
    await capture(menu, `${KEY}-${size.name}`);
    await visitor.close();
  }
});

test(`${KEY}: the sheet says the dish is hidden and its form shows the box unticked with its note, at 375, 820 and 1440`, async () => {
  if (!owner) throw new Error('No owner of a.');
  const { page } = owner;
  await page.goto(`${A}/inventory/products`);
  await productsReady(page);
  await searchProducts(page, staffMeal.sku);
  await expect(productRow(page, staffMeal.sku)).toBeVisible();

  await rowAction(page, 'inventory-products', staffMeal.id, 'detail');
  const sheet = dialog(page, 'inventory-product-detail');
  await expect(sheet.getByTestId('inventory-product-detail-website').locator('ion-note')).toHaveText(/^(Hidden|Oculto)$/);
  for (const size of PUBLIC_SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await sheet.getByTestId('inventory-product-detail-website').scrollIntoViewIfNeeded();
    await capture(page, `${KEY}-SHEET-${size.name}`);
  }
  await sheet.getByTestId('inventory-product-detail-close-button').click();
  await expect(sheet).toBeHidden();

  await page.setViewportSize(WIDE);
  await rowAction(page, 'inventory-products', staffMeal.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  const box = form.getByTestId('inventory-product-show-on-website');
  await expect(box).toHaveJSProperty('checked', false);
  await expect(form.getByTestId('inventory-product-show-on-website-note')).toBeVisible();
  // The form's reads answered: its tax category and its category are in their fields.
  await expect(form.locator('[data-testid=inventory-product-tax] input')).not.toHaveValue('');
  await expect(form.locator('[data-testid^="inventory-product-categories-chip-"]')).toHaveCount(1);
  for (const size of PUBLIC_SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await form.getByTestId('inventory-product-show-on-website-note').scrollIntoViewIfNeeded();
    await capture(page, `${KEY}-FORM-${size.name}`);
  }
  await form.getByTestId('inventory-product-form-cancel').click();
  await expect(form).toBeHidden();
});
