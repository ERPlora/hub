// The end of the hub's topbar, as a person reaches it. From a tablet «My apps», the assistant's sparkles and the bell
// are buttons on the bar. On a phone (under 768 px) the bar keeps two buttons at its end, the shell's «⋮» and the bell:
// «My apps» and the assistant are rows of «⋮», and each one opens once the menu has gone.
import { expect, type Locator, type Page } from '@playwright/test';

import { MY_APPS_DOOR, shown } from './helpers';

/** Whether the page is a phone's (under 768 px): the shell folds «My apps» and the assistant into «⋮». */
export const compactBar = (page: Page): boolean => (page.viewportSize()?.width ?? 1280) < 768;

/** The topbar of the screen on view. */
export const topbar = (page: Page): Locator => shown(page).locator('ion-header.app-topbar');

/** The shell's «⋮» of the screen on view: on a phone's bar only. */
export const topbarMore = (page: Page): Locator => shown(page).locator('[data-testid=topbar-more]');

/** The rows of «⋮» once open: Ionic presents its popover outside the page. */
export const topbarMoreMenu = (page: Page): Locator =>
  page.locator('ion-popover:not(.overlay-hidden) [data-testid=topbar-more-menu]');

/** What opens «My apps» on the bar of the screen on view: its ⠿ button, or «⋮» on a phone. */
export const appsDoor = (page: Page): Locator => topbar(page).locator(MY_APPS_DOOR);

/** What opens the assistant on the bar of the screen on view: its sparkles, or «⋮» on a phone. */
export const assistantDoor = (page: Page): Locator =>
  compactBar(page) ? topbarMore(page) : topbar(page).locator('[data-testid=assistant-button]');

/** Opens «⋮» and picks its row `id`: what that row opens comes once the menu has gone. */
async function pickFromMore(page: Page, id: string): Promise<void> {
  await topbarMore(page).click();
  await topbarMoreMenu(page).locator(`[data-testid=${id}]`).click();
}

/**
 * Expects the view's action `id` on its bar. On a phone the bar folds the view's actions into «⋮» when they do not fit
 * beside its other buttons (a help window's «?», the bell): there it is looked for in the open menu, closed after.
 */
export async function expectBarAction(page: Page, id: string): Promise<void> {
  if (!compactBar(page) || !(await topbarMore(page).isVisible())) {
    await expect(shown(page).locator(`[data-testid=${id}]`)).toBeVisible();
    return;
  }
  await topbarMore(page).click();
  await expect(topbarMoreMenu(page).locator(`[data-testid=${id}]`)).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(topbarMoreMenu(page)).toBeHidden();
}

/** Presses the assistant's sparkles (its row of «⋮» on a phone): they open the panel, or close it when open. */
export async function pressAssistant(page: Page): Promise<void> {
  if (compactBar(page)) await pickFromMore(page, 'assistant-button');
  else await assistantDoor(page).click();
}

/** Opens the assistant's panel from the bar, unless it is open already (its state is the tab's, across screens and
 *  reloads), and returns it once open with its box ready. */
export async function openAssistant(page: Page): Promise<Locator> {
  const panel = page.locator('[data-testid=assistant-panel]');
  await expect(assistantDoor(page)).toBeVisible();
  if ((await panel.getAttribute('data-open')) !== 'true') await pressAssistant(page);
  await expect(panel).toHaveAttribute('data-open', 'true');
  await expect(panel.locator('[data-testid=assistant-input] textarea')).toBeVisible();
  return panel;
}

/** Presses «My apps» (its row of «⋮» on a phone). */
export async function pressMyApps(page: Page): Promise<void> {
  if (compactBar(page)) await pickFromMore(page, 'topbar-more-apps');
  else await appsDoor(page).click();
}

/**
 * Opens the «My apps» sheet from the screen on view and returns it. Ionic moves a presented modal to `ion-app`,
 * outside the page, so it is found on the page (the presented one), not in `shown(page)`.
 */
export async function openApps(page: Page): Promise<Locator> {
  await pressMyApps(page);
  const sheet = page.locator('ion-modal[data-testid=apps-launcher]:not(.overlay-hidden)');
  await expect(sheet.locator('[data-testid=apps-launcher-app]').first()).toBeVisible();
  return sheet;
}

/** The names «My apps» (the menu of the apps, from the session) lists now. */
export async function menuApps(page: Page): Promise<string[]> {
  const sheet = await openApps(page);
  const names = (await sheet.locator('[data-testid=apps-launcher-app]').allInnerTexts()).map((name) => name.trim());
  await sheet.locator('[data-testid=apps-launcher-close]').click();
  await expect(sheet).toBeHidden();
  return names;
}

export interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The title's text, centred on its bar (Ionic's ios title), within 4 px; returns both boxes. */
export async function expectTitleCentred(page: Page, label: string): Promise<{ title: Box; toolbar: Box }> {
  const text = await topbar(page)
    .locator('ion-title')
    .evaluate((el) => {
      const inner = el.shadowRoot?.querySelector('.toolbar-title') ?? el;
      const range = document.createRange();
      range.selectNodeContents(inner);
      const box = (range.getClientRects().length ? range : inner).getBoundingClientRect();
      return { x: box.x, y: box.y, width: box.width, height: box.height };
    });
  const toolbar = (await topbar(page).locator('ion-toolbar').boundingBox())!;
  const centre = (box: Box) => box.x + box.width / 2;
  expect(Math.abs(centre(text) - centre(toolbar)), `${label}: the title is centred`).toBeLessThanOrEqual(4);
  return { title: text, toolbar };
}
