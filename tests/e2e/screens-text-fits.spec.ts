// flow: APPOINTMENT-F01, APPOINTMENT-F27 — every screen of the apps the salon's and the restaurant's QA journeys walk
// (journey-screens.ts), in Spanish and with names as long as real ones (text-fits-seed.ts), at the three sizes, reads
// its texts whole (text-cut.ts): no text cut by its box with no title to read it whole, no short word split over two
// lines. A site already known is in text-fits-known.json with its issue; anything else fails, with a screenshot of
// where it showed. The walk of every screen runs every night with the rest of the e2e; the browser smoke, which
// stops a merge, runs the agenda «By professional», day and week, which sits behind a switch of its screen.
// Every step that waits on the browser has a time limit (within-time.ts): a page that never answers fails its test.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, settled, shown, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';
import { journeyApps, registeredRoutes, screensAmong } from './journey-screens';
import { cutTexts, measureInOneFont } from './text-cut';
import { KNOWN_SITES, staleScreens } from './text-fits-known';
import { BOOKED_DAY, removeLongTexts, seedLongTexts } from './text-fits-seed';
import { withinTime } from './within-time';

const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
] as const;

/** What a screen shows while it loads: it is measured once nothing of this is on view. */
const LOADING = ['ion-spinner', 'ion-loading', 'ion-skeleton-text', '[aria-busy="true"]', '[data-testid$="-loading"]']
  .map((selector) => `${selector}:visible`)
  .join(', ');

/** The screens behind a switch: the agenda's «By professional», by day and by week, on the booked day. */
const SWITCHED = [
  { screen: 'agenda · by professional · day', open: ['appointment-toolbar-view-staff', 'appointment-toolbar-span-day'] },
  { screen: 'agenda · by professional · week', open: ['appointment-toolbar-view-staff', 'appointment-toolbar-span-week'] },
] as const;

/** How long a step that waits on the browser may take: a navigation, a scan of the page, a screenshot. */
const STEP_MS = 30_000;

interface Seen {
  screen: string;
  size: string;
  kind: string;
  box: string;
  text: string;
}

const addressOf = (screen: string): string => (screen === '/appointment/agenda' ? `${screen}?date=${BOOKED_DAY}` : screen);
const known = (seen: Seen): boolean => KNOWN_SITES.some((site) => site.box === seen.box && site.screens.includes(seen.screen));
const described = (seen: Seen): string => `${seen.screen} · ${seen.size} · ${seen.kind} · ${seen.box} «${seen.text}»`;
const snapName = (seen: Seen): string => `text-fits-${seen.screen.replace(/[^a-z0-9]+/gi, '-')}-${seen.size}`;

/** The texts cut on the screen on view at each size, a screenshot of each size that cuts one it does not know. */
async function measured(page: Page, screen: string): Promise<Seen[]> {
  const out: Seen[] = [];
  for (const size of SIZES) {
    const where = `${screen} at ${size.label}`;
    await withinTime(`resizing ${where}`, page.setViewportSize(size), STEP_MS);
    await withinTime(`settling ${where}`, settled(page), STEP_MS);
    // A page Ionic is still bringing in is painted at opacity 0: measured then, it would show nothing to cut.
    await expect(shown(page), `${where} on view`).not.toHaveClass(/ion-page-invisible/, { timeout: 20_000 });
    await expect(page.locator(LOADING), `${where} still loading`).toHaveCount(0, { timeout: 20_000 });
    await withinTime(`settling ${where}`, settled(page), STEP_MS);
    const cuts = (await withinTime(`the scan of ${where}`, cutTexts(page), STEP_MS)).map((cut) => ({ screen, size: size.label, ...cut }));
    if (cuts.some((cut) => !known(cut))) await withinTime(`the screenshot of ${where}`, capture(page, snapName(cuts[0])), STEP_MS);
    out.push(...cuts);
  }
  return out;
}

/** Opens `address`, with a time limit: Playwright sets none on a navigation in this suite. */
const opened = (page: Page, address: string): Promise<unknown> =>
  withinTime(`opening ${address}`, page.goto(address, { timeout: STEP_MS }), STEP_MS + 5_000);

/** The texts cut on the agenda «By professional», by day and by week, on the booked day. */
async function agendaCuts(page: Page): Promise<Seen[]> {
  const seen: Seen[] = [];
  for (const switched of SWITCHED) {
    await page.setViewportSize(SIZES[0]);
    await opened(page, addressOf('/appointment/agenda'));
    for (const testid of switched.open) await page.locator(`[data-testid=${testid}]:visible`).click({ timeout: STEP_MS });
    seen.push(...(await measured(page, switched.screen)));
  }
  return seen;
}

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  ({ context, page } = await signedInSpanish(browser, SIZES[0], '/'));
  await measureInOneFont(context);
  await turnOnMissing(context, A, journeyApps().filter((app) => app !== 'base'), turnedOn);
  await seedLongTexts(context);
});

test.afterAll(async () => {
  await removeLongTexts(context);
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

test('the agenda «By professional», by day and by week, reads its customers and services whole at the three sizes @smoke', async () => {
  test.setTimeout(180_000);
  const seen = await agendaCuts(page);
  expect(seen.filter((cut) => !known(cut)).map(described), 'texts cut where no site is known').toEqual([]);
});

test('every screen of the salon and restaurant journeys reads its texts whole, in Spanish, at the three sizes', async () => {
  test.setTimeout(600_000);
  await opened(page, '/');
  const screens = screensAmong(await withinTime('reading the routes', registeredRoutes(page), STEP_MS), journeyApps());
  const seen = await agendaCuts(page);
  for (const screen of screens) {
    await opened(page, addressOf(screen));
    seen.push(...(await measured(page, screen)));
  }
  expect(seen.filter((cut) => !known(cut)).map(described), 'texts cut where no site is known').toEqual([]);
  expect(staleScreens(seen), 'known sites that no longer cut there: take those screens out of text-fits-known.json').toEqual([]);
});
