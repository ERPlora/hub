// flow: INVENTORY-F01, INVENTORY-F02, BASE-F05 · hub#1015 — Android's Back on «New product» and «Editing product» of the
// installed app. It closed the window and threw away what had been typed, without a word (QA on a Lenovo tablet). Now,
// with something typed and not saved, Back asks «Discard changes?» («Keep editing» / «Discard changes») and the window
// stays until the person chooses; a second Back closes the question and they keep editing. As it opened, Back closes
// it at once, as before. The installed app's Back is simulated at the edge (system-back-helpers.ts); hub, SaaS, Taxes
// and Inventory are the real ones. Nothing is saved: the products the edit needs are made through the API and removed.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, login, shot, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  dialog,
  fill,
  productBySku,
  productsReady,
  rowAction,
  searchProducts,
  stamp,
  VIEWPORTS,
} from './inventory-helpers';
import { insideTheApp, leftTheApp, pressBack } from './system-back-helpers';

test.afterAll(() => {
  cleanInventory();
});

/** «Discard changes?»: base's question (ConfirmDialog), on top of the window; the newest one (a closed one stays parked
 *  hidden). Ionic moves its name and role into its shadow DOM, so it is found by its class and its words. */
const question = (page: Page): Locator => page.locator('ion-modal.ep-confirm-dialog').last();
const QUESTION = /Discard changes\?|¿Descartar los cambios\?/;
/** No question on screen. */
const noQuestion = (page: Page) => expect(page.locator('ion-modal.ep-confirm-dialog:visible')).toHaveCount(0);

/** Products of the installed app, opened cold (a link or a reload straight into it). */
async function productsInsideTheApp(page: Page): Promise<void> {
  await login(page, A);
  await insideTheApp(page);
  await page.goto('/inventory/products');
  await productsReady(page);
}

async function newProduct(page: Page): Promise<Locator> {
  await shown(page).locator('[data-testid=inventory-products-add]').click();
  const form = dialog(page, 'inventory-product-form');
  await expect(form).toBeVisible();
  return form;
}

for (const vp of VIEWPORTS) {
  test(`INVENTORY-F01 ${vp.label}: Back on «New product» with something typed asks first and keeps it until the person chooses`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await productsInsideTheApp(page);
    const form = await newProduct(page);
    const name = form.locator('[data-testid=inventory-product-name] input');
    await fill(form, 'inventory-product-name', 'E2E Back coffee');
    await fill(form, 'inventory-product-sku', `E2E-BACK-${stamp()}`);

    await pressBack(page);
    const asked = question(page);
    await expect(asked).toBeVisible();
    await expect(asked).toContainText(QUESTION);
    await expect(asked.locator('.ep-form-modal__cancel')).toHaveText(/^\s*(Keep editing|Seguir editando)\s*$/);
    await expect(asked.locator('.ep-form-modal__submit')).toHaveText(/^\s*(Discard changes|Descartar cambios)\s*$/);
    await expect(form).toBeVisible();
    await expect(page).toHaveURL(`${A}/inventory/products`);
    await page.screenshot({ path: shot(`INVENTORY-F01-back-asks-${vp.label}`) });

    // A second Back closes the question, as Back closes any window on top: the person keeps editing.
    await pressBack(page);
    await expect(asked).toBeHidden();
    await expect(form).toBeVisible();
    await expect(name).toHaveValue('E2E Back coffee');

    await pressBack(page);
    await asked.locator('.ep-form-modal__cancel').click();
    await expect(asked).toBeHidden();
    await expect(form).toBeVisible();
    await expect(name).toHaveValue('E2E Back coffee');

    await pressBack(page);
    await asked.locator('.ep-form-modal__submit').click();
    await expect(form).toBeHidden();
    await expect(page).toHaveURL(`${A}/inventory/products`);
    expect(await leftTheApp(page)).toBe(false);

    // Thrown away: «New product» opens empty again, and Back on it closes it at once.
    const again = await newProduct(page);
    await expect(again.locator('[data-testid=inventory-product-name] input')).toHaveValue('');
    await pressBack(page);
    await expect(again).toBeHidden();
    await noQuestion(page);
  });
}

test('INVENTORY-F01 390: Back on «New product» as it opened closes it at once, and the next Back goes Home', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await productsInsideTheApp(page);
  const form = await newProduct(page);

  await pressBack(page);
  await expect(form).toBeHidden();
  await noQuestion(page);
  await expect(page).toHaveURL(`${A}/inventory/products`);

  await pressBack(page);
  await expect(page).toHaveURL(`${A}/`);
  expect(await leftTheApp(page)).toBe(false);
});

test('INVENTORY-F02 390: Back on «Editing product» closes it as opened; with a change it asks, and «Discard changes» saves nothing', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const sku = `E2E-BACK-EDIT-${stamp()}`;
  await productsInsideTheApp(page);
  const tea = await createProduct(context, { name: 'E2E Back tea', sku, price: 250 });
  await searchProducts(page, sku);

  await rowAction(page, tea.id, 'edit');
  const form = dialog(page, 'inventory-product-form');
  await expect(form).toContainText(/(Editing product|Editando producto) — E2E Back tea/);
  await pressBack(page);
  await expect(form).toBeHidden();
  await noQuestion(page);

  await rowAction(page, tea.id, 'edit');
  await expect(form).toBeVisible();
  await fill(form, 'inventory-product-name', 'E2E Back green tea');
  await pressBack(page);
  const asked = question(page);
  await expect(asked).toBeVisible();
  await expect(form).toBeVisible();
  await page.screenshot({ path: shot('INVENTORY-F02-back-asks-390') });
  await asked.locator('.ep-form-modal__submit').click();
  await expect(form).toBeHidden();
  await expect(page).toHaveURL(`${A}/inventory/products`);
  expect((await productBySku(context, sku)).name).toBe('E2E Back tea');
});
