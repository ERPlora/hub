// flow: INVENTORY-F30, INVENTORY-F31, INVENTORY-F32 — the photo of an article (apps/inventory/WORKBOOK.md), in Chrome
// against the real Inventory, Sales and Taxes apps and the shared image library the Hub serves (`/p/catalog/…`, read
// from `blueprints/img` locally), no doubles:
//   - F30: «Edit» → «Photo» → «Choose from the library», searched in Spanish («café con leche»); the image tapped
//     shows in the form at once and is the article's after «Save changes»: the list's thumbnail and the till's tile
//     load it from the library;
//   - F31: «Upload photo» with a PNG made here: shown at once, uploaded after «Save changes» and kept by the Hub as a
//     512 × 512 WebP in the business's folder (`file:…`, served under `/p/media/<hub>/…`), which the list and the
//     till load; a file past 2 MB is refused on the device, before anything is sent;
//   - F32: an article without a photo keeps its initials over its colour in the till and in the list, never a gap;
//   - screenshots of the library window and of the till at 390, 834 and 1440.
// What this file creates is deleted after it (its photos through the API, which removes them from the folder); the
// cash register goes back as it was.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  dialog,
  type Product,
  productBySku,
  productRow,
  productsReady,
  rowAction,
  searchProducts,
  stamp,
  VIEWPORTS,
} from './inventory-helpers';
import { drawerOff, restoreDrawer } from './sale-helpers';

const RUN = stamp();
let coffee: Product;
let toast: Product;
let own: Product;

/** A 64 × 64 PNG (a sun over red) the person picks on the device. */
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAABG0lEQVR4nOWZy23EMBBD6YcUk7PPKWJL2NJSQsrY09S0FWQhjT4WrXc1wCFNyRCs4/XzLWeQOcgcZA4yB5mDzEHmIHOQOcgcZM7XCNHz9/Hfo3j+9Z11dDzMffA9LsnRJUCV9b4xjsYAaeu9YnC5e7XpcLn7RjVWcN+iySLu08qs4z6nz1LuE1PsjxKs9vprZ23TwDnx9VdN3KYB7wDn9PVTPnePBlYGmYPMQeYgc5A5aIcA0ftvVCFRMHePBu4QIKavoiibuE0DmltCFM/aqQHNKiFqplQ3MDpDVOpnltC4DFGvnNwDIzJESjO/iftmiKxa01eoV4Zo0Nn+juwmt5Q3uSe+BGQOMgeZg8xB5iBzkDnIHGQOVxto5Q3w1FTbH5ebCwAAAABJRU5ErkJggg==',
  'base64',
);
const LIBRARY_URL = '/p/catalog/hospitality/cafe_con_leche.webp';

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/inventory/products');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  coffee = await createProduct(context, { name: `E2E Latte ${RUN}`, sku: `E2E-PH-L-${RUN}`, price: 180 });
  toast = await createProduct(context, { name: `E2E Toast ${RUN}`, sku: `E2E-PH-T-${RUN}`, price: 250 });
  own = await createProduct(context, { name: `E2E House cake ${RUN}`, sku: `E2E-PH-O-${RUN}`, price: 400 });
  await context.close();
});

test.afterAll(async ({ browser }) => {
  // Through the API, so a photo of its own leaves the business's folder with its article.
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/inventory/products');
  for (const product of [coffee, toast, own]) {
    if (product) await api(context, A, 'POST', '/inventory/products/delete', { id: product.id });
  }
  await context.close();
  cleanInventory();
  restoreDrawer();
});

/** Whether the `<img>` in `scope` has loaded its file (a broken one has no natural width). */
async function loaded(scope: Locator): Promise<number> {
  const img = scope.locator('img').first();
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth)).toBeGreaterThan(0);
  return img.evaluate((el: HTMLImageElement) => el.naturalWidth);
}

