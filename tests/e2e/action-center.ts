// The hub's action center as a person meets it (`@erplora/ui`'s bell, arrival card and panel, fed by base's
// `useHubActionNotices`): the bell at the end of the bar on every size, its pill with the number, the card a new
// notice comes as, and the panel with the gravest notice on top and the others in rows.
import { type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, shown } from './helpers';
import { api } from './hub-api';

/** The bell of the screen on view: plain with nothing pending, a pill with the number and the gravity otherwise. */
export const actionBell = (page: Page): Locator => shown(page).locator('[data-testid=action-bell]');

/** The number on the bell's pill. */
export const bellBadge = (page: Page): Locator => actionBell(page).locator('.action-bell__count');

/** The bell says `total` on its pill, or no number when it is 0. */
export async function bellSays(page: Page, total: number, options: { timeout?: number } = {}): Promise<void> {
  if (total > 0) await expect(bellBadge(page)).toHaveText(String(total), options);
  else await expect(bellBadge(page)).toHaveCount(0, options);
}

/** What the bell counts now, as the server says: every counter of `base.bell.counters` and one for «You cannot issue
 *  invoices yet» while a step that blocks invoicing is pending (`base.setup.status`). */
export async function bellTotal(context: BrowserContext, origin: string = A): Promise<number> {
  const [bell, setup] = await Promise.all([
    api<{ counters: { count: number }[] }>(context, origin, 'GET', '/home/bell'),
    api<{ blocking_pending: number }>(context, origin, 'GET', '/home/setup'),
  ]);
  expect(bell.status).toBe(200);
  expect(setup.status).toBe(200);
  return bell.data.counters.reduce((sum, counter) => sum + counter.count, 0) + (setup.data.blocking_pending > 0 ? 1 : 0);
}

/** A counter of the bell as the server sends it (`base.bell.counters`), its words in the person's language. */
export interface ServerCounter {
  key: string;
  count: number;
  severity: 'danger' | 'warning' | 'info';
  title: string;
  body: string | null;
  action_label: string;
  due: string | null;
}

/** The counter `key` the server gives the person of `context` now; undefined while it is at zero. */
export async function serverCounter(context: BrowserContext, key: string, origin: string = A): Promise<ServerCounter | undefined> {
  const bell = await api<{ counters: ServerCounter[] }>(context, origin, 'GET', '/home/bell');
  expect(bell.status).toBe(200);
  return bell.data.counters.find((counter) => counter.key === key);
}

/** How much of the deadline ring on the bell's pill is left: 1 with no deadline or a week or more away, 0 when due. */
export async function bellRingLeft(page: Page): Promise<number> {
  return Number(await actionBell(page).locator('.action-bell__ring').getAttribute('data-progress'));
}

/** The panel of the action center: Ionic moves a presented modal to `ion-app`, outside the page. */
export const actionPanel = (page: Page): Locator => page.locator('ion-modal[data-testid=action-panel]');

/** The card a new notice comes as, under the bar, before it settles in the bell; not the copy of it that flies to
 *  the bell as it goes (`action-arrival-ghost`). */
export const arrivalCard = (page: Page): Locator => page.locator('[data-testid=action-arrival]:not(.action-arrival-ghost)');

/** The notice of the panel that says `text`: the featured one on top, or one of the rows below it. */
export const noticeIn = (panel: Locator, text: string | RegExp): Locator =>
  panel.locator('[data-testid=action-featured], [data-testid=action-row]').filter({ hasText: text });

/** The notice on top of the panel, with its sentence and its buttons. */
export const featuredNotice = (panel: Locator): Locator => panel.locator('[data-testid=action-featured]');

/** Opens the panel from the bell and resolves once Ionic has presented it; returns it. */
export async function openActionCenter(page: Page): Promise<Locator> {
  const presented = page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const done = (event: Event) => {
          if ((event.target as Element).getAttribute('data-testid') !== 'action-panel') return;
          document.removeEventListener('ionModalDidPresent', done);
          resolve();
        };
        document.addEventListener('ionModalDidPresent', done);
      }),
  );
  await actionBell(page).click();
  await presented;
  const panel = actionPanel(page);
  await expect(panel).toBeVisible();
  return panel;
}

/** Closes the panel with Esc and waits until Ionic has let it go. */
export async function closeActionCenter(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await expect(actionPanel(page)).toBeHidden();
}

/** Opens the panel and puts the notice that says `text` on top (tapping its row when it is not there); returns it. */
export async function featureNotice(page: Page, text: string | RegExp): Promise<Locator> {
  const panel = await openActionCenter(page);
  const featured = featuredNotice(panel);
  // The notice may still be on its way (the panel loading, or the live result not here yet): wait until it is listed.
  await expect(noticeIn(panel, text).first()).toBeVisible();
  const row = panel.locator('[data-testid=action-row]').filter({ hasText: text });
  if (await row.count()) await row.first().click();
  await expect(featured).toContainText(text);
  return featured;
}

/** The button of the featured notice that says `label`. */
export const noticeButton = (featured: Locator, label: string | RegExp): Locator =>
  featured.locator('ion-button').filter({ hasText: label });

/** The featured notice says the server's heading, sentence and button for `counter`. */
export async function expectTheServersWords(featured: Locator, counter: ServerCounter): Promise<void> {
  await expect(featured.locator('h3')).toHaveText(counter.title);
  const body = featured.locator('.action-featured__body');
  if (counter.body) await expect(body).toHaveText(counter.body);
  else await expect(body).toHaveCount(0);
  await expect(noticeButton(featured, counter.action_label)).toBeVisible();
}
