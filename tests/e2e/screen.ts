// More of the screen on view: the taller tablet's size, Chrome's address bar over a tablet in landscape, where a
// window sits on the page, the icons it painted, and the capture once it settled and nothing runs past its right edge.
import { type ElementHandle, expect, type Locator, type Page } from '@playwright/test';

import { capture, horizontalOverflow, shown, untilStill } from './helpers';

/** The three sizes with the taller tablet, 834×1194. */
export const THREE_SIZES_TALL_TABLET = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** An Android tablet in landscape in Chrome, with the address bar shown: the page has 665 px of height, while `100vh`
 *  still counts the 721 px it would have without the bar. Open the page at `withoutBar`, then `underAddressBar`. */
export const CHROME_LANDSCAPE = { width: 1280, page: 665, withoutBar: 721 } as const;

/** Chrome's address bar over a page opened `CHROME_LANDSCAPE.withoutBar` high: the page loses its height, `vh` does
 *  not. Removing the style it returns takes the bar away. */
export function underAddressBar(page: Page): Promise<ElementHandle> {
  const height = `${CHROME_LANDSCAPE.page}px !important`;
  return page.addStyleTag({ content: `body { height: ${height}; max-height: ${height}; }` });
}

export interface Box {
  top: number;
  bottom: number;
}

export interface WindowFit {
  /** The height the page has: the modal's own box, which covers it. */
  screen: number;
  /** Ionic's wrapper, in the modal's shadow root: the window the person sees. */
  window: Box;
  /** Each part asked for, by its name. */
  parts: Record<string, Box>;
}

/** Where the window of the `ion-modal` `modal` sits on the page, and each of its `parts` (a name, and a selector inside
 *  the modal). */
export function windowFit(modal: Locator, parts: Record<string, string>): Promise<WindowFit> {
  return modal.evaluate((el, selectors) => {
    const box = (part: Element | null | undefined, name: string): Box => {
      if (!part) throw new Error(`the window has no ${name}`);
      const { top, bottom } = part.getBoundingClientRect();
      return { top, bottom };
    };
    return {
      screen: el.getBoundingClientRect().height,
      window: box(el.shadowRoot?.querySelector('.modal-wrapper'), 'wrapper'),
      parts: Object.fromEntries(Object.entries(selectors).map(([name, selector]) => [name, box(el.querySelector(selector), name)])),
    };
  }, parts);
}

/** The window inside the page, and each part named in `onView` inside the window. */
export function expectWindowOnScreen(fit: WindowFit, onView: readonly string[], where: string): void {
  expect(fit.window.top, `the window starts on the screen ${where}`).toBeGreaterThanOrEqual(-0.5);
  expect(fit.window.bottom, `the window ends on the screen ${where}`).toBeLessThanOrEqual(fit.screen + 0.5);
  for (const name of onView) {
    const part = fit.parts[name];
    expect(part, `the window has a ${name}`).toBeDefined();
    expect(part.top, `the ${name} starts inside the window ${where}`).toBeGreaterThanOrEqual(fit.window.top - 0.5);
    expect(part.bottom, `the ${name} ends inside the window ${where}`).toBeLessThanOrEqual(fit.window.bottom + 0.5);
  }
}

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
