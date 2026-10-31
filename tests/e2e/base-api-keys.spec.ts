// The business's API keys from end to end (BASE-F86 create and copy the token, BASE-F89 see the keys and what each
// may do, BASE-F87 rotate, BASE-F88 revoke; registry keys BASE-G03, G05, G25, G37), in the three viewports, as the
// owner of hub `a`, which has its own database since S2a (round 2026-10-30 of PLAN-DB): a business that still shares
// control's database says «Not available yet» instead (ApiKeysPanel.test.ts, base/tests/test_api_keys.py).
//
// Each viewport makes one read-only key, sees its token once and copies it, finds it in the list with what it may do,
// calls the API with it from a context with no session (only the token opens the door), rotates it (the new token
// works, the old one is 401 at once) and revokes it (401 for good, listed as «Revoked» with no actions left). What a
// run made is deleted before and after it, so the other specs find the business as it was.
// flow: BASE-F86 BASE-F87 BASE-F88 BASE-F89
import { type APIRequestContext, type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, collectProblems, horizontalOverflow, hostPage, psql, shot, shown, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** Every key a run of this spec makes is named so, and only those are deleted. */
const PREFIX = 'E2E API key';

/** A read of an app every business has (Taxes), published to API keys: what a read-only key may call. */
const READ = '/api/tax/categories';

function forgetTheKeys(): void {
  psql(`delete from base_apikey where name like '${PREFIX}%'`);
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
  await page.screenshot({ path: shot(`CLOSE-BASE-${key}-${width}`) });
}

async function signedIn(browser: Browser, viewport: { width: number; height: number }) {
  return hostPage(browser, A, { viewport, next: '/employees#apikeys' });
}

/** Runs a row action: its button, or the same entry inside «⋮» when the row folds its actions. */
async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=api-keys-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=api-keys-row-${id}-menu]`);
  await button.or(menu).first().waitFor({ state: 'visible' });
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=api-keys-row-${id}-${action}]`).click();
}

/** The token the dialog shows once, read before «Done» closes it. */
async function tokenShown(page: Page): Promise<string> {
  const value = dialog(page, 'api-key-token-value');
  await expect(value).toHaveText(/^erpk_live_\S+$/);
  return (await value.innerText()).trim();
}

/** The status of a read of the API with `token` alone: no cookie, no session. */
async function readWith(request: APIRequestContext, token: string): Promise<number> {
  const response = await request.get(`${A}${READ}`, { headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' } });
  return response.status();
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F86 BASE-F89 BASE-F87 BASE-F88 — make, copy, use, rotate and revoke an API key at ${width}`, async ({ browser, playwright }) => {
    const name = `${PREFIX} ${width} ${Date.now()}`;
    const { context, page } = await signedIn(browser, viewport);
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: A });
    const outside = await playwright.request.newContext();
    const problems = await collectProblems(page);

    // BASE-F86: «New API key», with its name, its pace and what it may do («Read only»).
    await testid(page, 'api-keys-new').click();
    await expect(dialog(page, 'api-key-form')).toBeVisible();
    await dialog(page, 'api-key-form-name').locator('input').fill(name);
    await dialog(page, 'api-key-form-rate').locator('input').fill('30');
    await dialog(page, 'api-key-form-mode-read').click();
    await expect(dialog(page, 'api-key-form-mode-read')).toHaveAttribute('aria-checked', 'true');
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

    // BASE-F89: the key in the list, with the start of its token, what it may do, its state and its limit.
    const listed = await api<{ keys: { id: string; name: string; prefix: string }[] }>(context, A, 'GET', '/keys');
    expect(listed.status).toBe(200);
    const key = listed.data.keys.find((one) => one.name === name);
    expect(key, `${name} is listed`).toBeTruthy();
    const id = key!.id;
    expect(first.startsWith(key!.prefix)).toBe(true);
    const row = shown(page).locator('[data-testid="api-keys-row"]').filter({ hasText: name });
    await expect(row).toBeVisible();
    await expect(row.locator('[data-testid="api-keys-scopes"]')).toHaveText('Read only');
    await expect(row).toContainText('Active');
    await expect(row).toContainText(`${key!.prefix}…`);
    await expect(row).toContainText('30/min');
    await snap(page, 'BASE-F89', width);

    // The key opens what it may do, with no session at all.
    expect(await readWith(outside, first)).toBe(200);

    // BASE-F87: «Rotate» asks first, then shows the new token once; the old one stops at once.
    await rowAction(page, id, 'rotate');
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
    await rowAction(page, id, 'revoke');
    await expect(dialog(page, 'api-key-revoke')).toContainText('Any system using this token loses access at once.');
    await dialog(page, 'api-key-revoke-submit').click();
    await expect(dialog(page, 'api-key-revoke')).toBeHidden();
    await expect(page.locator('ion-toast').filter({ hasText: `“${name}” revoked.` }).first()).toBeVisible();
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
