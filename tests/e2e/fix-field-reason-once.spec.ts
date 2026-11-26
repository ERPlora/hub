// flow: CASH_REGISTER-F02, TABLE-F08, BASE-F127
// hub#2535: the reason the server gives for one field is said once, under that field, in the three places where it was
// seen twice (a drawer named like another one, a red warning before the amber one, a role duplicated with the name of
// another role), in English and in Spanish, at the phone, the tablet and the desktop. Nothing is saved: every save is
// refused, and the drawer and the role the spec makes are deleted after it.
import { writeFileSync } from 'node:fs';

import { type Browser, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, psql, shown, signedInSpanish, turnOffTurnedOn, turnOnMissing, uniqueName } from './helpers';
import { dialog } from './inventory-helpers';
import { ownerPage, rowAction } from './service-helpers';
import { discardChanges } from './unsaved-back-helpers';

const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '820', width: 820, height: 1180 },
  { label: '1280', width: 1280, height: 720 },
] as const;
const LANGUAGES = ['en', 'es'] as const;
type Language = (typeof LANGUAGES)[number];

const DRAWER_TAKEN = { en: 'There is already a drawer with that name.', es: 'Ya hay un cajón con ese nombre.' };
const RED_BEFORE_AMBER = { en: 'The red warning cannot come before the amber one.', es: 'El aviso rojo no puede llegar antes que el ámbar.' };
const ROLE_TAKEN = { en: 'There is already a role with that name. Choose another.', es: 'Ya hay un rol con ese nombre. Elige otro.' };

/** The apps the three places need, in the order they can be turned on. */
const NEEDED = ['customer', 'tax', 'sale', 'cash_register', 'table'];
const turnedOn: string[] = [];
const DRAWER = uniqueName('E2E2535 Barra');

test.beforeAll(async ({ browser }) => {
  const { context } = await ownerPage(browser, '/');
  try {
    await turnOnMissing(context, A, NEEDED, turnedOn);
    const created = await api(context, A, 'POST', '/cash_register/registers', { name: DRAWER });
    expect(created.status, JSON.stringify(created.data)).toBe(201);
  } finally {
    await context.close();
  }
});

test.afterAll(async ({ browser }) => {
  psql(`delete from cash_register_register where name = '${DRAWER}'`);
  const { context } = await ownerPage(browser, '/');
  await turnOffTurnedOn(context, A, turnedOn).finally(() => context.close());
});

async function signedIn(browser: Browser, language: Language, path: string): Promise<{ page: Page; close: () => Promise<void> }> {
  const viewport = { width: SIZES[2].width, height: SIZES[2].height };
  const { context, page } = language === 'en' ? await ownerPage(browser, path, viewport) : await signedInSpanish(browser, viewport, path);
  return { page, close: () => context.close() };
}

/** Where a box sits, in whole pixels. */
const at = (box: { x: number; y: number; width: number; height: number }) => ({
  x: Math.round(box.x),
  y: Math.round(box.y),
  width: Math.round(box.width),
  height: Math.round(box.height),
});

/**
 * `field` is marked with `reason` under its own input, and `reason` is on screen once in `scope`: `notice`, the red box
 * of the window or of the page, is not there. Measured, and captured, at each of the three sizes.
 */
async function saidOnceUnder(page: Page, scope: Locator, field: Locator, notice: Locator, reason: string, name: string): Promise<void> {
  const under = field.locator('.error-text');
  await expect(field).toHaveClass(/ion-invalid/);
  await expect(under).toHaveText(reason);
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await field.scrollIntoViewIfNeeded();
    await expect(notice).toHaveCount(0);
    await expect(scope.getByText(reason, { exact: true })).toHaveCount(1);
    const input = await field.locator('input').boundingBox();
    const text = await under.boundingBox();
    expect(input, `${name} at ${size.label}: the field is on screen`).not.toBeNull();
    expect(text, `${name} at ${size.label}: its reason is on screen`).not.toBeNull();
    if (!input || !text) return;
    expect(text.y, `${name} at ${size.label}: the reason sits under the input`).toBeGreaterThanOrEqual(input.y + input.height - 1);
    expect(text.x + text.width, `${name} at ${size.label}: the reason fits the screen`).toBeLessThanOrEqual(size.width);
    test.info().annotations.push({ type: `box ${name} ${size.label}`, description: JSON.stringify({ input: at(input), reason: at(text) }) });
    writeFileSync(test.info().outputPath(`hub2535-${name}-${size.label}.png`), await page.screenshot());
  }
}

