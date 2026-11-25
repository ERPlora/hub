// The business's API keys from end to end (BASE-F86 create and copy the token, BASE-F89 see the keys and what each
// may do, BASE-F87 rotate, BASE-F88 revoke), in the three viewports, as the owner of hub `a`.
//
// Each viewport makes a key that only reads Inventory, sees its token once and copies it, finds it in the list with what
// it may do and who made it, calls the API with it from a context with no session (only the token opens the door: it
// reads Inventory, and writing there or reading another app is refused), rotates it (the new token works, the old one
// is 401 at once) and revokes it (401 for good, listed as «Revoked» with no actions left). Another key, on all apps,
// creates and reads. What a run made is deleted before and after it, so the other specs find the business as it was.
// flow: BASE-F86 BASE-F87 BASE-F88 BASE-F89
import { type APIRequestContext, type Browser, expect, type Page, test } from '@playwright/test';

import { cutLabels } from './field-labels';
import {
  A,
  api,
  capture,
  collectProblems,
  horizontalOverflow,
  hostPage,
  psql,
  saveSessionForTheSweep,
  shown,
  signedInSpanish,
  untilStill,
} from './helpers';
import { rowAction } from './service-helpers';
import { toastSaying } from './toast-helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** Every key a run of this spec makes is named so, and only those are deleted. */
const PREFIX = 'E2E API key';

/** What a key that only reads Inventory may call there, and what it may not call on another app. */
const CATEGORIES = '/api/inventory/categories';
const TAXES = '/api/tax/categories';

function forgetTheKeys(): void {
  psql(`delete from base_apikey where name like '${PREFIX}%'`);
  psql(`delete from inventory_category where name like '${PREFIX}%'`);
}

test.beforeAll(forgetTheKeys);
test.afterAll(forgetTheKeys);
test.describe.configure({ mode: 'serial' });

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
/** A dialog, or something inside one: Ionic carries an open `ion-modal` out of the page (README, «los diálogos»). */
const dialog = (page: Page, id: string) => page.locator(`[data-testid="${id}"]`);

/** The capture of a step, once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await page.mouse.move(0, 0);
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `CLOSE-BASE-${key}-${width}`);
}

async function signedIn(browser: Browser, viewport: { width: number; height: number }) {
  return hostPage(browser, A, { viewport, next: '/employees#apikeys' });
}

/** The token the dialog shows once, read before «Done» closes it. */
async function tokenShown(page: Page): Promise<string> {
  const value = dialog(page, 'api-key-token-value');
  await expect(value).toHaveText(/^erpk_live_\S+$/);
  return (await value.innerText()).trim();
}

/** What the API answers to `token` alone (no cookie, no session): its status and, when it refuses, the code. */
async function call(request: APIRequestContext, token: string, method: 'GET' | 'POST', path: string): Promise<[number, string]> {
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' };
  const name = `${PREFIX} ${Date.now()}`;
  const response = await (method === 'GET' ? request.get(`${A}${path}`, { headers }) : request.post(`${A}${path}`, { headers, data: { name } }));
  const answer = (await response.json()) as { error?: { code: string } };
  return [response.status(), answer.error?.code ?? ''];
}

const readWith = async (request: APIRequestContext, token: string) => (await call(request, token, 'GET', CATEGORIES))[0];

