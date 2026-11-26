// flow: BASE-F132
// The side menu on a low screen, as on a tablet in landscape in Chrome (1280×665 of CSS): every entry shows whole,
// without scrolling, because the entries come before the foot. There the QR «Open on your phone» folds into one row
// that shows the code on a tap; on a taller screen the code stays painted in the foot. Measured as boxes, with the
// longest menu the owner can have (API included), in English and Spanish.
import { type Browser, type Locator, type Page, expect, test } from '@playwright/test';

import { A, api, capture, login, record, shown, signedInSpanish } from './helpers';

interface Size {
  label: string;
  width: number;
  height: number;
  /** Whether the code fits under the entries at this size, and stays painted in the foot. */
  roomy: boolean;
}

const SIZES: Size[] = [
  { label: '375x667', width: 375, height: 667, roomy: false },
  { label: '820x1180', width: 820, height: 1180, roomy: true },
  { label: '1280x720', width: 1280, height: 720, roomy: false },
  { label: '1280x665', width: 1280, height: 665, roomy: false },
  { label: '1440x900', width: 1440, height: 900, roomy: true },
];

const TITLE = { en: 'Open on your phone', es: 'Ábrelo en el móvil' } as const;
type Language = keyof typeof TITLE;

const menu = (page: Page): Locator => page.locator('ion-menu.dash-menu');
const qr = (page: Page): Locator => page.locator('[data-testid=sidebar-install-qr]');
const inlineCode = (page: Page): Locator => qr(page).locator('img.sidebar-install-qr-code');
const fold = (page: Page): Locator => qr(page).locator('[data-testid=sidebar-install-qr-open]');
const popover = (page: Page): Locator => page.locator('ion-popover.sidebar-install-qr-popover');

/** Each entry of the menu against the box of the list that holds them: whole inside it, and on top where painted. */
async function entriesAgainstTheirList(page: Page) {
  return menu(page)
    .locator('ion-content.sidebar-content')
    .evaluate((content) => {
      const scroll = content.shadowRoot!.querySelector('[part~="scroll"]')!;
      const box = scroll.getBoundingClientRect();
      const entries = [...content.querySelectorAll('ion-item.nav-item')].map((item) => {
        const rect = item.getBoundingClientRect();
        const atCentre = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return {
          id: item.getAttribute('data-testid'),
          top: Math.round(rect.top),
          bottom: Math.round(rect.bottom),
          whole: rect.height > 0 && rect.top >= box.top - 0.5 && rect.bottom <= box.bottom + 0.5,
          onTop: atCentre !== null && item.contains(atCentre),
        };
      });
      return {
        list: { top: Math.round(box.top), bottom: Math.round(box.bottom) },
        hiddenBelow: scroll.scrollHeight - scroll.clientHeight,
        entries,
      };
    });
}

async function openMenu(page: Page, size: Size): Promise<void> {
  if (size.width < 992) {
    await shown(page).locator('ion-header.app-topbar ion-menu-button').click();
  }
  await expect(menu(page)).toBeVisible();
  await expect(menu(page).locator('[data-testid=nav-settings]')).toBeVisible();
  await expect(qr(page)).toBeVisible();
}

async function signedIn(browser: Browser, size: Size, language: Language) {
  const viewport = { width: size.width, height: size.height };
  if (language === 'es') return signedInSpanish(browser, viewport, '/');
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/');
  return { context, page };
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  // «API» in the menu too, the longest menu an owner can have.
  const { context } = await signedIn(browser, SIZES[4], 'en');
  expect((await api(context, A, 'POST', '/api-docs/settings/update', { docs_enabled: true })).status).toBe(200);
  await context.close();
});

test.afterAll(async ({ browser }) => {
  const { context } = await signedIn(browser, SIZES[4], 'en');
  expect((await api(context, A, 'POST', '/api-docs/settings/update', { docs_enabled: false })).status).toBe(200);
  await context.close();
});

/** The menu open at `size`: every entry whole inside its list and on top, and the QR painted or a tap away. */
async function expectEntriesWholeAndQrAtHand(page: Page, size: Size, language: Language, name: string): Promise<void> {
  await openMenu(page, size);
  await expect(menu(page).locator('[data-testid=nav-api]')).toBeVisible();

  const measured = await entriesAgainstTheirList(page);
  record(name, measured);
  expect(measured.entries.map((entry) => entry.id)).toEqual([
    'nav-home',
    'nav-employees',
    'nav-files',
    'nav-apps',
    'nav-system',
    'nav-api',
    'nav-settings',
  ]);
  expect(measured.hiddenBelow, 'nothing of the list is left to scroll to').toBeLessThanOrEqual(0);
  for (const entry of measured.entries) {
    expect(entry.whole, `${entry.id} inside its list`).toBe(true);
    expect(entry.onTop, `${entry.id} not covered by the foot`).toBe(true);
  }

  if (size.roomy) {
    await expect(inlineCode(page)).toBeVisible();
    await expect(fold(page)).toBeHidden();
    await capture(page, name);
    return;
  }
  await expect(inlineCode(page)).toBeHidden();
  const door = menu(page).getByRole('button', { name: TITLE[language], exact: true });
  await expect(door).toBeVisible();
  await expect(door).toHaveAttribute('aria-haspopup', 'dialog');
  await capture(page, name);

  await door.click();
  await expect(popover(page)).toBeVisible();
  const code = popover(page).getByRole('img', { name: language === 'en' ? `QR code of ${A}/` : `Código QR de ${A}/` });
  await expect(code).toBeVisible();
  expect(await code.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  const codeBox = (await code.boundingBox())!;
  expect(codeBox.y, 'the code whole on screen').toBeGreaterThanOrEqual(0);
  expect(codeBox.y + codeBox.height).toBeLessThanOrEqual(size.height);
  expect(codeBox.x).toBeGreaterThanOrEqual(0);
  expect(codeBox.x + codeBox.width).toBeLessThanOrEqual(size.width);
  await expect(popover(page).locator('.sidebar-install-qr-title')).toHaveText(TITLE[language]);
  await capture(page, `${name}-open`);

  await page.keyboard.press('Escape');
  await expect(popover(page)).toBeHidden();
  await expect(door).toBeFocused();
}

for (const language of ['en', 'es'] as const) {
  for (const size of SIZES) {
    test(`${size.label} ${language}: every entry of the menu shows whole, and the QR is at hand`, async ({ browser }) => {
      const { context, page } = await signedIn(browser, size, language);
      await expectEntriesWholeAndQrAtHand(page, size, language, `SHELL-SIDEBAR-LOW-${size.label}-${language}`);
      await context.close();
    });
  }
}

// The interface size the person picks in My profile zooms the page: at 120 % a 900 px window holds a menu of 750 px,
// too low for the entries and the code, so the code folds there too.
test('1440x900 at an interface size of 120 %: every entry shows whole, and the QR is a tap away', async ({ browser }) => {
  const size: Size = { label: '1440x900-120', width: 1440, height: 900, roomy: false };
  const { context, page } = await signedIn(browser, size, 'en');
  try {
    expect((await api(context, A, 'POST', '/me/preferences', { ui_scale: 120 })).status).toBe(200);
    await page.reload();
    await expect.poll(() => page.evaluate(() => document.documentElement.style.zoom)).toBe('120%');
    await expectEntriesWholeAndQrAtHand(page, size, 'en', 'SHELL-SIDEBAR-LOW-1440x900-120-en');
  } finally {
    expect((await api(context, A, 'POST', '/me/preferences', { ui_scale: 100 })).status).toBe(200);
    await context.close();
  }
});
