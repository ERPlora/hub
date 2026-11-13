// What the e2e of the Home share: a person of `a` signed in in Spanish on it, its setup card («Configura tu negocio»)
// and a step's row in it, and the panels of its widget board.
import { type Browser, type BrowserContext, expect, type Locator, type Page } from '@playwright/test';

import { A, capturedFitting, type Credentials, login, OWNER, shown } from './helpers';

/** The setup card of the Home on view. */
export const setupCard = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');

/** The row of the step `key` in the setup card of the Home on view. */
export const setupRow = (page: Page, key: string): Locator => setupCard(page).locator(`[data-testid="setup-row"][data-key="${key}"]`);

/** The panel `key` of the Home's widget board. */
export const boardWidget = (page: Page, key: string): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);

/** The localStorage key of the Home's widget board: the panels on it. */
export const HOME_BOARD = 'dashboard-hub';

/** The Home is painted once its setup card has read its steps. */
export const setupCardRead = (page: Page): Promise<void> => expect(setupCard(page)).toHaveAttribute('aria-busy', 'false');

/** The Home is painted once «My apps» shows. */
export const myAppsShown = (page: Page): Promise<void> => expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();

/** The Home is painted once its widget board shows. */
export const boardShown = (page: Page): Promise<void> => expect(shown(page).locator('[data-testid="widget-board"]')).toBeVisible();

/** Who visits the Home and how it is laid out. */
export interface HomeVisit {
  /** The owner unless said. */
  who?: Credentials;
  /** The widget board laid out before the visit: its key in the browser's storage and the panels on it. */
  board?: { key: string; panels: string[] };
  /** Whether the session is saved for the fleet's visual sweep when asked (`E2E_SAVE_STORAGE_STATE`); yes unless said. */
  sweep?: boolean;
}

/** A person of `a` signed in in Spanish (the Hub's language cookie, as the sign-in sets it from the account) on the Home
 *  at `viewport`, once `ready` says it is painted; every `/api/live` the page opens is timed in `streams`. */
export async function spanishOnTheHome(
  browser: Browser,
  viewport: { width: number; height: number },
  ready: (page: Page) => Promise<void>,
  visit: HomeVisit = {},
): Promise<{ context: BrowserContext; page: Page; streams: number[] }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const { board } = visit;
  if (board) await context.addInitScript(([key, panels]) => localStorage.setItem(key, panels), [board.key, JSON.stringify(board.panels)]);
  const page = await context.newPage();
  const streams: number[] = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/live')) streams.push(Date.now());
  });
  await login(page, A, '/', visit.who ?? OWNER);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await ready(page);
  if ((visit.sweep ?? true) && process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page, streams };
}

/** The owner on `a` in Spanish on the Home, once its setup card has read its steps. */
export const spanishOwnerOnTheSetupCard = (browser: Browser, viewport: { width: number; height: number }) =>
  spanishOnTheHome(browser, viewport, setupCardRead);

/** The owner on `a` in Spanish on the Home once its setup card has read its steps, with `panels` laid out on its board
 *  (and then the session saved for the fleet's visual sweep, when asked). */
export const spanishOwnerWithPanels = (browser: Browser, viewport: { width: number; height: number }, panels?: string[]) =>
  spanishOnTheHome(browser, viewport, setupCardRead, { board: panels && { key: HOME_BOARD, panels }, sweep: Boolean(panels) });

/** The owner on `a` in Spanish on the Home, once «My apps» shows. */
export const spanishOwnerOnMyApps = (browser: Browser, viewport: { width: number; height: number }) =>
  spanishOnTheHome(browser, viewport, myAppsShown);

/** «Ver todo» when the card folds the step `key` away (a «Recomendado» step while more important ones are pending, two
 *  rows on a phone), and the step in sight. */
export async function unfoldedTo(page: Page, key: string): Promise<void> {
  await setupCardRead(page);
  const toggle = setupCard(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') await toggle.click();
  await expect(setupRow(page, key)).toBeVisible();
}

/** The step `key` of the setup card: its row, its pill and its «Configurar» link; «Ver todo» until it is in sight
 *  (`unfolded`); the step in sight, its pill saying `says`, its row centred on screen and, given a `shot`, captured
 *  fitting the screen (`inSight`); back on the Home, the step done with nothing left to configure (`backDone`); and
 *  the step done, out of the folded list and «Hecho» under «Ver todo», with
 *  nothing left to configure (`doneUnderTheFold`). */
export function setupStep(key: string) {
  const row = (page: Page): Locator => setupRow(page, key);
  const pill = (page: Page): Locator => row(page).locator('[data-testid="setup-pill"]');
  const configure = (page: Page): Locator => row(page).locator(`[data-testid="setup-configure-${key}"]`);
  const unfolded = (page: Page): Promise<void> => unfoldedTo(page, key);
  return {
    row,
    pill,
    configure,
    unfolded,
    inSight: async (page: Page, says: string, shot?: { name: string; label: string }): Promise<void> => {
      await unfolded(page);
      await expect(pill(page)).toHaveText(says);
      await row(page).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      if (shot) await capturedFitting(page, shot.name, shot.label);
    },
    backDone: async (page: Page): Promise<void> => {
      await page.goBack();
      await expect(page).toHaveURL(`${A}/`);
      await unfolded(page);
      await expect(pill(page)).toHaveText('Hecho');
      await expect(configure(page)).toHaveCount(0);
    },
    doneUnderTheFold: async (page: Page): Promise<void> => {
      await expect(row(page)).toHaveCount(0);
      await setupCard(page).locator('[data-testid="setup-toggle"]').click();
      await expect(pill(page)).toHaveText('Hecho');
      await expect(configure(page)).toHaveCount(0);
    },
  };
}

/** Waits until the page has opened no `/api/live` for longer than `quietMs`: every subscription of the screen is declared
 *  (and, waited past a subscription's release, every one of a screen left behind is gone). */
export async function streamsQuiet(streams: number[], quietMs = 1_000): Promise<void> {
  await expect.poll(() => Date.now() - (streams.at(-1) ?? 0), { timeout: 15_000 }).toBeGreaterThan(quietMs);
}
