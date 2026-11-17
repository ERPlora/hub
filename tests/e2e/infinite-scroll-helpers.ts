// The cards of a DataTable, and a phone's list, load the next rows at the end of their scroll (Ionic's
// `ion-infinite-scroll`): there is no «Load more» button to press.
import type { Page } from '@playwright/test';

import { shown } from './helpers';

const infinite = (page: Page) => shown(page).locator('ion-infinite-scroll');

/** The table still asks for more at the end of its scroll: Ionic's infinite scroll is there and on. */
export async function loadsMore(page: Page): Promise<boolean> {
  if ((await infinite(page).count()) === 0) return false;
  return infinite(page)
    .first()
    .evaluate((el) => (el as HTMLElement & { disabled?: boolean }).disabled !== true);
}

/** Scrolls the table's rows to the bottom of their scroll (the page's `ion-content`, or the cards themselves), as a
 *  person would: Ionic asks for the next ones. */
export async function scrollToEnd(page: Page): Promise<void> {
  await infinite(page)
    .first()
    .evaluate(async (el) => {
      // `ion-content` scrolls an element of its own; the cards of a table that fills its page are their own scroller.
      // Ionic's `scrollToBottom` is not awaited: it can wait on an animation that never ends while the rows grow.
      const host = el.closest<HTMLElement & { getScrollElement?: () => Promise<HTMLElement> }>('ion-content, .ion-content-scroll-host');
      const scroller = host?.getScrollElement ? await host.getScrollElement() : host;
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
    });
}
