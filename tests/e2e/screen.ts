// What the specs find on the screen shown and measure on it: the sizes they look at it in, the page on view and
// what it marks, its icons and how far it runs past the right edge.
import type { Locator, Page } from '@playwright/test';

/** The three sizes with the taller tablet, 834×1194. */
export const THREE_SIZES_TALL_TABLET = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** The three sizes the e2e looks at a screen in: a phone, a tablet and a desk. */
export const THREE_SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
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

/**
 * How many pixels of the page lie past the right edge of their box, 0 when everything fits its width: the document's
 * and, in every `ion-content` (the shown page's, the pinned side menu's, an open sheet's), its scroll box, in its shadow
 * root (`part="scroll"`; a hidden one is 0 wide). Ionic pins the `body` to the window, so a screen that runs past the
 * right edge is cut inside its `ion-content` and the document never grows: the document alone read 0 with a 1600 px
 * block on a page at 390. The one «no horizontal scroll» measure of the e2e (`horizontal-overflow.test.ts` keeps it so).
 */
export async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const boxes: Element[] = [document.documentElement];
    for (const content of document.querySelectorAll('ion-content')) {
      const scroll = content.shadowRoot?.querySelector('[part~="scroll"]');
      if (scroll) boxes.push(scroll);
    }
    return Math.max(0, ...boxes.map((box) => box.scrollWidth - box.clientWidth));
  });
}

/** What the page on screen marks with this `data-testid`. */
export const testid = (page: Page, id: string): Locator => shown(page).locator(`[data-testid="${id}"]`);

/** `id`'s row in the Apps screen. */
export const appRow = (page: Page, id: string): Locator => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** Ionic's overlays. An inline `ion-modal` wraps its content in an `.ion-page` of its own. */
const OVERLAYS = 'ion-modal, ion-popover, ion-alert, ion-action-sheet, ion-loading, ion-picker-legacy';

/**
 * The page shown by `IonRouterOutlet` (hidden pages stay in the DOM), never a dialog presented over it:
 * Ionic moves a presented modal to `ion-app`, after the pages, so the last visible `.ion-page` would be the
 * dialog's. A dialog is found with `page.locator('ion-modal[data-testid=…]')`, not here.
 */
export const shown = (page: Page): Locator =>
  page.locator(`.ion-page:not(.ion-page-hidden):not(:is(${OVERLAYS}) *)`).last();
