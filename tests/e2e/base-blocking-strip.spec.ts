// flow: BASE-F01
// The red strip «Todavía no puedes facturar» (BASE-F01 step 5; base's WORKBOOK «La franja…») and Invoicing's own
// notice under it say the same sentence in Spanish, with the same word for the sales receipt: «tique», never «ticket»
// (FIX-HUB-BASE-BLOCKING-STRIP-SAYS-TICKET-WHERE-INVOICING-SAYS-TIQUE; the symptom was hub#283's
// `FIX-INVOICE-SETUP-HOOKS-INVOICE-F21-employee-390.png`). Hub `a` with no issuer, its owner in Spanish, on Invoicing →
// Invoices, at the three widths. The hub's issuer row is parked for the run and put back as it was after it.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';

const KEY = 'FIX-HUB-BASE-BLOCKING-STRIP-SAYS-TICKET-WHERE-INVOICING-SAYS-TIQUE';
/** The hub's issuer, parked while the run needs a hub without one. */
const PARKED = 'e2e_base_blocking_strip_issuer';
/** The one sentence both say, as base's and Invoicing's Spanish catalogues word it. */
const SENTENCE = 'No se podrá emitir ningún tique ni factura hasta que configures esto:';

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  psql([`drop table if exists ${PARKED}`, `create table ${PARKED} as select * from invoice_issuer`, 'delete from invoice_issuer'].join('; '));
});

test.afterAll(() => {
  psql(['delete from invoice_issuer', `insert into invoice_issuer select * from ${PARKED}`, `drop table ${PARKED}`].join('; '));
});

/** The owner of `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account). */
async function spanish(browser: Browser, viewport: { width: number; height: number }): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, '/', OWNER);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  return { context, page };
}

for (const size of VIEWPORTS) {
  test(`BASE-F01 at ${size.label}: the strip and Invoicing's notice say «tique» with the same sentence`, async ({ browser }) => {
    const { context, page } = await spanish(browser, { width: size.width, height: size.height });
    try {
      await page.goto(`${A}/invoice/invoices`);
      await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
      const strip = shown(page).locator('[data-testid="blocking-strip"]');
      await expect(strip).toBeVisible();
      await expect(strip.locator('.blocking-strip-title')).toHaveText('Todavía no puedes facturar');
      await expect(strip.locator('.blocking-strip-text')).toHaveText(SENTENCE);
      const notice = shown(page).locator('[data-testid="invoice-issuer-notice"]');
      await expect(notice).toBeVisible();
      await expect(notice).toContainText(SENTENCE);
      await expect(strip).not.toContainText(/\btickets?\b/i);
      await expect(notice).not.toContainText(/\btickets?\b/i);
      await untilStill(page);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
