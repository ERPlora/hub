// flow: BASE-F64
// The interface size of My profile (BASE-F64) is a `zoom` on <html>. At every size a small window opens right beside
// what opens it, as at 100 %: the person's menu under its card (Ionic places it) and the list of a field under the
// field (the shared Combo places it, here the country of a customer card). Its gap and its offset grow with the
// interface, and nothing else moves it. Measured as boxes, at four window sizes, in English and Spanish.
import { type BrowserContext, type Page, expect, test } from '@playwright/test';

import {
  A,
  api,
  capture,
  login,
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

/** Sub-pixel rounding of two boxes read in the same space; the zoom counted twice moves the menu tens of pixels. */
const TOLERANCE = 2;

const KEY = 'FIX-UI-POPOVER-INTERFACE-SIZE';

const card = (page: Page) => page.locator('ion-menu.dash-menu [data-testid=user-menu-trigger]');
const userMenu = (page: Page) => page.locator('ion-popover.sidebar-user-popover');

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

/** The menu open from its card: where its box starts against the card's, as the person sees both. */
async function menuAgainstItsCard(page: Page, size: Size): Promise<{ gap: number; offset: number }> {
  if (size.width < 992) await shown(page).locator('ion-header.app-topbar ion-menu-button').click();
  await expect(card(page)).toBeVisible();
  await card(page).click();
  await expect(userMenu(page).locator('ion-item').first()).toBeVisible();
  return userMenu(page).evaluate((popover) => {
    const trigger = document.querySelector('ion-menu.dash-menu [data-testid=user-menu-trigger]')!.getBoundingClientRect();
    const content = popover.shadowRoot!.querySelector('.popover-content')!.getBoundingClientRect();
    return { gap: content.top - trigger.bottom, offset: content.left - trigger.left };
  });
}

const customerForm = (page: Page) => page.locator('ion-modal[data-testid=customer-create]');
const countryField = (page: Page) => customerForm(page).locator('ion-input[data-testid=customer-form-country]');
const countryList = (page: Page) => page.locator('ion-popover.combo__popover');

/** The country list open under its field in a new customer card: its box against the field's, on its side of it. */
async function listAgainstItsField(page: Page): Promise<{ gap: number; offset: number; width: number }> {
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

test.describe.configure({ mode: 'serial' });

const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOnMissing(context, A, ['customer'], turnedOn);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A });
  const page = await context.newPage();
  await login(page, A, '/');
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

for (const size of SIZES) {
  test(`BASE-F64 — a field's list opens beside its field at every interface size (${size.label})`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL: A, viewport: size, locale: 'en-US' });
    const page = await context.newPage();
    await login(page, A, '/customer/customers');
    const before = await appearance(context);
    try {
      const measured: Record<number, { gap: number; offset: number; width: number }> = {};
      for (const scale of SCALES) {
        await atScale(context, page, scale);
        measured[scale] = await listAgainstItsField(page);
        if (scale === 120) await capture(page, `${KEY}-LIST-${size.label}-120-EN`);
      }
      record(`${KEY}-LIST-${size.label}`, measured);

      const base = measured[100];
      expect(base.gap, 'at 100 % the list starts just beside the field').toBeGreaterThanOrEqual(0);
      expect(base.gap).toBeLessThanOrEqual(16);
      for (const scale of SCALES) {
        const zoom = scale / 100;
        const { gap, offset, width } = measured[scale];
        expect(Math.abs(gap - base.gap * zoom), `gap beside the field at ${scale} %`).toBeLessThanOrEqual(TOLERANCE);
        expect(Math.abs(offset), `the list starts at the field's edge at ${scale} %`).toBeLessThanOrEqual(TOLERANCE);
        expect(Math.abs(width - base.width), `the list as wide as the field at ${scale} %`).toBeLessThanOrEqual(
          TOLERANCE,
        );
      }

      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await atScale(context, page, 120);
      await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
      const spanish = await listAgainstItsField(page);
      expect(Math.abs(spanish.gap - base.gap * 1.2), 'gap beside the field at 120 %, in Spanish').toBeLessThanOrEqual(
        TOLERANCE,
      );
      await capture(page, `${KEY}-LIST-${size.label}-120-ES`);
    } finally {
      expect((await api(context, A, 'POST', '/me/preferences', before)).status).toBe(200);
      await context.close();
    }
  });
}

for (const size of SIZES) {
  test(`BASE-F64 — the person's menu opens under its card at every interface size (${size.label})`, async ({
    browser,
  }) => {
    const context = await browser.newContext({ baseURL: A, viewport: size, locale: 'en-US' });
    const page = await context.newPage();
    await login(page, A, '/');
    await saveSessionForTheSweep(context);
    const before = await appearance(context);
    try {
      const measured: Record<number, { gap: number; offset: number }> = {};
      for (const scale of SCALES) {
        await atScale(context, page, scale);
        measured[scale] = await menuAgainstItsCard(page, size);
        if (scale === 120) await capture(page, `${KEY}-${size.label}-120-EN`);
      }
      record(`${KEY}-${size.label}`, measured);

      const base = measured[100];
      expect(base.gap, 'at 100 % the menu starts just under the card').toBeGreaterThanOrEqual(0);
      expect(base.gap).toBeLessThanOrEqual(24);
      for (const scale of SCALES) {
        const zoom = scale / 100;
        expect(Math.abs(measured[scale].gap - base.gap * zoom), `gap under the card at ${scale} %`).toBeLessThanOrEqual(
          TOLERANCE,
        );
        expect(
          Math.abs(measured[scale].offset - base.offset * zoom),
          `offset from the card's edge at ${scale} %`,
        ).toBeLessThanOrEqual(TOLERANCE);
      }

      await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
      await atScale(context, page, 120);
      await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
      const spanish = await menuAgainstItsCard(page, size);
      expect(Math.abs(spanish.gap - base.gap * 1.2), 'gap under the card at 120 %, in Spanish').toBeLessThanOrEqual(
        TOLERANCE,
      );
      await capture(page, `${KEY}-${size.label}-120-ES`);
    } finally {
      expect((await api(context, A, 'POST', '/me/preferences', before)).status).toBe(200);
      await context.close();
    }
  });
}
