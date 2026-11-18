// More of the screen on view: the taller tablet's size, the icons it painted, an element scrolled to through the
// page's repaints, and the capture once it settled and nothing runs past its right edge.
import { expect, type Locator, type Page } from '@playwright/test';

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

/** How many times `scrolledTo` looks again for an element the page painted again while it scrolled to it. */
const SCROLL_REPAINTS = 10;

/** Playwright's error when the element an action took is gone from the page (painted again in its place). */
const notAttached = (error: unknown): boolean => error instanceof Error && error.message.includes('Element is not attached to the DOM');

/**
 * Scrolls to what `target` finds once it has stayed attached to the page through the scroll. Playwright's
 * `scrollIntoViewIfNeeded` takes the element once and keeps it (a click looks for it again; a scroll does not): right
 * after `page.setViewportSize`, a DataTable switches between its cards and its rows a frame or more later (its phone
 * breakpoint's `matchMedia`, #274), so a spec that checked the text in what the size before painted scrolls to an
 * element the list is replacing and fails with «Element is not attached to the DOM» (hub#1303). This looks for it
 * again, as many times as the page paints it again (up to `SCROLL_REPAINTS`, then it fails saying so); any other error
 * fails the spec as before.
 */
export async function scrolledTo(target: Locator): Promise<void> {
  for (let repaints = 0; repaints < SCROLL_REPAINTS; repaints++) {
    try {
      await target.scrollIntoViewIfNeeded();
      return;
    } catch (error) {
      if (!notAttached(error)) throw error;
    }
  }
  throw new Error(`scrolledTo: ${String(target)} was painted again ${SCROLL_REPAINTS} times while scrolling to it`);
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
