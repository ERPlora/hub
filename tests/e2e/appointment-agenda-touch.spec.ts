// On a tablet, one tap on the Agenda's switches only changes the view: the click the browser makes after the touch lands
// on the tapped button, not on what the new view puts under the finger (the rows-per-page menu in landscape, «New
// repeating appointment» in portrait, the day's row on the way back). Chrome with touch emulated, against hub `a`.
// flow: APPOINTMENT-F12, APPOINTMENT-F13
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, login, shown } from './helpers';

const SIZES = [
  { label: '1280x800', width: 1280, height: 800 },
  { label: '800x1280', width: 800, height: 1280 },
];

declare global {
  interface Window {
    clicked?: string[];
  }
}

async function touchOwner(browser: Browser, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, hasTouch: true, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/appointment/agenda');
  return { context, page };
}

/** Writes down what each click lands on, by its nearest `data-testid`. */
async function watchClicks(page: Page): Promise<void> {
  await page.evaluate(() => {
    window.clicked = [];
    document.addEventListener(
      'click',
      (event) => {
        const target = event.target as HTMLElement;
        window.clicked?.push(target.closest('[data-testid]')?.getAttribute('data-testid') ?? target.tagName);
      },
      true,
    );
  });
}

/** Taps a button of the bar and returns what the clicks that followed landed on, once anything they opened shows. */
async function tap(page: Page, testid: string): Promise<string[]> {
  await page.evaluate(() => {
    window.clicked = [];
  });
  await shown(page).locator(`[data-testid=${testid}]`).tap();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => setTimeout(resolve, 600))));
  return page.evaluate(() => window.clicked ?? []);
}

async function nothingOpened(page: Page, after: string): Promise<void> {
  await expect(page.locator('ion-popover:not(.overlay-hidden)'), `a menu opened by itself after ${after}`).toHaveCount(0);
  await expect(page.locator('ion-modal:not(.overlay-hidden)'), `a window opened by itself after ${after}`).toHaveCount(0);
}

for (const size of SIZES) {
  test(`APPOINTMENT-F12 — one tap on the Agenda's switches only changes the view (${size.label})`, async ({ browser }) => {
    const { context, page } = await touchOwner(browser, { width: size.width, height: size.height });
    try {
      const view = (id: string) => shown(page).locator(`[data-testid=appointment-toolbar-view-${id}]`);
      const date = shown(page).locator('[data-testid=appointment-toolbar-date]');
      await expect(view('list')).toHaveClass(/segment-button-checked/);
      await shown(page).locator('[data-testid=appointment-list-row], [data-testid=appointment-list-empty]').first().waitFor();
      const today = await date.textContent();
      await watchClicks(page);

      expect(await tap(page, 'appointment-toolbar-view-series')).toEqual(['appointment-toolbar-view-series']);
      await shown(page).locator('[data-testid=appointment-series-row], [data-testid=appointment-series-empty]').first().waitFor();
      await expect(view('series')).toHaveClass(/segment-button-checked/);
      await nothingOpened(page, 'tapping «Repeating»');

      expect(await tap(page, 'appointment-toolbar-view-list')).toEqual(['appointment-toolbar-view-list']);
      await expect(view('list')).toHaveClass(/segment-button-checked/);
      await expect(date).toHaveText(today ?? '');
      await nothingOpened(page, 'tapping «List»');

      expect(await tap(page, 'appointment-toolbar-view-staff')).toEqual(['appointment-toolbar-view-staff']);
      await expect(view('staff')).toHaveClass(/segment-button-checked/);
      expect(await tap(page, 'appointment-toolbar-span-week')).toEqual(['appointment-toolbar-span-week']);
      expect(await tap(page, 'appointment-toolbar-span-day')).toEqual(['appointment-toolbar-span-day']);
      await expect(date).toHaveText(today ?? '');
      await nothingOpened(page, 'tapping «By professional», «Week» and «Day»');
    } finally {
      await context.close();
    }
  });
}
