// flow: WEBSITE-F05, WEBSITE-F09, WEBSITE-F10, BASE-F110 — the menu of a restaurant's public page, as a customer at a
// table sees it after scanning the menu's QR. Two dishes of Inventory in their own category: one with a photo of its
// own, a description and two allergens, one with a photo of the shared library. The catalog's address (the page's with
// `#catalog`) opens the page right at the catalog, and each card shows its photo (loaded lazily), its description and
// its allergens in the visitor's language, at 375, 820 and 1440, with no error of the page's security policy; «Share and
// QR» gives that address and its QR; and on the business's own domain both photos load too. Hub `a`'s site, its photo
// and its products are put back after, also when a test fails: the other specs expect `/` of `a` to jump to the login.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, psql } from './helpers';
import { cleanInventory, createProduct, stamp } from './inventory-helpers';
import { keepPhotoOfA, type PhotoOfA } from './saas-photo';
import { STACK } from './stack';
import { atRest, ownerOfTheSite, photo, PUBLIC_SIZES, type Site, siteBackOffline, WIDE } from './website-helpers';

const KEY = 'WEBSITE-MENU';
const DOMAIN = 'www.micarta.test';
const ON_DOMAIN = `http://${DOMAIN}:${STACK.hubPort}`;
const RUN = stamp();
const CATEGORY = `E2E Tapas ${RUN}`;
const TOAST = 'E2E Tostada';
const LATTE = 'E2E Café con leche';
const DESCRIPTION = 'Pan de pueblo con tomate y aceite.';
const LIBRARY_URL = '/p/catalog/hospitality/cafe_con_leche.webp';

test.describe.configure({ mode: 'serial' });
test.use({ launchOptions: { args: [`--host-resolver-rules=MAP ${DOMAIN} 127.0.0.1`] } });

let saasPhoto: PhotoOfA | undefined;
let photoBefore: Record<string, unknown> = {};
let found: Site | undefined;
let owner: { context: BrowserContext; page: Page } | undefined;

/** A visitor: a fresh context without a session, its console's errors (the page's policy refusing an image among
 * them) gathered in `failures`. */
async function visitor(
  browser: Browser,
  viewport: { width: number; height: number },
  locale = 'en-GB',
): Promise<{ context: BrowserContext; page: Page; failures: string[] }> {
  const context = await browser.newContext({ viewport, locale });
  const page = await context.newPage();
  const failures: string[] = [];
  page.on('console', (message) => {
    // Only on the own domain, over plain HTTP on a host that is not localhost: on the real domain it is HTTPS.
    if (message.type() === 'error' && !message.text().includes('Cross-Origin-Opener-Policy')) failures.push(message.text());
  });
  page.on('pageerror', (error) => failures.push(String(error)));
  return { context, page, failures };
}

const card = (page: Page, name: string): Locator => page.locator('[data-ep-block="catalog"] .card').filter({ hasText: name });

/** The card's photo in sight and loaded (it loads lazily), and its address. */
async function loadedPhoto(item: Locator): Promise<string> {
  const image = item.locator('img');
  await expect(image).toHaveAttribute('loading', 'lazy');
  await image.scrollIntoViewIfNeeded();
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  return image.evaluate((img: HTMLImageElement) => img.src);
}

test.beforeAll(async ({ browser }) => {
  saasPhoto = keepPhotoOfA('e2e_website_menu_photo_before');
  photoBefore = JSON.parse(psql(`select state from base_hub where slug = 'a'`) || '{}') as Record<string, unknown>;
  ({ owner, found } = await ownerOfTheSite(browser, WIDE));
  const { context } = owner;
  const tapas = await api<{ id: string }>(context, A, 'POST', '/inventory/categories', { name: CATEGORY });
  expect(tapas.status, JSON.stringify(tapas.data)).toBe(201);
  const toast = await createProduct(context, {
    ...{ name: TOAST, sku: `E2E-MENU-T-${RUN}`, price: 350, description: DESCRIPTION },
    ...{ allergens: ['milk', 'gluten'], category_ids: [tapas.data.id] },
  });
  const upload = await api(context, A, 'POST', '/inventory/products/image/upload', {
    id: toast.id,
    data_base64: (await photo(owner.page, 'Tostada', 20)).toString('base64'),
  });
  expect(upload.status, JSON.stringify(upload.data)).toBe(200);
  const latte = await createProduct(context, { name: LATTE, sku: `E2E-MENU-L-${RUN}`, price: 180, category_ids: [tapas.data.id] });
  const library = await api(context, A, 'POST', '/inventory/products/image', { id: latte.id, image: 'catalog:hospitality/cafe_con_leche' });
  expect(library.status, JSON.stringify(library.data)).toBe(200);
  const content = {
    ...found.content,
    catalog: { hidden: false, title: '', source: 'inventory', category_ids: [tapas.data.id], show_prices: true },
  };
  const saved = await api(context, A, 'POST', '/website/site', { template: 'classic', theme: found.theme, content });
  expect(saved.status, JSON.stringify(saved.data)).toBe(200);
  const published = await api(context, A, 'POST', '/website/site/publish');
  expect(published.status, JSON.stringify(published.data)).toBe(200);
});

