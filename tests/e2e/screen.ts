// More of the screen on view: the taller tablet's size, the icons it painted, the capture once it settled and nothing
// runs past its right edge, and the same at each of the three sizes every screen is seen at.
import { expect, type Page } from '@playwright/test';

import { capture, horizontalOverflow, shown, untilStill } from './helpers';

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

/** The three sizes every screen is seen at: a low phone, an Android tablet and a desk. */
export const THREE_SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1440, height: 900 },
] as const;

/** `what` on view at each of the three sizes with nothing past the right edge, captured as `<name>-<W>x<H>`; then back
 *  at the desk. */
export async function capturedAtEachSize(page: Page, name: string, what: string): Promise<void> {
  for (const size of THREE_SIZES) {
    await page.setViewportSize(size);
    await expect(shown(page).locator(`[data-testid=${what}]`).first()).toBeVisible();
    expect(await horizontalOverflow(page), `${name} ${size.width}x${size.height}`).toBe(0);
    await capture(page, `${name}-${size.width}x${size.height}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}
