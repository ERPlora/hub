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

/** Scrolls the table's rows to their end, as a person would: Ionic asks for the next ones. */
export async function scrollToEnd(page: Page): Promise<void> {
  await infinite(page).first().scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 2000);
}
