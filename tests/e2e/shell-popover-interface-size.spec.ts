// flow: BASE-F64
// The interface size of My profile (BASE-F64) is a `zoom` on <html>. At every size a small window opens right beside
// what opens it, as at 100 %: the person's menu under its card (Ionic places it) and the list of a field under the
// field (the shared Combo places it, here the country of a customer card). Its gap and its offset grow with the
// interface, and nothing else moves it. Measured as boxes, at four window sizes, in English and Spanish.
import { type Browser, type BrowserContext, type Page, expect, test } from '@playwright/test';

import {
  A,
  api,
  capture,
  hostPage,
  record,
  saveSessionForTheSweep,
  shown,
  turnOffTurnedOn,
  turnOnMissing,
} from './helpers';

interface Size {
  label: string;
  width: number;
  height: number;
}

const SIZES: Size[] = [
  { label: '375x667', width: 375, height: 667 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '1280x720', width: 1280, height: 720 },
  { label: '1440x900', width: 1440, height: 900 },
];

const SCALES = [80, 100, 110, 120] as const;

/** Sub-pixel rounding of two boxes read in the same space; the zoom counted twice moves a window tens of pixels. */
const TOLERANCE = 2;

const KEY = 'FIX-UI-POPOVER-INTERFACE-SIZE';

/** A window against what opens it, as the person sees both: the space between them, how far its start is from the
 *  start of what opens it, and how much wider it is. */
interface Placed {
  gap: number;
  offset: number;
  width: number;
}

const card = (page: Page) => page.locator('ion-menu.dash-menu [data-testid=user-menu-trigger]');
const userMenu = (page: Page) => page.locator('ion-popover.sidebar-user-popover');
const customerForm = (page: Page) => page.locator('ion-modal[data-testid=customer-create]');
const countryField = (page: Page) => customerForm(page).locator('ion-input[data-testid=customer-form-country]');
const countryList = (page: Page) => page.locator('ion-popover.combo__popover');

interface Appearance {
  theme_mode: string;
  palette: string;
  ui_scale: number;
}

async function appearance(context: BrowserContext): Promise<Appearance> {
  const answer = await api<Appearance>(context, A, 'GET', '/me/profile');
  expect(answer.status, JSON.stringify(answer.data)).toBe(200);
  const { theme_mode, palette, ui_scale } = answer.data;
  return { theme_mode, palette, ui_scale };
}

async function atScale(context: BrowserContext, page: Page, scale: number): Promise<void> {
  expect((await api(context, A, 'POST', '/me/preferences', { ui_scale: scale })).status).toBe(200);
  await page.reload();
  await expect(page.locator('html')).toHaveCSS('zoom', String(scale / 100));
}

/** The menu open from its card. */
async function menuAgainstItsCard(page: Page, size: Size): Promise<Placed> {
  if (size.width < 992) await shown(page).locator('ion-header.app-topbar ion-menu-button').click();
  await expect(card(page)).toBeVisible();
  await card(page).click();
  await expect(userMenu(page).locator('ion-item').first()).toBeVisible();
  return userMenu(page).evaluate((popover) => {
    const trigger = document.querySelector('ion-menu.dash-menu [data-testid=user-menu-trigger]')!.getBoundingClientRect();
    const content = popover.shadowRoot!.querySelector('.popover-content')!.getBoundingClientRect();
    return { gap: content.top - trigger.bottom, offset: content.left - trigger.left, width: content.width - trigger.width };
  });
}

/** The country list open beside its field in a new customer card, on whichever side of it the list goes. */
async function listAgainstItsField(page: Page): Promise<Placed> {
  await shown(page).locator('[data-testid=customer-list-add]').click();
  await expect(customerForm(page)).toBeVisible();
  await customerForm(page).locator('[data-testid=customer-form-more] > summary').click();
  const input = countryField(page).locator('input');
  await input.scrollIntoViewIfNeeded();
  await input.fill('fra');
  await expect(page.locator('[data-testid=customer-form-country-option-FR]')).toBeVisible();
  await expect(countryList(page).locator('.popover-content')).toHaveCSS('opacity', '1');
  return countryList(page).evaluate((popover) => {
    const field = document
      .querySelector('ion-modal[data-testid=customer-create] ion-input[data-testid=customer-form-country]')!
      .getBoundingClientRect();
    const list = popover.shadowRoot!.querySelector('.popover-content')!.getBoundingClientRect();
    const gap = list.top >= field.bottom - 1 ? list.top - field.bottom : field.top - list.bottom;
    return { gap, offset: list.left - field.left, width: list.width - field.width };
  });
}

/** The owner on `next` at `size` opens the window (`open`) at every interface size, and once more at 120 % in
 *  Spanish; each 120 % is captured. The person's own appearance is put back after. */
async function atEveryScale(
  browser: Browser,
  size: Size,
  next: string,
  name: string,
  open: (page: Page) => Promise<Placed>,
): Promise<{ at: Record<number, Placed>; spanish: Placed }> {
  const { context, page } = await hostPage(browser, A, { next, viewport: size });
  await saveSessionForTheSweep(context);
  const before = await appearance(context);
  try {
    const at: Record<number, Placed> = {};
    for (const scale of SCALES) {
      await atScale(context, page, scale);
      at[scale] = await open(page);
      if (scale === 120) await capture(page, `${name}-120-EN`);
    }
    record(name, at);
    await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
    await atScale(context, page, 120);
    await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
    const spanish = await open(page);
    await capture(page, `${name}-120-ES`);
    return { at, spanish };
  } finally {
    expect((await api(context, A, 'POST', '/me/preferences', before)).status).toBe(200);
    await context.close();
  }
}

/** Beside what opens it at 100 % (no further than `most`), and at every size what `keys` name grows with the
 *  interface and nothing else: as at 100 %, times the zoom. */
function expectBesideItsOpener(
  { at, spanish }: { at: Record<number, Placed>; spanish: Placed },
  most: number,
  keys: (keyof Placed)[],
): void {
  const base = at[100];
  expect(base.gap, 'at 100 % it starts just beside what opens it').toBeGreaterThanOrEqual(0);
  expect(base.gap).toBeLessThanOrEqual(most);
  for (const scale of SCALES) {
    for (const key of keys) {
      expect(Math.abs(at[scale][key] - (base[key] * scale) / 100), `${key} at ${scale} %`).toBeLessThanOrEqual(TOLERANCE);
    }
  }
  expect(Math.abs(spanish.gap - base.gap * 1.2), 'gap at 120 %, in Spanish').toBeLessThanOrEqual(TOLERANCE);
}

test.describe.configure({ mode: 'serial' });

const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/' });
  await turnOnMissing(context, A, ['customer'], turnedOn);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/' });
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

for (const size of SIZES) {
  test(`BASE-F64 — the person's menu opens under its card at every interface size (${size.label})`, async ({
    browser,
  }) => {
    const measured = await atEveryScale(browser, size, '/', `${KEY}-${size.label}`, (page) =>
      menuAgainstItsCard(page, size),
    );
    expectBesideItsOpener(measured, 24, ['gap', 'offset']);
  });

  test(`BASE-F64 — a field's list opens beside its field at every interface size (${size.label})`, async ({
    browser,
  }) => {
    const measured = await atEveryScale(browser, size, '/customer/customers', `${KEY}-LIST-${size.label}`, listAgainstItsField);
    expectBesideItsOpener(measured, 16, ['gap', 'offset', 'width']);
  });
}