test.afterAll(async () => {
  try {
    if (owner && found) await siteBackOffline(owner.context, found);
  } finally {
    saasPhoto?.putBack();
    cleanInventory();
    await owner?.context.close();
  }
});

test(`${KEY}: the catalog's address opens the page at the menu, each dish with its photo, description and allergens, at 375, 820 and 1440`, async ({
  browser,
}) => {
  for (const size of PUBLIC_SIZES) {
    const { context, page, failures } = await visitor(browser, { width: size.width, height: size.height });
    const response = await page.goto(`${A}/#catalog`);
    expect(response?.status()).toBe(200);
    await expect(page.locator('#catalog')).toBeInViewport();
    const toast = card(page, TOAST);
    await expect(toast).toContainText(DESCRIPTION);
    await expect(toast).toContainText('Allergens: Gluten, Milk');
    await expect(toast).toContainText('€3.50');
    expect(new URL(await loadedPhoto(toast)).pathname).toMatch(/^\/p\/media\/[0-9a-f]{32}\/inventory\/products\/[0-9a-f]{32}\.webp$/);
    const latte = card(page, LATTE);
    await expect(latte).not.toContainText('Allergens');
    expect(new URL(await loadedPhoto(latte)).pathname).toBe(LIBRARY_URL);
    await toast.scrollIntoViewIfNeeded();
    await atRest(page);
    await capture(page, `${KEY}-${size.name}`);
    expect(failures).toEqual([]);
    await context.close();
  }
});

test(`${KEY}: a visitor in Spanish reads the allergens by their Spanish names`, async ({ browser }) => {
  const { context, page, failures } = await visitor(browser, { width: 375, height: 667 }, 'es-ES');
  await page.goto(`${A}/#catalog`);
  await expect(card(page, TOAST)).toContainText('Alérgenos: Gluten, Leche');
  await expect(card(page, TOAST)).toContainText('3,50');
  expect(failures).toEqual([]);
  await context.close();
});

test(`${KEY}: «Share and QR» gives the catalog's own address and QR, to print for the tables`, async () => {
  if (!owner) throw new Error('No owner of a.');
  const { page, context } = owner;
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: A });
  await page.goto(`${A}/website`);
  await page.getByTestId('website-share').click();
  await expect(page.getByTestId('website-share-catalog-url')).toHaveText(`${A}/#catalog`);
  await expect(page.getByTestId('website-share-catalog-hint')).toContainText('tables');
  const qr = page.getByTestId('website-share-catalog-qr');
  await expect.poll(() => qr.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await page.getByTestId('website-share-catalog-copy').click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(`${A}/#catalog`);
  const download = page.waitForEvent('download');
  await page.getByTestId('website-share-catalog-png').click();
  expect((await download).suggestedFilename()).toBe('website-catalog-qr-a.png');
  for (const size of PUBLIC_SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await qr.scrollIntoViewIfNeeded();
    await atRest(page);
    await capture(page, `${KEY}-SHARE-${size.name}`);
  }
  await page.setViewportSize(WIDE);
  await page.getByTestId('website-share-close').click();
});

test(`${KEY}: on the business's own domain both photos load, its own and the library's`, async ({ browser }) => {
  if (!saasPhoto) throw new Error('No photo of a was kept before the run.');
  await saasPhoto.send({ ...photoBefore, custom_domain: DOMAIN });
  try {
    const { context, page, failures } = await visitor(browser, WIDE);
    const response = await page.goto(`${ON_DOMAIN}/#catalog`);
    expect(response?.status()).toBe(200);
    for (const name of [TOAST, LATTE]) {
      expect(new URL(await loadedPhoto(card(page, name))).host, name).toBe(`${DOMAIN}:${STACK.hubPort}`);
    }
    expect(failures).toEqual([]);
    await context.close();
  } finally {
    await saasPhoto.send({ ...photoBefore, custom_domain: null });
  }
});
