// flow: SERVICE-F34, SERVICE-F35 — the photo of a service (apps/service/WORKBOOK.md), in Chrome against the real
// Services, Sales and Taxes apps and the shared image library the Hub serves, no doubles:
//   - F34: «Edit» → «Photo» → «Choose from the library»: the Hair and Beauty sectors come first; searched in Spanish
//     («mechas»), the image tapped is the service's after «Save changes», and the list's thumbnail and the till's
//     service tile load it from the library;
//   - F35: «Upload photo» with a PNG made here: uploaded after «Save changes» and kept as a 512 × 512 WebP in the
//     business's folder, which the list loads;
//   - the library names its images in the language the person reads the Hub in, whatever the business's;
//   - screenshots of the library window at 390, 834 and 1440, in English and in Spanish.
// What this file creates is deleted after it (its own photo through «Remove photo», which removes it from the folder);
// the cash register goes back as it was.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, painted, shown } from './helpers';
import { dialog, PHOTO_PNG, photoLoaded, VIEWPORTS } from './inventory-helpers';
import { drawerOff, restoreDrawer, tilePhotoLoaded } from './sale-helpers';
import { cleanUp, named, post, rowAction } from './service-helpers';

interface Service {
  id: string;
  name: string;
  image?: string;
  image_url?: string;
}

let highlights: Service;
let colour: Service;
let own: Service;
const LIBRARY_URL = '/p/catalog/beauty_hair/mechas.webp';

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/service/services');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  highlights = await post<Service>(context, '/service/services', { name: named('Highlights'), price: 4500, tax_category_key: 'service.generic' });
  colour = await post<Service>(context, '/service/services', { name: named('Colour'), price: 5000, tax_category_key: 'service.generic' });
  own = await post<Service>(context, '/service/services', { name: named('Signature cut'), price: 3000, tax_category_key: 'service.generic' });
  await context.close();
});

test.afterAll(async ({ browser }) => {
  // «Remove photo» through the API: its own photo leaves the business's folder before the rows go.
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/service/services');
  if (own) await api(context, A, 'POST', '/service/services/image', { id: own.id, image: '' });
  await context.close();
  cleanUp();
  restoreDrawer();
});

async function editForm(page: Page, service: Service): Promise<Locator> {
  await login(page, A, '/service/services');
  await shown(page).locator('[data-testid=service-services-search] input').fill(service.name);
  await expect(shown(page).locator('[data-testid=service-services-row]', { hasText: service.name })).toBeVisible();
  await rowAction(page, 'service-services', service.id, 'edit');
  const form = dialog(page, 'service-form');
  await expect(form).toBeVisible();
  return form;
}

/**
 * The service's form with the Hub in `language`, as the language picker of «My profile» leaves it; the business has no
 * language of its own here. The cookie goes after a first login: in a fresh context, the login brings back the hub's
 * cookies, the language among them.
 */
async function editFormIn(page: Page, service: Service, language: 'en' | 'es'): Promise<Locator> {
  await login(page, A, '/service/services');
  await page.context().addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  const form = await editForm(page, service);
  await expect(page.locator('html')).toHaveAttribute('lang', language);
  return form;
}

/**
 * The names of the library's images that do not show whole right under their image: cut with «…», short of lines,
 * past their tile, or pushed down away from the image by a taller tile of the same row.
 */
async function cutNames(library: Locator): Promise<string[]> {
  return library.locator('[data-testid^=service-form-image-library-modal-image-] span').evaluateAll((names) =>
    names
      .filter((name) => {
        const tile = name.closest('button')!.getBoundingClientRect();
        const image = name.previousElementSibling!.getBoundingClientRect();
        const box = name.getBoundingClientRect();
        const cut = name.scrollWidth > name.clientWidth + 1 || name.scrollHeight > name.clientHeight + 1;
        return cut || box.left < tile.left - 1 || box.right > tile.right + 1 || box.top - image.bottom > 8;
      })
      .map((name) => name.textContent!.trim()),
  );
}

async function detail(page: Page, id: string): Promise<Service> {
  const res = await api<Service>(page.context(), A, 'GET', `/service/services/detail?id=${id}`);
  expect(res.status).toBe(200);
  return res.data;
}

