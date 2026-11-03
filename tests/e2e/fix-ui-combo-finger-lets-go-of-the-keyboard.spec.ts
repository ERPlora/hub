// hub#537 — on a tablet (Lenovo TB361FU, Android, landscape), Menus and combos › «New menu»: after choosing the
// «VAT category» in its list with a finger, the field kept the focus and the on-screen keyboard stayed up, and the
// first tap on «Save» did not save (a second one did). A choice made with a finger now lets go of the focus, so the
// keyboard goes away (MUI Autocomplete's `blurOnSelect="touch"`), and it stays away once Ionic has closed the list
// (Ionic 8 gives the focus back, once a popover is gone, to what had it when it showed: the field). With a mouse the
// focus stays in the field, to go on with Tab. In Chrome with touch emulated (taps: pointerType `touch`), against hub
// `a` and the real Taxes app; the bench has no on-screen keyboard, so the focus is what is measured. Nothing is
// created but the menus, named «E2E VAT finger …» and removed before and after.
// flow: COMBO-F02, ui:Combo
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, login, psql, shown } from './helpers';

const TAG = 'E2E VAT finger';
const VIEWPORTS = [
  { label: '1280x800', width: 1280, height: 800 },
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];
const FIELD = 'combo-menu-form-tax_category';

function cleanUp(): void {
  psql(`delete from combo_combo where name like '${TAG}%'`);
}

test.describe.configure({ mode: 'serial' });
test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function ownerPage(browser: Browser, viewport: { width: number; height: number }, hasTouch: boolean) {
  const context = await browser.newContext({ baseURL: A, viewport, hasTouch, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/combo/menus');
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

/** Opens «New menu», names it and returns the form, the VAT category's input and the name. */
async function newMenu(page: Page, label: string, touch: boolean) {
  await shown(page).locator('[data-testid=combo-menus-row], [data-testid=combo-menus-empty]').first().waitFor();
  const add = shown(page).locator('[data-testid=combo-menus-add]');
  if (touch) await add.tap();
  else await add.click();
  const form = page.locator('ion-modal[data-testid=combo-menu-form]');
  await expect(form).toBeVisible();
  const name = `${TAG} ${label} ${Date.now().toString(36)}`;
  await page.locator('[data-testid=combo-menu-form-name] input').fill(name);
  return { form, input: page.locator(`[data-testid=${FIELD}] input`), name };
}

/** «Restaurant — food» among the options found for «food», once the search has answered. */
async function foodOption(page: Page) {
  const food = page.locator(`[data-testid^=${FIELD}-option-]`).filter({ hasText: 'Restaurant — food' }).first();
  await expect(food).toBeVisible();
  await expect(page.locator(`[data-testid=${FIELD}-loading]`)).toHaveCount(0);
  return food;
}

/** Ionic has closed the list (`overlay-hidden`): its focus restore (a microtask after its `didDismiss`) is done. */
async function listGone(page: Page): Promise<void> {
  await expect(page.locator('ion-popover.combo__popover:not(.overlay-hidden)')).toHaveCount(0);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 50))));
}

const fieldFocused = (page: Page): Promise<boolean> =>
  page.evaluate((testid) => document.activeElement === document.querySelector(`[data-testid=${testid}] input`), FIELD);

const savedCategory = (name: string): string =>
  psql(`select coalesce(t.key, '') from combo_combo c left join tax_taxcategory t on t.id = c.tax_category_id where c.name = '${name}'`);

for (const vp of VIEWPORTS) {
  test(`COMBO-F02 / ui:Combo — a finger choosing the VAT category lets go of the keyboard, and one tap on Save saves (${vp.label})`, async ({
    browser,
  }) => {
    const { context, page } = await ownerPage(browser, { width: vp.width, height: vp.height }, true);
    try {
      const { form, input, name } = await newMenu(page, vp.label, true);

      // A finger on the field, «food» typed, a finger on «Restaurant — food».
      await input.tap();
      await expect(input).toHaveAttribute('aria-expanded', 'true');
      await input.fill('food');
      const food = await foodOption(page);
      await food.tap();
      await expect(input).toHaveValue(/Restaurant — food/);
      await expect(input).toHaveAttribute('aria-expanded', 'false');

      // The field has let go of the focus (the keyboard goes away), and Ionic closing the list does not give it back.
      await listGone(page);
      expect(await fieldFocused(page), 'the field keeps the focus after a finger chose: the keyboard would stay up').toBe(false);
      await capture(page, `HUB-537-vat-chosen-by-finger-${vp.label}`);

      // One tap on Save saves: the form closes and the menu keeps «Restaurant — food».
      await page.locator('[data-testid=combo-menu-form-submit]').tap();
      await expect(form).toBeHidden();
      await expect.poll(() => savedCategory(name)).toBe('restaurant.food');
      await expect(shown(page).locator('[data-testid=combo-menus-row]').filter({ hasText: name })).toBeVisible();
      await capture(page, `HUB-537-menu-saved-${vp.label}`);
    } finally {
      await context.close();
    }
  });
}

test('COMBO-F02 / ui:Combo — with a mouse the focus stays in the VAT category field, to go on with Tab (1280x800)', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, { width: 1280, height: 800 }, false);
  try {
    const { form, input, name } = await newMenu(page, 'mouse', false);
    await input.click();
    await input.fill('food');
    const food = await foodOption(page);
    await food.click();
    await expect(input).toHaveValue(/Restaurant — food/);
    await listGone(page);
    expect(await fieldFocused(page), 'a mouse choice keeps the focus in the field').toBe(true);

    await page.locator('[data-testid=combo-menu-form-submit]').click();
    await expect(form).toBeHidden();
    await expect.poll(() => savedCategory(name)).toBe('restaurant.food');
  } finally {
    await context.close();
  }
});