/** The box of `action` on `app` (`'*'`: every app) of «New API key». */
const box = (page: Page, app: string, action: string) => dialog(page, `api-key-form-${app}-${action}`);

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F86 BASE-F89 BASE-F87 BASE-F88 — make, copy, use, rotate and revoke an API key at ${width}`, async ({ browser, playwright }) => {
    const name = `${PREFIX} ${width} ${Date.now()}`;
    const { context, page } = await signedIn(browser, viewport);
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: A });
    const outside = await playwright.request.newContext();
    const problems = await collectProblems(page);

    // BASE-F86: «New API key», with its name, its pace and what it may do: on chosen apps, reading Inventory. What was
    // ticked on «All apps» before going back to «Choose apps» is not given.
    await testid(page, 'api-keys-new').click();
    await expect(dialog(page, 'api-key-form')).toBeVisible();
    await dialog(page, 'api-key-form-name').locator('input').fill(name);
    await dialog(page, 'api-key-form-rate').locator('input').fill('30');
    await expect(dialog(page, 'api-key-form-submit')).toHaveAttribute('aria-disabled', 'true');
    await dialog(page, 'api-key-form-where-all').click();
    await expect(dialog(page, 'api-key-form-apps').locator('tbody tr')).toHaveCount(1);
    await box(page, '*', 'update').click();
    await snap(page, 'BASE-F86-all-apps', width);
    await dialog(page, 'api-key-form-where-apps').click();
    await expect(box(page, 'inventory', 'read')).toBeVisible();
    await box(page, 'inventory', 'read').click();
    await expect(box(page, 'inventory', 'read')).toHaveJSProperty('checked', true);
    await snap(page, 'BASE-F86-form', width);
    await dialog(page, 'api-key-form-submit').click();
    await expect(dialog(page, 'api-key-form')).toBeHidden();

    // The token, once, with «Copy»: the clipboard holds it whole and the button says «Copied».
    await expect(dialog(page, 'api-key-token')).toContainText('Copy the token now');
    const first = await tokenShown(page);
    await dialog(page, 'api-key-token-copy').click();
    await expect(dialog(page, 'api-key-token-copy')).toHaveText('Copied');
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(first);
    await snap(page, 'BASE-F86-token', width);
    await dialog(page, 'api-key-token-done').click();
    await expect(dialog(page, 'api-key-token')).toBeHidden();
    await expect(page.getByText(first)).toHaveCount(0);

    // BASE-F89: the key in the list, with the start of its token, what it may do, who made it, its state and its limit.
    const listed = await api<{ keys: { id: string; name: string; prefix: string; created_by: string }[] }>(context, A, 'GET', '/keys');
    expect(listed.status).toBe(200);
    const key = listed.data.keys.find((one) => one.name === name);
    expect(key, `${name} is listed`).toBeTruthy();
    const id = key!.id;
    expect(first.startsWith(key!.prefix)).toBe(true);
    expect(key!.created_by).toMatch(/^[^@]+$/);
    const row = shown(page).locator('[data-testid="api-keys-row"]').filter({ hasText: name });
    await expect(row).toBeVisible();
    await expect(row.locator('[data-testid="api-keys-scopes"]')).toHaveText('Inventory R');
    await expect(row).toContainText('Created by');
    await expect(row).toContainText(key!.created_by);
    await expect(row).toContainText('Active');
    await expect(row).toContainText(`${key!.prefix}…`);
    await expect(row).toContainText('30/min');
    await snap(page, 'BASE-F89', width);

    // The key opens what it may do, with no session at all: it reads Inventory, writes nothing there and opens no
    // other app.
    expect(await call(outside, first, 'GET', CATEGORIES)).toEqual([200, '']);
    expect(await call(outside, first, 'POST', CATEGORIES)).toEqual([403, 'base.api_key_scope']);
    expect(await call(outside, first, 'GET', TAXES)).toEqual([403, 'base.api_key_scope']);

    // BASE-F87: «Rotate» asks first, then shows the new token once; the old one stops at once.
    await rowAction(page, 'api-keys', id, 'rotate');
    await expect(dialog(page, 'api-key-rotate')).toContainText('gets a new token. The current one stops working at once.');
    await snap(page, 'BASE-F87-confirm', width);
    await dialog(page, 'api-key-rotate-submit').click();
    await expect(dialog(page, 'api-key-rotate')).toBeHidden();
    const second = await tokenShown(page);
    expect(second).not.toBe(first);
    await snap(page, 'BASE-F87-token', width);
    await dialog(page, 'api-key-token-done').click();
    await expect(dialog(page, 'api-key-token')).toBeHidden();
    expect(await readWith(outside, first)).toBe(401);
    expect(await readWith(outside, second)).toBe(200);

    // BASE-F88: «Revoke» asks first; the key stops for good and stays listed as «Revoked», with nothing left to do.
    await rowAction(page, 'api-keys', id, 'revoke');
    await expect(dialog(page, 'api-key-revoke')).toContainText('Any system using this token loses access at once.');
    await dialog(page, 'api-key-revoke-submit').click();
    await expect(dialog(page, 'api-key-revoke')).toBeHidden();
    await expect(toastSaying(page, `“${name}” revoked.`)).toBeVisible();
    await expect(row).toContainText('Revoked');
    await expect(shown(page).locator(`[data-testid^="api-keys-row-${id}-"]`)).toHaveCount(0);
    expect(await readWith(outside, second)).toBe(401);
    await snap(page, 'BASE-F88', width);

    const seen = await problems();
    expect(seen.console).toEqual([]);
    expect(seen.page).toEqual([]);
    await outside.dispose();
    await context.close();
  });
}

test('BASE-F86 BASE-F89 — a key on all apps creates and reads, and does nothing else', async ({ browser, playwright }) => {
  const name = `${PREFIX} all ${Date.now()}`;
  const { context, page } = await signedIn(browser, VIEWPORTS[1440]);
  const outside = await playwright.request.newContext();
  await testid(page, 'api-keys-new').click();
  await dialog(page, 'api-key-form-name').locator('input').fill(name);
  await dialog(page, 'api-key-form-where-all').click();
  await box(page, '*', 'create').click();
  await box(page, '*', 'read').click();
  await dialog(page, 'api-key-form-submit').click();
  const token = await tokenShown(page);
  await dialog(page, 'api-key-token-done').click();
  const row = shown(page).locator('[data-testid="api-keys-row"]').filter({ hasText: name });
  await expect(row.locator('[data-testid="api-keys-scopes"]')).toHaveText('All apps R/C');
  expect(await call(outside, token, 'GET', TAXES)).toEqual([200, '']);
  expect(await call(outside, token, 'POST', CATEGORIES)).toEqual([201, '']);
  expect(await call(outside, token, 'POST', `${CATEGORIES}/delete`)).toEqual([403, 'base.api_key_scope']);
  await outside.dispose();
  await context.close();
});

test('BASE-F86 — the boxes are ticked with the keyboard, and each says its app and its action', async ({ browser }) => {
  const { context, page } = await signedIn(browser, VIEWPORTS[1440]);
  await testid(page, 'api-keys-new').click();
  const read = page.getByRole('checkbox', { name: 'Inventory · Read' });
  await expect(read).toBeVisible();
  await read.focus();
  await page.keyboard.press('Space');
  await expect(box(page, 'inventory', 'read')).toHaveJSProperty('checked', true);
  await page.keyboard.press('Tab');
  await page.keyboard.press('Space');
  await expect(box(page, 'inventory', 'create')).toHaveJSProperty('checked', true);
  await context.close();
});

const FORM_VIEWPORTS = {
  375: { width: 375, height: 667 },
  820: { width: 820, height: 1180 },
  1280: { width: 1280, height: 720 },
} as const;

for (const [label, viewport] of Object.entries(FORM_VIEWPORTS)) {
  const width = Number(label);

  for (const language of ['en', 'es']) {
    test(`BASE-F86 — the form fits, with nothing cut, at ${width} in ${language}`, async ({ browser }) => {
      const { context, page } = await (language === 'es'
        ? signedInSpanish(browser, viewport, '/employees#apikeys')
        : signedIn(browser, viewport));
      await saveSessionForTheSweep(context);
      await testid(page, 'api-keys-new').click();
      const form = dialog(page, 'api-key-form');
      for (const where of ['apps', 'all']) {
        await dialog(page, `api-key-form-where-${where}`).click();
        await untilStill(page);
        await capture(page, `BASE-F86-${where}-${language}-${width}`);
        expect(await cutLabels(form)).toEqual([]);
        const fit = await form.locator('[data-testid="api-key-form-apps"]').evaluate((element) => {
          const table = element.querySelector('table');
          if (!table) throw new Error('The table of boxes is missing');
          const cut = [...element.querySelectorAll('th')].filter((th) => th.scrollWidth > th.clientWidth);
          return { sideways: table.getBoundingClientRect().right - element.getBoundingClientRect().right, cut: cut.map((th) => th.textContent) };
        });
        expect(fit).toEqual({ sideways: 0, cut: [] });
      }

      // The help under the choice takes only its text's height.
      const metrics = await form.locator('.api-key-scopes > .api-keys-hint').evaluate((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const text = range.getBoundingClientRect();
        const table = element.closest('.api-key-form')?.querySelector('[data-testid="api-key-form-apps"] table');
        if (!(table instanceof HTMLElement)) throw new Error('The table of boxes is missing');
        return {
          boxHeight: element.getBoundingClientRect().height,
          textHeight: text.height,
          tableGap: table.getBoundingClientRect().top - text.bottom,
        };
      });
      expect(metrics.boxHeight).toBeLessThanOrEqual(metrics.textHeight * 1.25 + 1);
      expect(metrics.tableGap).toBeGreaterThanOrEqual(0);
      expect(metrics.tableGap).toBeLessThanOrEqual(16);
      await context.close();
    });
  }
}
