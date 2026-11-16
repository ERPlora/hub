// flow: CASH_REGISTER-F02, CASH_REGISTER-F03, CASH_REGISTER-F05 — hub#1470: in Cash register a refused field loses its
// mark as soon as it is corrected, without saving again, and only its own. Seen in Settings › Drawers (a name another
// drawer has) and in «Open session» (the float this business requires), both refused by the server, and in a shift's
// «Movement», refused in the browser for three fields with the same words, at 390, 834 and 1440, and once more in
// Spanish, whose session the fleet's visual sweep reads. Nothing is created.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, capture, login, psql, shown } from './helpers';
import { dialog } from './inventory-helpers';
import { stamp } from './sale-helpers';
import { expectMarked, expectUnmarked, refuseWithTheSameWords, testEachSameWordsCase } from './same-words-helpers';
import { discardChanges } from './unsaved-back-helpers';

const DRAWER = `E2E1470 Bar ${stamp()}`;
const TAKEN = { en: 'There is already a drawer with that name.', es: 'Ya hay un cajón con ese nombre.' };
const FLOAT_REQUIRED = {
  en: 'This business requires an opening float: give the cash the drawer starts with.',
  es: 'Este negocio exige fondo de apertura: indica el efectivo con el que empieza la caja.',
};
const SAME_WORDS = { en: 'Check this field.', es: 'Revisa este campo.' };

type Language = keyof typeof TAKEN;

/** The session this file opens for the movement window: the only one its cleanup deletes. */
let session = '';
let floatRequiredBefore: unknown;

async function owner(context: BrowserContext, path: string): Promise<void> {
  await login(await context.newPage(), A, path);
}

async function openSession(context: BrowserContext): Promise<{ id: string; expected_balance: number | null } | null> {
  return (await api<{ session: { id: string; expected_balance: number | null } | null }>(context, A, 'GET', '/cash_register/sessions/current')).data.session;
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  await owner(context, '/cash_register/settings');
  const created = await api(context, A, 'POST', '/cash_register/registers', { name: DRAWER });
  expect(created.status, JSON.stringify(created.data)).toBe(201);
  floatRequiredBefore = (await api<Record<string, unknown>>(context, A, 'GET', '/cash_register/settings')).data.require_opening_balance;
  await api(context, A, 'POST', '/cash_register/settings', { require_opening_balance: true });
  const left = await openSession(context);
  if (left) await api(context, A, 'POST', '/cash_register/sessions/close', { session_id: left.id, closing_balance: Math.max(left.expected_balance ?? 0, 0) });
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  await owner(context, '/cash_register/settings');
  await api(context, A, 'POST', '/cash_register/settings', { require_opening_balance: floatRequiredBefore });
  await context.close();
  if (session) {
    psql(`delete from cash_register_movement where session_id = '${session}'`);
    psql(`delete from cash_register_session where id = '${session}'`);
  }
  psql(`delete from cash_register_register where name like '${DRAWER}%'`);
});

/** `field` (an Ionic field's host) typed again: what it held and `more`. */
async function typeMore(field: Locator, more: string): Promise<void> {
  const input = field.locator('input');
  await input.fill(`${await input.inputValue()}${more}`);
}

async function drawerNameTaken(page: Page, language: Language, label: string): Promise<void> {
  await shown(page).locator('[data-testid=cash-register-registers-heading]').scrollIntoViewIfNeeded();
  await shown(page).locator('[data-testid=cash-register-registers-add]').click();
  const modal = dialog(page, 'cash-register-register');
  const name = modal.locator('[data-testid=cash-register-register-name]');
  await name.locator('input').fill(DRAWER.toLowerCase());
  await modal.locator('[data-testid=cash-register-register-submit]').click();
  await expectMarked(name, TAKEN[language]);
  await expect(modal.locator('[data-testid=cash-register-register-error]')).toBeVisible();
  await capture(page, `CLOSE-CASH_REGISTER-hub1470-drawer-refused-${label}`);

  await typeMore(name, ' 2');
  await expectUnmarked(name, TAKEN[language]);
  await expect(modal.locator('[data-testid=cash-register-register-error]')).toBeHidden();
  await capture(page, `CLOSE-CASH_REGISTER-hub1470-drawer-typed-${label}`);

  await modal.locator('[data-testid=cash-register-register-cancel]').click();
  await discardChanges(page);
  await expect(modal).toBeHidden();
}

