// flow: COMBO-F14 — the photo of a set menu (apps/combo/WORKBOOK.md), in Chrome against the real Menus, Inventory,
// Sales and Taxes apps and the shared image library the Hub serves, no doubles:
//   - «Edit details» → «Photo» → «Choose from the library», searched in Spanish («desayuno»: the library's menu_* images
//     are one breakfast tray, titled as such by its manifest): the image tapped is the menu's after «Save», and the
//     list's thumbnail and the till's menu tile load it from the library;
//   - «Upload photo» with a PNG made here: uploaded after «Save» and kept as a 512 × 512 WebP in the business's folder;
//   - screenshots of the till with the menu's photo at 390, 834 and 1440.
// What this file creates is deleted after it (the menus through the API, which removes their own photo from the
// folder); the cash register goes back as it was.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { cleanInventory, createProduct, dialog, PHOTO_PNG, photoLoaded, stamp, VIEWPORTS } from './inventory-helpers';
import { drawerOff, restoreDrawer } from './sale-helpers';

interface Menu {
  id: string;
  name: string;
  image?: string;
  image_url?: string;
}

const RUN = stamp();
const TAG = 'e2e photo';
let daily: Menu;
let house: Menu;
const LIBRARY_URL = '/p/catalog/hospitality/menu_dia.webp';

/** A menu that the till can sell: one course with one product. */
async function sellableMenu(page: Page, name: string, productId: string): Promise<Menu> {
  const context = page.context();
  const menu = await api<Menu>(context, A, 'POST', '/combo/combos', { name, price: 1350, tax_category_key: 'product.generic' });
  expect(menu.status, 'menu').toBe(201);
  const course = await api<{ id: string }>(context, A, 'POST', '/combo/groups', { combo_id: menu.data.id, name: 'Main' });
  expect(course.status, 'course').toBe(201);
  const choice = await api(context, A, 'POST', '/combo/options', { group_id: course.data.id, product_id: productId });
  expect(choice.status, 'choice').toBe(201);
  return menu.data;
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/combo/menus');
  // The till opens without a cash session: the drawer's lock is sale-cash-gate.spec.ts's.
  await drawerOff(context);
  const stew = await createProduct(context, { name: `E2E Stew ${RUN}`, sku: `E2E-PHM-${RUN}`, price: 900 });
  daily = await sellableMenu(page, `${TAG} Daily ${RUN}`, stew.id);
  house = await sellableMenu(page, `${TAG} House ${RUN}`, stew.id);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  // Through the API, so a menu's own photo leaves the business's folder with it.
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/combo/menus');
  for (const menu of [daily, house]) {
    if (menu) await api(context, A, 'POST', '/combo/combos/delete', { id: menu.id });
  }
  await context.close();
  const combos = `select id from combo_combo where name like '${TAG} %'`;
  psql(
    [
      `delete from combo_choiceoption where group_id in (select id from combo_choicegroup where combo_id in (${combos}))`,
      `delete from combo_choicegroup where combo_id in (${combos})`,
      `delete from combo_combo where name like '${TAG} %'`,
    ].join('; '),
  );
  cleanInventory();
  restoreDrawer();
});

async function editForm(page: Page, menu: Menu): Promise<Locator> {
  await login(page, A, '/combo/menus');
  await shown(page).locator('[data-testid=combo-menus-search] input').fill(menu.name);
  await expect(shown(page).locator(`[data-testid=combo-menus-row][data-id="${menu.id}"]`)).toBeVisible();
  const action = shown(page).locator(`[data-testid=combo-menus-row-${menu.id}-edit]`);
  const more = shown(page).locator(`[data-testid=combo-menus-row-${menu.id}-menu]`);
  await action.or(more).first().waitFor({ state: 'visible' });
  if (await action.isVisible()) await action.click();
  else {
    await more.click();
    await page.locator(`ion-popover [data-testid=combo-menus-row-${menu.id}-edit]`).click();
  }
  const form = dialog(page, 'combo-menu-form');
  await expect(form).toBeVisible();
  return form;
}

async function detail(page: Page, id: string): Promise<Menu> {
  const res = await api<Menu>(page.context(), A, 'GET', `/combo/combos/detail?id=${id}`);
  expect(res.status).toBe(200);
  return res.data;
}

test('COMBO-F14: a library image is the menu’s photo in the list and on its till tile, at every width', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  const form = await editForm(page, daily);
  await form.locator('[data-testid=combo-menu-form-image-library]').click();
  const library = dialog(page, 'combo-menu-form-image-library-modal');
  await expect(library).toBeVisible();
  await library.locator('[data-testid=combo-menu-form-image-library-modal-search] input').fill('desayuno');
  const choice = library.locator('[data-testid=combo-menu-form-image-library-modal-image-hospitality-menu_dia]');
  await expect(choice).toBeVisible();
  await choice.click();
  await expect(library).toBeHidden();
  await expect(form.locator('[data-testid=combo-menu-form-image-preview] img')).toHaveAttribute('src', LIBRARY_URL);
  await form.locator('[data-testid=combo-menu-form-submit]').click();
  await expect(form).toBeHidden();

  expect(await detail(page, daily.id)).toMatchObject({ image: 'catalog:hospitality/menu_dia', image_url: LIBRARY_URL });
  expect(await photoLoaded(shown(page).locator(`[data-testid=combo-menu-photo-${daily.id}]`).first())).toBe(512);

  await login(page, A, '/sale/pos');
  await shown(page).locator('[data-testid=pos-till]').waitFor({ state: 'visible' });
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const tile = shown(page).locator(`[data-testid=pos-menu-${daily.id}]`);
    await tile.scrollIntoViewIfNeeded();
    await expect(tile.locator('.pos-menu__thumb img')).toHaveAttribute('src', LIBRARY_URL);
    expect(await photoLoaded(tile.locator('.pos-menu__thumb'))).toBe(512);
    await capture(page, `APP-COMBO-F14-${viewport.label}`);
  }
});

test('COMBO-F14: a photo of its own goes up with «Save» and comes back as a 512 × 512 WebP', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 860 });
  const form = await editForm(page, house);
  await form.locator('[data-testid=combo-menu-form-image-file]').setInputFiles({ name: 'house.png', mimeType: 'image/png', buffer: PHOTO_PNG });
  await expect(form.locator('[data-testid=combo-menu-form-image-preview] img')).toHaveAttribute('src', /^data:image\/png;base64,/);
  await form.locator('[data-testid=combo-menu-form-submit]').click();
  await expect(form).toBeHidden();

  const saved = await detail(page, house.id);
  expect(saved.image).toMatch(/^file:combo\/combos\/[0-9a-f]+\.webp$/);
  expect(saved.image_url).toMatch(/^\/p\/media\/[^/]+\/combo\/combos\/[0-9a-f]+\.webp$/);
  const thumb = shown(page).locator(`[data-testid=combo-menu-photo-${house.id}]`).first();
  await expect(thumb.locator('img')).toHaveAttribute('src', saved.image_url!);
  expect(await photoLoaded(thumb)).toBe(512);
});
