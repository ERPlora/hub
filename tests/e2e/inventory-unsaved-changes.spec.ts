// flow: INVENTORY-F01, INVENTORY-F02, BASE-F05 · hub#1015, hub#1023 — «New product» and «Editing product» with something
// typed and not saved. Android's Back on the installed app (hub#1015), and «Cancel» («Cancel editing»), the window's «×»,
// Escape and a tap outside (hub#1023), closed the window and threw away what had been typed, without a word. Now each of
// them asks «Discard changes?» («Keep editing» / «Discard changes») and the window stays until the person chooses; a
// second Back closes the question and they keep editing, and «Discard changes» closes it without asking again. As it
// opened, they close it at once, as before. The installed app's Back is simulated at the edge (system-back-helpers.ts);
// the other ways out are the browser's own; hub, SaaS, Taxes and Inventory are the real ones. Nothing is saved: the
// products the edit needs are made through the API and removed.
import { expect, type Locator, type Page, test } from '@playwright/test';

import { A, capture, login, shown } from './helpers';
import {
  cleanInventory,
  createProduct,
  fill,
  presentedDialog,
  productBySku,
  productsReady,
  rowAction,
  searchProducts,
  stamp,
  VIEWPORTS,
} from './inventory-helpers';
import { insideTheApp, leftTheApp, pressBack } from './system-back-helpers';
import { noQuestion, question, QUESTION } from './unsaved-back-helpers';

test.afterAll(() => {
  cleanInventory();
});

/** Products of the installed app, opened cold (a link or a reload straight into it). */
async function productsInsideTheApp(page: Page): Promise<void> {
  await login(page, A);
  await insideTheApp(page);
  await page.goto('/inventory/products');
  await productsReady(page);
}

/** The product window, opened with `open` and presented: only then does it take Back or any other way out (hub#1023: a
 *  press on a window Ionic is still loading went to the screen behind it). */
const presented = (page: Page, open: () => Promise<void>): Promise<Locator> => presentedDialog(page, 'inventory-product-form', open);

const newProduct = (page: Page): Promise<Locator> =>
  presented(page, () => shown(page).locator('[data-testid=inventory-products-add]').click());

/** A way out of the window, as the person takes it. */
type Way = [string, (form: Locator, page: Page) => Promise<void>];
const WAYS: Way[] = [
  ['Cancel', (form) => form.locator('[data-testid=inventory-product-form-cancel]').click()],
  ['×', (form) => form.locator('[data-testid=inventory-product-form-close]').click()],
  ['Escape', (_form, page) => page.keyboard.press('Escape')],
  // Above the card on a wide screen, above the sheet on a phone: the window's backdrop.
  ['a tap outside', (_form, page) => page.mouse.click(8, 8)],
];

/** Products in the browser: the window's own ways out need no installed app. */
async function products(page: Page): Promise<void> {
  await login(page, A);
  await page.goto('/inventory/products');
  await productsReady(page);
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
    await capture(page, `INVENTORY-F01-back-asks-${vp.label}`);

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

  const form = await presented(page, () => rowAction(page, tea.id, 'edit'));
  await expect(form).toContainText(/(Editing product|Editando producto) — E2E Back tea/);
  await pressBack(page);
  await expect(form).toBeHidden();
  await noQuestion(page);

  await presented(page, () => rowAction(page, tea.id, 'edit'));
  await fill(form, 'inventory-product-name', 'E2E Back green tea');
  await pressBack(page);
  const asked = question(page);
  await expect(asked).toBeVisible();
  await expect(form).toBeVisible();
  await capture(page, 'INVENTORY-F02-back-asks-390');
  await asked.locator('.ep-form-modal__submit').click();
  await expect(form).toBeHidden();
  await expect(page).toHaveURL(`${A}/inventory/products`);
  expect((await productBySku(context, sku)).name).toBe('E2E Back tea');
});

for (const vp of VIEWPORTS) {
  test(`INVENTORY-F01 ${vp.label}: Cancel, ×, Escape and a tap outside on «New product» ask first with something typed, and close it at once as it opened`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await products(page);
    const form = await newProduct(page);
    const name = form.locator('[data-testid=inventory-product-name] input');
    await fill(form, 'inventory-product-name', 'E2E Cancel coffee');

    for (const [way, leave] of WAYS) {
      await leave(form, page);
      const asked = question(page);
      await expect(asked, way).toBeVisible();
      await expect(asked, way).toContainText(QUESTION);
      await expect(asked.locator('.ep-form-modal__cancel'), way).toHaveText(/^\s*(Keep editing|Seguir editando)\s*$/);
      await expect(asked.locator('.ep-form-modal__submit'), way).toHaveText(/^\s*(Discard changes|Descartar cambios)\s*$/);
      await expect(form, way).toBeVisible();
      if (way === 'Cancel') await capture(page, `INVENTORY-F01-cancel-asks-${vp.label}`);

      await asked.locator('.ep-form-modal__cancel').click();
      await expect(asked, way).toBeHidden();
      await expect(form, way).toBeVisible();
      await expect(name, way).toHaveValue('E2E Cancel coffee');
    }

    // «Discard changes» closes it, and only once: no second question behind the first.
    await form.locator('[data-testid=inventory-product-form-cancel]').click();
    await question(page).locator('.ep-form-modal__submit').click();
    await expect(form).toBeHidden();
    await noQuestion(page);
    await expect(page).toHaveURL(`${A}/inventory/products`);

    // Thrown away: «New product» opens empty again, and every way out of it closes it at once.
    for (const [way, leave] of WAYS) {
      const again = await newProduct(page);
      await expect(again.locator('[data-testid=inventory-product-name] input'), way).toHaveValue('');
      await leave(again, page);
      await expect(again, way).toBeHidden();
      await noQuestion(page);
    }
  });
}

test('INVENTORY-F02 390: «Cancel editing» on «Editing product» closes it as saved; with a change it asks, and «Discard changes» saves nothing', async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const sku = `E2E-CANCEL-EDIT-${stamp()}`;
  await products(page);
  const tea = await createProduct(context, { name: 'E2E Cancel tea', sku, price: 250 });
  await searchProducts(page, sku);
  const cancelEdit = (form: Locator) => form.locator('[data-testid=inventory-product-form-cancel]');

  const form = await presented(page, () => rowAction(page, tea.id, 'edit'));
  await expect(form).toContainText(/(Editing product|Editando producto) — E2E Cancel tea/);
  await expect(cancelEdit(form)).toHaveText(/^\s*(Cancel editing|Cancelar edición)\s*$/);
  await cancelEdit(form).click();
  await expect(form).toBeHidden();
  await noQuestion(page);

  await presented(page, () => rowAction(page, tea.id, 'edit'));
  await fill(form, 'inventory-product-name', 'E2E Cancel green tea');
  await cancelEdit(form).click();
  const asked = question(page);
  await expect(asked).toBeVisible();
  await expect(asked).toContainText(QUESTION);
  await expect(form).toBeVisible();
  await capture(page, 'INVENTORY-F02-cancel-edit-asks-390');
  await asked.locator('.ep-form-modal__submit').click();
  await expect(form).toBeHidden();
  await noQuestion(page);
  expect((await productBySku(context, sku)).name).toBe('E2E Cancel tea');
});