async function floatRequired(page: Page, language: Language, label: string): Promise<void> {
  await shown(page).locator('[data-testid=cash-register-new-session]').click();
  const modal = dialog(page, 'cash-register-open');
  const balance = modal.locator('[data-testid=cash-register-open-balance]');
  const notes = modal.locator('[data-testid=cash-register-open-notes]');
  await notes.locator('input').fill('E2E1470');
  await modal.locator('[data-testid=cash-register-open-submit]').click();
  await expectMarked(balance, FLOAT_REQUIRED[language]);
  await expect(modal.locator('[data-testid=cash-register-open-error]')).toBeVisible();
  await capture(page, `CLOSE-CASH_REGISTER-hub1470-float-refused-${label}`);

  await typeMore(balance, '50');
  await expectUnmarked(balance, FLOAT_REQUIRED[language]);
  await expect(modal.locator('[data-testid=cash-register-open-error]')).toBeHidden();
  await capture(page, `CLOSE-CASH_REGISTER-hub1470-float-typed-${label}`);

  await modal.locator('[data-testid=cash-register-open-cancel]').click();
  await discardChanges(page);
  await expect(modal).toBeHidden();
  expect(psql("select count(*) from cash_register_session where status = 'open'")).toBe('0');
}

async function movementOneByOne(page: Page, language: Language, label: string): Promise<void> {
  const words = SAME_WORDS[language];
  await shown(page).locator(`[data-testid=cash-register-sessions-row-${session}-movement]`).first().click();
  const modal = dialog(page, 'cash-register-movement');
  const [type, amount, concept] = ['type', 'amount', 'concept'].map((key) => modal.locator(`[data-testid=cash-register-movement-${key}]`));
  await amount.locator('input').fill('20');
  await concept.locator('input').fill('E2E1470');

  await refuseWithTheSameWords(page, '**/api/cash_register/movements', ['type', 'amount', 'description'], words);
  await modal.locator('[data-testid=cash-register-movement-submit]').click();
  for (const field of [type, amount, concept]) await expect(field).toHaveClass(/ion-invalid/);
  await expectMarked(amount, words);
  await expectMarked(concept, words);
  await capture(page, `CLOSE-CASH_REGISTER-hub1470-movement-refused-${label}`);

  await typeMore(amount, '1');
  await expectUnmarked(amount, words);
  await expectMarked(concept, words);
  await expect(type).toHaveClass(/ion-invalid/);
  await typeMore(concept, ' 2');
  await expectUnmarked(concept, words);
  await expect(type).toHaveClass(/ion-invalid/);
  await capture(page, `CLOSE-CASH_REGISTER-hub1470-movement-typed-${label}`);

  await page.unroute('**/api/cash_register/movements');
  await modal.locator('[data-testid=cash-register-movement-cancel]').click();
  await discardChanges(page);
  await expect(modal).toBeHidden();
  expect(psql(`select count(*) from cash_register_movement where session_id = '${session}'`)).toBe('0');
}

testEachSameWordsCase(
  ({ size }) => `hub#1470 CASH_REGISTER-F02 at ${size.label}: a drawer name another drawer has loses its mark once typed again`,
  '/cash_register/settings',
  (page, { language, size }) => drawerNameTaken(page, language, size.label),
);

testEachSameWordsCase(
  ({ size }) => `hub#1470 CASH_REGISTER-F03 at ${size.label}: the float the business requires loses its mark once typed`,
  '/cash_register/sessions',
  (page, { language, size }) => floatRequired(page, language, size.label),
);

test.describe('with a shift open', () => {
  test.beforeAll(async ({ browser }) => {
    const context = await browser.newContext({ baseURL: A });
    await owner(context, '/cash_register/sessions');
    const opened = await api<{ id: string }>(context, A, 'POST', '/cash_register/sessions/open', { opening_balance: 10000 });
    expect(opened.status, JSON.stringify(opened.data)).toBe(201);
    session = opened.data.id;
    await context.close();
  });

  testEachSameWordsCase(
    ({ size }) => `hub#1470 CASH_REGISTER-F05 at ${size.label}: three fields refused with the same words, each corrected loses only its own`,
    '/cash_register/sessions',
    (page, { language, size }) => movementOneByOne(page, language, size.label),
  );
});
