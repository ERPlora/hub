// More of the screen on view: the taller tablet's size, the tablet in landscape under Chrome's address bar and the sizes
// a window is measured at, the icons it painted, and the capture once it settled and nothing runs past its right edge.
import { expect, type Page } from '@playwright/test';

import { capture, horizontalOverflow, settled, shown, untilStill } from './helpers';

/** The three sizes with the taller tablet, 834×1194. */
export const THREE_SIZES_TALL_TABLET = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** Every `ion-icon` on screen: its name and whether its shadow root painted an `<svg>`. */
export async function iconStates(page: Page): Promise<{ name: string; painted: boolean }[]> {
  return page.evaluate(() =>
    [...document.querySelectorAll('ion-icon')]
      .filter((el) => el.getBoundingClientRect().width > 0)
      .map((el) => ({
        name: el.getAttribute('name') ?? '(icon prop)',
        painted: !!el.shadowRoot?.querySelector('svg'),
      })),
  );
}

/** The capture once the screen settled and nothing scrolls sideways. */
export async function settledCapture(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** The page still, with nothing past its right edge at the size `label`, then captured as `name`. */
export async function capturedFitting(page: Page, name: string, label: string): Promise<void> {
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `no sideways scroll at ${label}`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

/** Chrome on an Android tablet in landscape with its address bar shown: the page is 665 px tall while `100vh` still
 *  counts the 761 px the screen has without the bar. */
export const CHROME_LANDSCAPE = { width: 1280, page: 665, withoutBar: 761 } as const;

/** The sizes a window is measured at besides the address bar: the same tablet without it, the desktop, the tablet
 *  upright and the low phone. */
export const FIT_SIZES = [
  { width: 1280, height: 665 },
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 820, height: 1180 },
  { width: 375, height: 667 },
] as const;

/** Shortens the page to what Chrome's address bar leaves of `CHROME_LANDSCAPE`; the function it returns lifts the bar. */
export async function underAddressBar(page: Page): Promise<() => Promise<void>> {
  const { page: height } = CHROME_LANDSCAPE;
  const bar = await page.addStyleTag({ content: `body { height: ${height}px !important; max-height: ${height}px !important; }` });
  return () => bar.evaluate((style) => (style as Element).remove());
}

/** Each of `FIT_SIZES` in turn, settled, handed to `check` with its label (`1280x665`) and its height. */
export async function atEachFitSize(page: Page, check: (label: string, height: number) => Promise<void>): Promise<void> {
  for (const size of FIT_SIZES) {
    await page.setViewportSize(size);
    await settled(page);
    await check(`${size.width}x${size.height}`, size.height);
  }
}
