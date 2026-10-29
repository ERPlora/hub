// flow: los paneles de las apps en el Inicio (BASE-F06) y el panel de la cola de contingencia de VeriFactu (VERIFACTU-F31)
// The text under a panel's figure (FIX-HUB-HOME-WIDGET-OPTIONS-LAZY-TEXT): VeriFactu's «Cola de contingencia» on the
// owner's board of hub `a` says under the server's figure what it counts, «En cola de contingencia» in Spanish and
// «In contingency queue» in English, as the old module did (its module.json, `verifactu.contingency` options.label);
// the board list no longer fails on a translated text among a panel's options. Each size and language leaves the
// capture `FIX-HUB-HOME-WIDGET-OPTIONS-LAZY-TEXT[-en]-<width>`.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, horizontalOverflow, login, shot, shown, untilStill } from './helpers';

const KEY = 'FIX-HUB-HOME-WIDGET-OPTIONS-LAZY-TEXT';
const PANEL = 'verifactu.contingency';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
const LANGUAGES = [
  { code: 'es', locale: 'es-ES', title: 'Cola de contingencia', label: 'En cola de contingencia', shot: KEY },
  { code: 'en', locale: 'en-US', title: 'Contingency queue', label: 'In contingency queue', shot: `${KEY}-en` },
];
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';

/** The owner on `a` in `language` (the Hub's language cookie, as the sign-in sets it from the account), on the Home
 *  with only the queue's panel on the board. */
async function owner(
  browser: Browser,
  viewport: { width: number; height: number },
  language: (typeof LANGUAGES)[number],
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: language.locale });
  await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify([PANEL])]);
  const page = await context.newPage();
  await login(page, A, '/');
  await context.addCookies([{ name: 'django_language', value: language.code, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language.code}`));
  // The owner's Spanish session with the queue's panel for the fleet's visual sweep
  // (`ui-clip-sweep.sh --storage-state`), when asked.
  if (language.code === 'es' && process.env.E2E_SAVE_STORAGE_STATE) {
    await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  }
  return { context, page };
}

const panel = (page: Page): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${PANEL}"]`);

for (const language of LANGUAGES) {
  for (const size of SIZES) {
    test(`BASE-F06 VERIFACTU-F31 at ${size.label} in ${language.code}: the queue's panel says under its figure what it counts`, async ({ browser }) => {
      const { context, page } = await owner(browser, { width: size.width, height: size.height }, language);
      try {
        const queue = panel(page);
        await expect(queue).toHaveAttribute('aria-busy', 'false');
        await expect(queue.locator('[data-testid="widget-error"]')).toHaveCount(0);
        await expect(queue.locator('[data-testid="widget-title"]')).toHaveText(language.title);

        // The server's figure, and under it what it counts in the reader's language.
        const summary = await api<{ queued_count: number }>(context, A, 'GET', '/verifactu/stats/contingency_summary');
        expect(summary.status).toBe(200);
        await expect(queue.locator('[data-testid="widget-value"]')).toHaveText(
          new Intl.NumberFormat(language.locale).format(summary.data.queued_count),
        );
        await expect(queue.locator('[data-testid="widget-label"]')).toHaveText(language.label);
        await expect(queue.locator('[data-testid="widget-label"]')).toBeVisible();

        // The board in sight, with no sideways scroll.
        await queue.evaluate((element) => element.scrollIntoView({ block: 'center' }));
        await untilStill(page);
        const overflow = await horizontalOverflow(page);
        expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
        await page.screenshot({ path: shot(`${language.shot}-${size.label}`) });
      } finally {
        await context.close();
      }
    });
  }
}
