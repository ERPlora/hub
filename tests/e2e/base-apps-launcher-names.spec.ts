// flow: BASE-F05 — the «My apps» sheet of the bar, in Spanish, with Automations on: «Automatizaciones», the longest
// word of the apps' Spanish names, stays one word on one line at every size, desktop, tablet in both orientations and
// phone. A word wider than its tile ends in «…» and the whole name stays the tile's title and accessible name.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, saveSessionForTheSweep, signedInSpanish, turnOffTurnedOn, turnOnMissing } from './helpers';
import { openApps } from './topbar';
import { splitWords } from './words';

const SIZES = [
  { label: '1440', width: 1440, height: 900 },
  { label: '1280', width: 1280, height: 800 },
  { label: '834', width: 834, height: 1194 },
  { label: '375', width: 375, height: 667 },
] as const;
const LONGEST = 'Automatizaciones';

let context: BrowserContext;
let page: Page;
const turnedOn: string[] = [];

test.beforeAll(async ({ browser }) => {
  ({ context, page } = await signedInSpanish(browser, { width: 1440, height: 900 }, '/'));
  await saveSessionForTheSweep(context);
  await turnOnMissing(context, A, ['flow'], turnedOn);
  await page.reload();
});

test.afterAll(async () => {
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

test('BASE-F05: the sheet never splits an app name inside a word, and a name that does not fit ends in «…»', async () => {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    const sheet = await openApps(page);
    const tile = sheet.locator('[data-testid=apps-launcher-app]', { hasText: LONGEST });
    const name = tile.locator('.apps-launcher-name');
    await expect(tile).toHaveAttribute('title', LONGEST);
    await expect(tile).toHaveAttribute('aria-label', LONGEST);
    await expect(name).toHaveText(LONGEST);
    await expect.poll(() => splitWords(name), { message: `«${LONGEST}» split inside the word at ${size.label}` }).toEqual([]);
    const cut = await name.evaluate((el) => ({ wider: el.scrollWidth > el.clientWidth, overflow: getComputedStyle(el).textOverflow }));
    if (cut.wider) expect(cut.overflow, `a name wider than its tile ends in «…» at ${size.label}`).toBe('ellipsis');
    expect(await horizontalOverflow(page), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
    await tile.scrollIntoViewIfNeeded();
    await capture(page,`BASE-F05-apps-launcher-names-${size.label}`);
    await sheet.locator('[data-testid=apps-launcher-close]').click();
    await expect(sheet).toBeHidden();
  }
});