test('SERVICE-F34: a library image, Hair and Beauty first, is the service’s photo in the list and in the till', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  const form = await editForm(page, highlights);
  await form.locator('[data-testid=service-form-image-library]').click();
  const library = dialog(page, 'service-form-image-library-modal');
  await expect(library).toBeVisible();
  const tabs = library.locator('[data-testid^=service-form-image-library-modal-folder-]');
  await expect(tabs).toHaveCount(7);
  expect(await tabs.evaluateAll((els) => els.slice(0, 3).map((el) => el.getAttribute('data-testid')!.split('-folder-')[1]))).toEqual([
    'all',
    'beauty_hair',
    'beauty_body',
  ]);
  await library.locator('[data-testid=service-form-image-library-modal-search] input').fill('mechas');
  const choice = library.locator('[data-testid=service-form-image-library-modal-image-beauty_hair-mechas]');
  await expect(choice).toBeVisible();
  await photoLoaded(choice);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await capture(page, `APP-SERVICE-F34-${viewport.label}`);
  }
  await page.setViewportSize({ width: 1280, height: 860 });
  await choice.click();
  await expect(library).toBeHidden();
  await expect(form.locator('[data-testid=service-form-image-preview] img')).toHaveAttribute('src', LIBRARY_URL);
  await form.locator('[data-testid=service-form-submit]').click();
  await expect(form).toBeHidden();

  expect(await detail(page, highlights.id)).toMatchObject({ image: 'catalog:beauty_hair/mechas', image_url: LIBRARY_URL });
  expect(await photoLoaded(shown(page).locator(`[data-testid=service-photo-${highlights.id}]`).first())).toBe(512);

  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  await shown(page).locator('[data-testid=pos-category-services]').click();
  const tile = shown(page).locator(`[data-testid=pos-service-${highlights.id}]`);
  expect(await tilePhotoLoaded(tile, highlights.name, LIBRARY_URL)).toBe(512);
});

test('SERVICE-F34: the library names its images in the language the person reads the Hub in', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  for (const [language, title] of [['es', 'Mechas'], ['en', 'Highlights']] as const) {
    const form = await editFormIn(page, colour, language);
    await form.locator('[data-testid=service-form-image-library]').click();
    const library = dialog(page, 'service-form-image-library-modal');
    await library.locator('[data-testid=service-form-image-library-modal-search] input').fill('Mechas');
    const choice = library.locator('[data-testid=service-form-image-library-modal-image-beauty_hair-mechas]');
    await expect(choice).toHaveText(title);
    await expect(choice.locator('img')).toHaveAttribute('alt', title);
    if (language !== 'es') continue;
    await photoLoaded(choice);
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await capture(page, `APP-SERVICE-F34-ES-${viewport.label}`);
    }
    await page.setViewportSize({ width: 1280, height: 860 });
  }
});

test('SERVICE-F34: every image of the library shows its whole name under it, on a phone, a tablet and a desktop', async ({ page }) => {
  // The longest Spanish names of the hair sector, and the longest single word of the library.
  const searches = [
    ['Mechas', 'mechas_papel'],
    ['Corte', 'corte_caballero'],
    ['Microdermoabrasión', 'microdermoabrasion'],
  ] as const;
  const sizes = [
    { width: 375, height: 667 },
    { width: 820, height: 1180 },
    { width: 1180, height: 820 },
    { width: 1440, height: 900 },
  ];
  await page.setViewportSize(sizes[3]);
  const form = await editFormIn(page, colour, 'es');
  await form.locator('[data-testid=service-form-image-library]').click();
  const library = dialog(page, 'service-form-image-library-modal');
  for (const [query, longest] of searches) {
    await library.locator('[data-testid=service-form-image-library-modal-search] input').fill(query);
    await expect(library.locator(`[data-testid$=-image-beauty_hair-${longest}], [data-testid$=-image-beauty_body-${longest}]`)).toBeVisible();
    for (const size of sizes) {
      await page.setViewportSize(size);
      await painted(page);
      expect(await cutNames(library), `«${query}» at ${size.width}x${size.height}`).toEqual([]);
      if (query !== 'Microdermoabrasión') await capture(page, `APP-SERVICE-F34-NAMES-${query}-${size.width}x${size.height}`);
    }
    await page.setViewportSize(sizes[3]);
  }
});

test('SERVICE-F35: a photo of its own goes up with «Save changes» and comes back as a 512 × 512 WebP', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  const form = await editForm(page, own);
  await form.locator('[data-testid=service-form-image-file]').setInputFiles({ name: 'cut.png', mimeType: 'image/png', buffer: PHOTO_PNG });
  await expect(form.locator('[data-testid=service-form-image-preview] img')).toHaveAttribute('src', /^data:image\/png;base64,/);
  await form.locator('[data-testid=service-form-submit]').click();
  await expect(form).toBeHidden();

  const saved = await detail(page, own.id);
  expect(saved.image).toMatch(/^file:service\/services\/[0-9a-f]+\.webp$/);
  expect(saved.image_url).toMatch(/^\/p\/media\/[^/]+\/service\/services\/[0-9a-f]+\.webp$/);
  const thumb = shown(page).locator(`[data-testid=service-photo-${own.id}]`).first();
  await expect(thumb.locator('img')).toHaveAttribute('src', saved.image_url!);
  expect(await photoLoaded(thumb)).toBe(512);
});
