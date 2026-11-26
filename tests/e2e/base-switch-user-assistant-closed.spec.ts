// flow: BASE-F102 BASE-F60 BASE-F92
// On a shared till, with the assistant's panel open and a conversation in it, whoever enters next finds the panel
// closed and empty, and opening it starts from nothing: after «Switch user» (with a PIN or a badge), after signing out
// and after the till locked by itself. Whoever does not switch finds it as they left it, also after reloading. A business of its own, signed up on the SaaS's screens, with its
// owner and an employee: a PIN in the hubs `a` or `b` would change every other spec's way in. The stack's fake
// provider answers the panel (README of this folder, «El asistente»).
import { expect, type Page, test } from '@playwright/test';

import { pressPin, userMenu } from './access-door';
import { VIEWPORTS } from './assistant-card-helpers';
import { ask, lastAnswer, openPanel, panel } from './assistant-panel';
import { GREETING } from './assistant-provider';
import { api, capture, login, psql, shown } from './helpers';
import { panelSpec } from './provider-helpers';
import { businessOnSaas, joinsAsEmployee, type SaasBusiness, type SaasOwner, signUpOnSaas } from './saas-owner';
import { STACK } from './stack';

panelSpec();

const OWNER_PIN = '4826';
const EMPLOYEE_PIN = '9071';
/** A card's number, one per run: a badge opens one person's door only. */
const BADGE = `78${String(Date.now()).slice(-8)}`;
/** The three sizes, and the QA's tablet in landscape, where the panel takes a third of the screen. */
const SIZES = [...VIEWPORTS, { label: '1280x720', width: 1280, height: 720 }];

test.describe.configure({ mode: 'serial' });

let owner: SaasOwner;
let employee: SaasOwner;
let business: SaasBusiness;
let origin: string;
let till: Page;

const usernameOf = (email: string): string => psql(`SELECT username FROM auth_user WHERE email = '${email}'`);

/** The name the session gives the person in hand (`base.session.me`). */
async function whoIsIn(page: Page): Promise<string | null> {
  const me = await api<{ user: { email?: string; label: string } | null }>(page.context(), origin, 'GET', '/me');
  return me.data.user?.label ?? null;
}

/** The panel open on the till with a question answered: the conversation of whoever is in. */
async function conversationOpen(page: Page): Promise<void> {
  await page.setViewportSize({ width: 1280, height: 720 });
  await openPanel(page);
  await ask(page, 'Hola');
  await expect(lastAnswer(page)).toHaveText(GREETING.en);
}