for (const language of LANGUAGES) {
  test(`hub#2535 CASH_REGISTER-F02 (${language}): a drawer named like another one says why once, under the name`, async ({ browser }) => {
    const { page, close } = await signedIn(browser, language, '/cash_register/settings');
    try {
      await shown(page).locator('[data-testid=cash-register-registers-heading]').scrollIntoViewIfNeeded();
      await shown(page).locator('[data-testid=cash-register-registers-add]').click();
      const modal = dialog(page, 'cash-register-register');
      const name = modal.locator('[data-testid=cash-register-register-name]');
      await name.locator('input').fill(DRAWER.toLowerCase());
      await modal.locator('[data-testid=cash-register-register-submit]').click();
      await saidOnceUnder(page, modal, name, modal.locator('[data-testid=cash-register-register-error]'), DRAWER_TAKEN[language], `drawer-${language}`);
      await modal.locator('[data-testid=cash-register-register-cancel]').click();
      await discardChanges(page);
      await expect(modal).toBeHidden();
      expect(psql(`select count(*) from cash_register_register where lower(name) = lower('${DRAWER}')`)).toBe('1');
    } finally {
      await close();
    }
  });

  test(`hub#2535 TABLE-F08 (${language}): a red warning before the amber one says why once, under «Red warning»`, async ({ browser }) => {
    const { page, close } = await signedIn(browser, language, '/table/settings');
    try {
      const form = shown(page).locator('[data-testid=table-settings]');
      const amber = form.locator('[data-testid=table-settings-timer_warning_minutes]');
      const red = form.locator('[data-testid=table-settings-timer_critical_minutes]');
      const before = psql('select timer_warning_minutes, timer_critical_minutes from table_tablesettings');
      await amber.locator('input').fill('45');
      await red.locator('input').fill('30');
      await form.locator('[data-testid=table-settings-save]').click();
      await saidOnceUnder(page, form, red, form.locator('[data-testid=table-settings-save-error]'), RED_BEFORE_AMBER[language], `table-${language}`);
      expect(psql('select timer_warning_minutes, timer_critical_minutes from table_tablesettings')).toBe(before);
    } finally {
      await close();
    }
  });

  test(`hub#2535 BASE-F127 (${language}): a role duplicated with the name of another role says why once, under the name`, async ({ browser }) => {
    const { page, close } = await signedIn(browser, language, '/employees#roles');
    const taken = uniqueName('E2E2535 Caja');
    const own = await api<{ key: string }>(page.context(), A, 'POST', '/roles', { based_on: 'hub_employee', name: taken });
    expect(own.status, JSON.stringify(own.data)).toBe(200);
    try {
      await page.reload();
      await rowAction(page, 'roles', 'hub_employee', 'duplicate');
      const modal = dialog(page, 'role-new');
      const name = modal.locator('[data-testid=role-new-name]');
      await name.locator('input').fill(taken.toLowerCase());
      await modal.locator('[data-testid=role-new-submit]').click();
      await saidOnceUnder(page, modal, name, modal.locator('[data-testid=role-new-error]'), ROLE_TAKEN[language], `role-${language}`);
    } finally {
      await api(page.context(), A, 'POST', '/roles/delete', { role: own.data.key });
      await close();
    }
  });
}
