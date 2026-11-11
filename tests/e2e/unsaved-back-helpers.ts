// BASE-F05: one create window of an app, as the person reaches it. The installed app's Back is simulated at the edge;
// every screen, form and confirmation is real. Nothing is saved: the dirty form asks, keeps what was typed on a second
// Back, closes only on «Discard changes», opens blank again and closes cleanly when untouched, in three sizes.
// `expectWaysOutAskOnDirtyForm` walks the window's own ways out the same way (hub#1156): «Cancel», the «×», Escape and
// a tap outside, in the browser, with no installed app.
import { expect, type Locator, type Page } from '@playwright/test';

import { A, capture, login, shown } from './helpers';
import { presentedDialog } from './inventory-helpers';
import { insideTheApp, pressBack } from './system-back-helpers';

export interface UnsavedFormCase {
  app: string;
  flow: string;
  /** The screen that opens the window. */
  route: string;
  /** The button that opens it (its `data-testid`), or what opens it on the screen when it is not a button (a row). */
  add: string | ((page: Page) => Locator);
  /** The window's `data-testid`. */
  form: string;
  /** A text field of it, which opens blank. */
  field: string;
  /** What is typed in it; a plain text unless the field asks for another. */
  value?: string;
}

const VIEWPORTS = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];

/** «Discard changes?»: base's question (ConfirmDialog), on top of the window; the newest one (a closed one stays parked
 *  hidden). Ionic moves its name and role into its shadow DOM, so it is found by its class and its words. */
export const question = (page: Page): Locator => page.locator('ion-modal.ep-confirm-dialog').last();
/** Its title, in either language. */
export const QUESTION = /Discard changes\?|¿Descartar los cambios\?/;
/** No question on screen. */
export const noQuestion = (page: Page) => expect(page.locator('ion-modal.ep-confirm-dialog:visible')).toHaveCount(0);

/** `shots` names the captures of the question (`<shots>-<app>-<size>`). */
export async function expectBackAsksOnDirtyForm(page: Page, item: UnsavedFormCase, shots: string): Promise<void> {
  await login(page, A);
  await insideTheApp(page);
  await page.goto(item.route);
  const add = typeof item.add === 'string' ? shown(page).locator(`[data-testid=${item.add}]`) : item.add(page);
  await expect(add).toBeVisible();
  const form = page.locator(`ion-modal[data-testid=${item.form}]`);
  const field = form.locator(`[data-testid=${item.field}] input`);
  const value = item.value ?? 'E2E unsaved';

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await add.click();
    await expect(form).toBeVisible();
    await field.fill(value);
    await pressBack(page);
    const asked = question(page);
    await expect(asked).toBeVisible();
    await expect(asked).toContainText(QUESTION);
    await expect(form).toBeVisible();
    await capture(page, `${shots}-${item.app}-${viewport.label}`);

    await pressBack(page);
    await expect(asked).toBeHidden();
    await expect(form).toBeVisible();
    await expect(field).toHaveValue(value);

    await pressBack(page);
    await asked.locator('.ep-form-modal__submit').click();
    await expect(form).toBeHidden();

    await add.click();
    await expect(form).toBeVisible();
    await expect(field).toHaveValue('');
    await pressBack(page);
    await expect(form).toBeHidden();
    await noQuestion(page);
  }
  if (process.env.E2E_SAVE_STORAGE_STATE) await page.context().storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
}

/** A way out of the window, as the person takes it. */
type Way = [string, (form: Locator, page: Page) => Promise<void>];

/** «Cancel» and the «×» of its FormModal (`<form>-cancel`, `<form>-close`), Escape and — when a tap outside closes it —
 *  a tap above the card on a wide screen, above the sheet on a phone. */
async function waysOut(form: Locator, item: UnsavedFormCase): Promise<Way[]> {
  const ways: Way[] = [
    ['Cancel', (f) => f.locator(`[data-testid=${item.form}-cancel]`).click()],
    ['×', (f) => f.locator(`[data-testid=${item.form}-close]`).click()],
    ['Escape', (_f, page) => page.keyboard.press('Escape')],
  ];
  if (await form.evaluate((el) => (el as HTMLElement & { backdropDismiss?: boolean }).backdropDismiss !== false)) {
    ways.push(['a tap outside', (_f, page) => page.mouse.click(8, 8)]);
  }
  return ways;
}

/** With something typed every way out asks «Discard changes?» and «Keep editing» keeps it; «Discard changes» closes it;
 *  it opens blank again and, untouched, closes at once. `shots` names the captures of the question after «Cancel»
 *  (`<shots>-<app>-<size>`). */
export async function expectWaysOutAskOnDirtyForm(page: Page, item: UnsavedFormCase, shots: string): Promise<void> {
  await login(page, A);
  await page.goto(item.route);
  const add = typeof item.add === 'string' ? shown(page).locator(`[data-testid=${item.add}]`) : item.add(page);
  await expect(add).toBeVisible();
  const open = () => presentedDialog(page, item.form, () => add.click());
  const value = item.value ?? 'E2E unsaved';

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    const form = await open();
    const field = form.locator(`[data-testid=${item.field}] input`);
    await field.fill(value);
    for (const [way, leave] of await waysOut(form, item)) {
      await leave(form, page);
      const asked = question(page);
      await expect(asked, way).toBeVisible();
      await expect(asked, way).toContainText(QUESTION);
      await expect(form, way).toBeVisible();
      if (way === 'Cancel') await capture(page, `${shots}-${item.app}-${viewport.label}`);
      await asked.locator('.ep-form-modal__cancel').click();
      await expect(asked, way).toBeHidden();
      await expect(form, way).toBeVisible();
      await expect(field, way).toHaveValue(value);
    }

    await form.locator(`[data-testid=${item.form}-cancel]`).click();
    await question(page).locator('.ep-form-modal__submit').click();
    await expect(form).toBeHidden();
    await noQuestion(page);

    const again = await open();
    await expect(again.locator(`[data-testid=${item.field}] input`)).toHaveValue('');
    await again.locator(`[data-testid=${item.form}-close]`).click();
    await expect(again).toBeHidden();
    await noQuestion(page);
  }
}