/** Right after the switch: the panel closed at every size; opened, it starts from nothing. */
async function closedAndEmpty(page: Page, key: string): Promise<void> {
  for (const { label, width, height } of SIZES) {
    await page.setViewportSize({ width, height });
    await expect(panel(page)).toHaveAttribute('data-open', 'false');
    await capture(page, `hub-2604-${key}-closed-${label}`);
    // Nothing of the panel takes the screen's side: the screen has all of its width.
    const screen = await page.locator('ion-app > ion-split-pane').boundingBox();
    expect(Math.round(screen!.width), `the screen's width at ${label}`).toBe(width);
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await openPanel(page);
  await expect(panel(page).locator('[data-testid="assistant-empty"]')).toBeVisible();
  await expect(panel(page).locator('[data-testid="assistant-bubble-user"]')).toHaveCount(0);
  await capture(page, `hub-2604-${key}-opened-empty-1280x720`);
}

test.beforeAll(async ({ browser }) => {
  owner = await signUpOnSaas(browser, 'switch-panel-owner');
  employee = await signUpOnSaas(browser, 'switch-panel-employee');
  business = await businessOnSaas(owner, { name: `Switch panel ${Date.now().toString(36)}`, country: 'ES' });
  await joinsAsEmployee(owner, employee, business);
  origin = STACK.hub(business.slug);
  // The owner, first in, gives themselves a PIN and a badge; the employee, entering after, is asked for theirs. One
  // device at a time on the Free plan: the till signs in again, with the owner's PIN.
  await login(owner.page, origin, '/', owner.credentials);
  const pin = await api<{ set: boolean }>(owner.context, origin, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
  const badge = await api(owner.context, origin, 'POST', '/people/badge', { person: usernameOf(owner.credentials.email), badge: BADGE });
  expect(badge.status, JSON.stringify(badge.data)).toBe(200);
  const theirs = employee.page;
  await theirs.goto(`${origin}/`);
  await expect(theirs).toHaveURL(`${origin}/pin/setup?next=%2F`, { timeout: 30_000 });
  await pressPin(theirs, EMPLOYEE_PIN);
  await expect(shown(theirs).getByTestId('pin-setup-step')).toHaveText('Confirm your PIN');
  await pressPin(theirs, EMPLOYEE_PIN);
  await expect(theirs).toHaveURL(`${origin}/`);
  till = owner.page;
  await till.goto(`${origin}/`);
  await expect(till).toHaveURL(/\/login(\?|$)/);
  await shown(till).getByTestId('pin-face').filter({ hasText: 'e2e-switch-panel-owner' }).click();
  await pressPin(till, OWNER_PIN);
  await expect(till).toHaveURL(`${origin}/`);
});

test.afterAll(async () => {
  // The till's session, for a sweep of its screens (as base-access-pinpad-fit.spec.ts saves it).
  if (process.env.E2E_SAVE_STORAGE_STATE) await owner?.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await owner?.context.close();
  await employee?.context.close();
});

test('BASE-F92: whoever does not switch finds the panel as they left it, also after reloading', async () => {
  await conversationOpen(till);
  await till.reload();
  await expect(panel(till)).toHaveAttribute('data-open', 'true');
  await expect(panel(till).locator('[data-testid="assistant-bubble-user"]')).toHaveText(['Hola']);
});

test('BASE-F102: whoever takes over with their PIN finds the panel closed and empty', async () => {
  await expect(panel(till)).toHaveAttribute('data-open', 'true');
  await userMenu(till, 'switch-user');
  await expect(till).toHaveURL(`${origin}/switch-user`);
  await shown(till).getByTestId('pin-face').filter({ hasText: 'e2e-switch-panel-employee' }).click();
  await pressPin(till, EMPLOYEE_PIN);
  await expect(till).toHaveURL(`${origin}/`);
  expect(await whoIsIn(till)).toMatch(/e2e-switch-panel-employee/);
  await closedAndEmpty(till, 'pin');
});

test('BASE-F102: whoever takes over with their badge finds the panel closed and empty', async () => {
  await conversationOpen(till);
  await userMenu(till, 'switch-user');
  await expect(till).toHaveURL(`${origin}/switch-user`);
  await expect(shown(till).getByTestId('pin-face').first()).toBeVisible();
  await till.keyboard.type(BADGE, { delay: 5 });
  await till.keyboard.press('Enter');
  await expect(till).toHaveURL(`${origin}/`);
  expect(await whoIsIn(till)).toMatch(/e2e-switch-panel-owner/);
  await closedAndEmpty(till, 'badge');
});

test('BASE-F102: after signing out of the till, whoever enters next with their PIN finds the panel closed and empty', async () => {
  await conversationOpen(till);
  await userMenu(till, 'logout');
  await expect(till).toHaveURL(/\/login(\?|$)/);
  await shown(till).getByTestId('pin-face').filter({ hasText: 'e2e-switch-panel-employee' }).click();
  await pressPin(till, EMPLOYEE_PIN);
  await expect(till).toHaveURL(`${origin}/`);
  expect(await whoIsIn(till)).toMatch(/e2e-switch-panel-employee/);
  await closedAndEmpty(till, 'sign-out');
});

test('BASE-F102: after the till locked by itself, whoever enters next with their PIN finds the panel closed and empty', async () => {
  // A business that asks always, after a minute without use; the page loaded again reads it.
  psql("UPDATE base_accesssettings SET pin_policy = 'always', pin_inactivity_minutes = 1", business.slug);
  await till.goto(`${origin}/`);
  await conversationOpen(till);
  await till.clock.install();
  await till.reload();
  await expect(panel(till)).toHaveAttribute('data-open', 'true');
  await till.clock.fastForward('01:05');
  await expect(till).toHaveURL(/\/login(\?|$)/, { timeout: 60_000 });
  await shown(till).getByTestId('pin-face').filter({ hasText: 'e2e-switch-panel-owner' }).click();
  await pressPin(till, OWNER_PIN);
  await expect(till).toHaveURL(`${origin}/`);
  expect(await whoIsIn(till)).toMatch(/e2e-switch-panel-owner/);
  await closedAndEmpty(till, 'idle');
});
