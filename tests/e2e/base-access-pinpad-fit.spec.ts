// flow: BASE-F55 BASE-F58
// hub#441: Access's PIN pad shows its four rows whole, the 0 and erase included, without scrolling, on a tablet in
// landscape (the Lenovo TB361FU of the QA: 1280×800 CSS, 776 under the native app's status bar, less in its browser),
// on a desk, a tablet in portrait and a low phone (Square's, Toast's and Lightspeed's passcode screens: the keypad is
// always whole). In Spanish, whose texts over the pad are the longest. The way in of the issue: the owner, with a PIN
// that has a 0, signs out of a shared device of hub `a` and lands on its PIN pad; at the tablet they erase a wrong
// digit and enter with the 0. A session that ended (`?notice=ended`, BASE-F58) puts its notice over the pad, which
// still fits. The owner's PIN exists only while this file runs (a PIN in hub `a` turns every browser's way in into
// the PIN pad: base-access.spec.ts), and goes with it (`afterAll`).
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, capture, login, OWNER, psql, shown, untilStill } from './helpers';

const KEY = 'FIX-HUB-441-PINPAD-LANDSCAPE';
/** The key the cut hid: the PIN has a 0. */
const OWNER_PIN = '2580';
/** The smallest key a finger hits without missing (Material's 48 dp touch target). */
const MIN_KEY = 48;
const SIZES = [
  /** The QA's tablet in landscape, in the native app (the status bar takes 24 of its 800). */
  { label: '1280x776', width: 1280, height: 776 },
  /** The same tablet in its browser: the status bar, the tab strip and the address bar over the page. */
  { label: '1280x680', width: 1280, height: 680 },
  /** An iPad Air in landscape. */
  { label: '1180x820', width: 1180, height: 820 },
  /** A laptop's browser with its bars. */
  { label: '1366x657', width: 1366, height: 657 },
  /** The fleet's three: a desk, a tablet in portrait and a low phone (an iPhone SE). */
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
] as const;
/** Where the person enters in the end: the QA's tablet. */
const TABLET = SIZES[0];

test.describe.configure({ mode: 'serial' });

let till: { context: BrowserContext; page: Page };
let username = '';

/** The owner's PIN gone, in this hub's database: the business's way in stays erplora.com's for every other spec. */
function forgetThePin(): void {
  if (username) psql(`UPDATE base_credential SET pin_hash = '', pin_set_at = NULL WHERE username = '${username}'`);
}

/** The screen in hand scrolled back to its top: what a person sees when the door opens. */
async function toTop(page: Page): Promise<void> {
  await shown(page)
    .locator('ion-content')
    .first()
    .evaluate((content) => (content as unknown as { scrollToTop: (duration: number) => Promise<void> }).scrollToTop(0));
}

/** The user menu of the side menu (pinned at 1440), and the entry `id` in it. */
async function userMenu(page: Page, id: string): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
  await page.locator(`ion-popover [data-testid="user-menu-${id}"]`).click();
}

/** At `size`, unscrolled: the pad's first row and its last (the 0 and erase) inside the screen, and keys a finger hits. */
async function expectWholePad(page: Page, size: { label: string; width: number; height: number }): Promise<void> {
  await page.setViewportSize({ width: size.width, height: size.height });
  const pad = shown(page).getByTestId('pinpad');
  await expect(pad).toBeVisible();
  await untilStill(page);
  await toTop(page);
  for (const id of ['pinpad-key-1', 'pinpad-key-0', 'pinpad-erase']) {
    const key = await pad.getByTestId(id).boundingBox();
    expect(key, `${id} at ${size.label}`).not.toBeNull();
    expect(key!.y, `${id} below the screen's top at ${size.label}`).toBeGreaterThanOrEqual(0);
    expect(key!.y + key!.height, `${id} above the screen's bottom at ${size.label}, unscrolled`).toBeLessThanOrEqual(size.height + 0.5);
    expect(key!.x + key!.width, `${id} left of the screen's right at ${size.label}`).toBeLessThanOrEqual(size.width + 0.5);
    expect(Math.round(key!.height), `${id} a finger's size at ${size.label}`).toBeGreaterThanOrEqual(MIN_KEY);
  }
}

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A, locale: 'es-ES' });
  till = { context, page: await context.newPage() };
  // Its own session: signing out of it must not end the one other specs reuse (helpers.ts, `login`).
  await login(till.page, A, '/', OWNER, { fresh: true });
  const me = await api<{ user: { id: string } | null }>(context, A, 'GET', '/me');
  expect(me.status, 'GET /api/me').toBe(200);
  username = psql(`SELECT username FROM base_hubuser WHERE id = '${me.data.user?.id ?? ''}'`);
  expect(username, 'the owner, in this hub').not.toBe('');
  forgetThePin();
  const pin = await api<{ set: boolean }>(context, A, 'POST', '/me/pin', { pin: OWNER_PIN });
  expect(pin.status, JSON.stringify(pin.data)).toBe(200);
  // In Spanish (the Hub's language cookie, as the sign-in sets it): the longest texts over the pad.
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
});

test.afterAll(async () => {
  forgetThePin();
  // The till's device (its cookie), for a sweep of its Access (as base-approval.spec.ts saves the cashier's).
  if (process.env.E2E_SAVE_STORAGE_STATE) await till?.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  await till?.context.close();
});

test('BASE-F55: signing out of the shared device leaves its PIN pad whole on screen at every size', async () => {
  const { page } = till;
  await userMenu(page, 'logout');
  await expect(page).toHaveURL(/\/login(\?|$)/);
  // One person with a PIN: the pad is already theirs.
  await expect(shown(page).getByTestId('pin-door-chosen')).toBeVisible();
  for (const size of SIZES) {
    await expectWholePad(page, size);
    // The whole door, down to its footer: nothing of it under the screen's edge.
    const footer = await shown(page).getByTestId('access-footer').boundingBox();
    expect(footer, `the footer at ${size.label}`).not.toBeNull();
    expect(footer!.y + footer!.height, `the footer above the screen's bottom at ${size.label}`).toBeLessThanOrEqual(size.height + 0.5);
    await capture(page, `${KEY}-${size.label}`);
  }
});

test('BASE-F55: at the tablet in landscape the owner erases a wrong digit and enters with a PIN that has a 0', async () => {
  const { page } = till;
  await expectWholePad(page, TABLET);
  const pad = shown(page).getByTestId('pinpad');
  const filled = pad.locator('[data-testid=pinpad-dot].is-filled');
  await pad.getByTestId('pinpad-key-9').click();
  await expect(filled).toHaveCount(1);
  await pad.getByTestId('pinpad-erase').click();
  await expect(filled).toHaveCount(0);
  for (const digit of OWNER_PIN) await pad.getByTestId(`pinpad-key-${digit}`).click();
  await expect(page).toHaveURL(`${A}/`);
});

test('BASE-F58: a session that ended says so over the pad, and the pad stays whole at the tablet in landscape', async () => {
  const { page } = till;
  await userMenu(page, 'logout');
  await expect(page).toHaveURL(/\/login(\?|$)/);
  await page.goto(`${A}/login?notice=ended`);
  await expect(shown(page).getByTestId('access-notice')).toBeVisible();
  for (const size of [TABLET, SIZES[1], SIZES[2], SIZES[4]]) {
    await expectWholePad(page, size);
    await capture(page, `${KEY}-ended-${size.label}`);
  }
});