async function editForm(page: Page, product: Product): Promise<Locator> {
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await searchProducts(page, product.sku);
  await expect(productRow(page, product.sku)).toBeVisible();
  await rowAction(page, product.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  await expect(form).toBeVisible();
  return form;
}

const tile = (page: Page, product: Product): Locator => shown(page).locator(`[data-testid=pos-product-${product.id}]`);

test('INVENTORY-F30: a library image searched in Spanish is the article’s photo in the list and in the till', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  const form = await editForm(page, coffee);
  await expect(form.locator('[data-testid=inventory-product-image-none]')).toBeVisible();
  await form.locator('[data-testid=inventory-product-image-library]').click();

  const library = dialog(page, 'inventory-product-image-library-modal');
  await expect(library).toBeVisible();
  // It opens searching the article's name; the person writes what it is, in Spanish.
  await expect(library.locator('[data-testid=inventory-product-image-library-modal-search] input')).toHaveValue(coffee.name);
  await library.locator('[data-testid=inventory-product-image-library-modal-search] input').fill('café con leche');
  const choice = library.locator('[data-testid=inventory-product-image-library-modal-image-hospitality-cafe_con_leche]');
  await expect(choice).toBeVisible();
  await expect(choice).toContainText(/Café con leche|Coffee with milk/);
  await loaded(choice);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await capture(page, `APP-INVENTORY-F30-${viewport.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
  await choice.click();
  await expect(library).toBeHidden();

  await expect(form.locator('[data-testid=inventory-product-image-preview] img')).toHaveAttribute('src', LIBRARY_URL);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();

  const saved = await productBySku(context, coffee.sku);
  expect(saved).toMatchObject({ image: 'catalog:hospitality/cafe_con_leche', image_url: LIBRARY_URL });
  const thumb = shown(page).locator(`[data-testid=inventory-product-photo-${coffee.id}]`).first();
  expect(await loaded(thumb)).toBe(512);
});

test('INVENTORY-F31: a photo of its own goes up with «Save changes» and comes back as a 512 × 512 WebP', async ({ page, context }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  const form = await editForm(page, own);
  const file = form.locator('[data-testid=inventory-product-image-file]');

  // Past 2 MB: refused on the device, nothing is sent.
  await file.setInputFiles({ name: 'huge.png', mimeType: 'image/png', buffer: Buffer.alloc(2 * 1024 * 1024 + 1) });
  await expect(form.locator('[data-testid=inventory-product-image-error]')).toHaveText(
    /The photo weighs more than 2 MB\. Choose a lighter one\.|La foto pesa más de 2 MB\. Elige una más ligera\./,
  );
  await expect(form.locator('[data-testid=inventory-product-image-preview] img')).toHaveCount(0);

  await file.setInputFiles({ name: 'house-cake.png', mimeType: 'image/png', buffer: PNG });
  await expect(form.locator('[data-testid=inventory-product-image-error]')).toHaveCount(0);
  await expect(form.locator('[data-testid=inventory-product-image-preview] img')).toHaveAttribute('src', /^data:image\/png;base64,/);
  await form.locator('[data-testid=inventory-product-form-submit]').click();
  await expect(form).toBeHidden();

  const saved = await productBySku(context, own.sku);
  const { image, image_url: url } = saved as Product & { image: string; image_url: string };
  expect(image).toMatch(/^file:inventory\/products\/[0-9a-f]+\.webp$/);
  expect(url).toMatch(/^\/p\/media\/[^/]+\/inventory\/products\/[0-9a-f]+\.webp$/);
  const thumb = shown(page).locator(`[data-testid=inventory-product-photo-${own.id}]`).first();
  await expect(thumb.locator('img')).toHaveAttribute('src', url);
  expect(await loaded(thumb)).toBe(512);
  const served = await page.request.get(`${A}${url}`);
  expect([served.status(), served.headers()['content-type']]).toEqual([200, 'image/webp']);
});

test('INVENTORY-F32: the till shows each article’s photo, and the initials over its colour without one, at every width', async ({ page }) => {
  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await expect(tile(page, coffee)).toBeAttached();
    await tile(page, coffee).scrollIntoViewIfNeeded();
    const photo = tile(page, coffee).locator('.pos-tile__thumb img');
    await expect(photo).toHaveAttribute('src', LIBRARY_URL);
    await expect(photo).toHaveAttribute('alt', coffee.name);
    expect(await loaded(tile(page, coffee).locator('.pos-tile__thumb'))).toBe(512);
    expect(await loaded(tile(page, own).locator('.pos-tile__thumb'))).toBe(512);
    // Without a photo: its initials over its colour, never a gap nor a broken image.
    const initials = tile(page, toast).locator('.pos-tile__thumb');
    await expect(initials.locator('img')).toHaveCount(0);
    await expect(initials).toHaveText('ET');
    await expect(initials).toHaveAttribute('style', /linear-gradient/);
    await tile(page, coffee).scrollIntoViewIfNeeded();
    await capture(page, `APP-INVENTORY-F32-${viewport.label}`);
  }
});

test('INVENTORY-F32: the products list shows the thumbnail before the name, and the initials without a photo', async ({ page }) => {
  await login(page, A, '/inventory/products');
  await productsReady(page);
  await searchProducts(page, `E2E-PH-`);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const coffeeThumb = shown(page).locator(`[data-testid=inventory-product-photo-${coffee.id}]`).first();
    await expect(coffeeThumb.locator('img')).toHaveAttribute('src', LIBRARY_URL);
    const toastThumb = shown(page).locator(`[data-testid=inventory-product-photo-${toast.id}]`).first();
    await expect(toastThumb.locator('img')).toHaveCount(0);
    await expect(toastThumb).toHaveText('ET');
    await capture(page, `APP-INVENTORY-F32-list-${viewport.label}`);
  }
});
