// The way in of a shared till, as a person goes through it: the keys of the PIN pad on screen and the user card of the
// side menu, whose entries are «Switch user» and «Sign out».
import type { Page } from '@playwright/test';

import { shown } from './helpers';

/** Types `digits` on the PIN pad of the screen on view. */
export async function pressPin(page: Page, digits: string): Promise<void> {
  for (const digit of digits) await shown(page).getByTestId(`pinpad-key-${digit}`).click();
}

/** From this width the side menu is pinned; under it, a drawer the bar's menu button opens. */
const PINNED_MIN = 992;

/** The person at the top of the side menu tapped, on their name (the drawer opened first where the menu is one): their
 *  menu presented. */
export async function openUserCard(page: Page): Promise<void> {
  if ((page.viewportSize()?.width ?? PINNED_MIN) < PINNED_MIN) {
    const opened = page.evaluate(() => new Promise<void>((resolve) => document.addEventListener('ionDidOpen', () => resolve(), { once: true })));
    await shown(page).locator('ion-menu-button').click();
    await opened;
  }
  const presented = page.evaluate(
    () => new Promise<void>((resolve) => document.addEventListener('ionPopoverDidPresent', () => resolve(), { once: true })),
  );
  await page.locator('ion-menu [data-testid="user-menu-trigger"] .sidebar-user-name').click();
  await presented;
}

/** The user menu of the side menu (pinned at 1440), and the entry `id` in it. */
export async function userMenu(page: Page, id: string): Promise<void> {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openUserCard(page);
  await page.locator(`ion-popover [data-testid="user-menu-${id}"]`).click();
}
