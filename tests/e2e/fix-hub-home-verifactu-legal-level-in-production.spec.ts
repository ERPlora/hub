// flow: «Termina de configurar tu negocio» and the action center's «Todavía no puedes facturar» (BASE-F01, BASE-F04)
// with VeriFactu's step (VERIFACTU-F08)
// A hub in production whose way to the AEAT broke (ERPlora's signed
// authorisation revoked) has every new sale refused, so its Home says so. «Configura VeriFactu» is «Necesario para
// facturar» in «Termina de configurar tu negocio», and the action center's «Todavía no puedes facturar» names it in its
// sentence: to the owner with «Configurar VeriFactu», to the employee with no button and «An administrator has to set
// this up.». In testing the same hub stays «Importante», out of that notice: it sells without a way.
// Production is the configuration's environment, set in the database for the run: no local server opens real filing
// and nothing is sent (the sale is refused before any record is made). The photo is sent the way the SaaS sends it
// (`PUT /internal/hubs/{id}/state`, signed); what the run changes in VeriFactu's configuration and in `a`'s photo is
// put back after it (or removed, if the run made it).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { bellSays, bellTotal, featureNotice, noticeButton, noticeIn, openActionCenter } from './action-center';
import { capture } from './capture';
import { api } from './hub-api';
import { login } from './login';
import { EMPLOYEE, OWNER } from './saas';
import { horizontalOverflow, shown } from './screen';
import { A } from './stack';
import { keepVerifactu, putVerifactuBack, revokedIn } from './verifactu-helpers';

const KEY = 'FIX-HUB-HOME-VERIFACTU-LEGAL-LEVEL-IN-PRODUCTION';
const STEP = 'verifactu.sending_route';
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];
test.beforeAll(() => {
  keepVerifactu('e2e_fix_vf_legal');
});

test.afterAll(() => {
  putVerifactuBack();
});

/** A person on `a` in `language` (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function onHome(
  browser: Browser,
  viewport: { width: number; height: number },
  { language = 'es', who = OWNER } = {},
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: language === 'es' ? 'es-ES' : 'en-GB' });
  const page = await context.newPage();
  await login(page, A, '/', who);
  await context.addCookies([{ name: 'django_language', value: language, domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${language}`));
  await expect(card(page)).toHaveAttribute('aria-busy', 'false');
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
  if (who === OWNER && language === 'es' && process.env.E2E_SAVE_STORAGE_STATE) {
    await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  }
  return { context, page };
}

const card = (page: Page): Locator => shown(page).locator('[data-testid="setup-card"]');
const row = (page: Page): Locator => card(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);

/** «Todavía no puedes facturar» on top of the action center, once the bell has counted what the server says. */
async function blockingNotice(page: Page, context: BrowserContext, title: string): Promise<Locator> {
  await bellSays(page, await bellTotal(context));
  const featured = await featureNotice(page, title);
  await expect(featured.locator('h3')).toHaveText(title);
  return featured;
}

/** The sentence of a notice: the steps it names (another ⛔, as the business's tax details, may stand beside them). */
const sentence = (featured: Locator): Locator => featured.locator('.action-featured__body');

test.describe.configure({ mode: 'serial' });

for (const size of SIZES) {
  test(`BASE-F01 VERIFACTU-F08 at ${size.label}: in production with the authorisation revoked, «Configura VeriFactu» is «Necesario para facturar» and «Todavía no puedes facturar» names it`, async ({ browser }) => {
    await revokedIn('production');
    const { context, page } = await onHome(browser, { width: size.width, height: size.height });
    try {
      // The sale is refused from now on (what the notice warns of), and the Home says it is a wall.
      const config = await api<{ environment: string; issue_blocker: { code: string } | null }>(context, A, 'GET', '/verifactu/config');
      expect(config.status).toBe(200);
      expect([config.data.environment, config.data.issue_blocker?.code]).toEqual(['production', 'representation_not_approved']);
      // Folded, a phone's two rows included: the ⛔ goes before the «Importante» ones, with no «Ver todo» to press, and
      // what it leaves out of the fold is one press away (hub#801).
      await expect(card(page)).toHaveAttribute('aria-busy', 'false');
      const rows = card(page).locator('[data-testid="setup-row"]');
      await expect(rows.first().locator('[data-testid="setup-pill"]')).toHaveText('Necesario para facturar');
      await expect(row(page).locator('.setup-row-title')).toHaveText('Configura VeriFactu');
      await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Necesario para facturar');
      const folded = await rows.count();
      await card(page).locator('[data-testid="setup-toggle"]').click();
      await expect.poll(() => rows.count()).toBeGreaterThan(folded);

      // The action center's «Todavía no puedes facturar»: the consequence, the step and its «Configurar VeriFactu».
      const featured = await blockingNotice(page, context, 'Todavía no puedes facturar');
      await expect(sentence(featured)).toContainText('No se podrá emitir ningún tique ni factura hasta que configures esto:');
      await expect(sentence(featured)).toContainText('Configura VeriFactu');
      const configure = noticeButton(featured, 'Configurar VeriFactu');
      await expect(configure).toBeVisible();
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await capture(page, `${KEY}-${size.label}`);

      await configure.click();
      await expect(page).toHaveURL(`${A}/verifactu/config`);
    } finally {
      await context.close();
    }
  });
}

test('BASE-F04 VERIFACTU-F08: in production the employee is told too, in English, with nothing to set up', async ({ browser }) => {
  await revokedIn('production');
  const { context, page } = await onHome(browser, { width: 1440, height: 900 }, { language: 'en', who: EMPLOYEE });
  try {
    await expect(row(page).locator('.setup-row-title')).toHaveText('Set up VeriFactu');
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Needed to invoice');
    const featured = await blockingNotice(page, context, 'You cannot issue invoices yet');
    await expect(sentence(featured)).toContainText('Set up VeriFactu');
    await expect(sentence(featured)).toContainText('An administrator has to set this up.');
    await expect(featured.locator('ion-button')).toHaveCount(0);
    await capture(page, `${KEY}-employee-en-1440`);
  } finally {
    await context.close();
  }
});

test('BASE-F01: in testing the same revoked authorisation stays «Importante», out of «Todavía no puedes facturar»', async ({ browser }) => {
  await revokedIn('testing');
  const { context, page } = await onHome(browser, { width: 1440, height: 900 });
  try {
    const config = await api<{ environment: string; issue_blocker: unknown }>(context, A, 'GET', '/verifactu/config');
    expect([config.data.environment, config.data.issue_blocker]).toEqual(['testing', null]);
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');
    // The business's tax details may be a wall of their own while the hub has no issuer; VeriFactu's step in testing
    // never is: the notice, when there is one, does not name it.
    const setup = await api<{ blocking_pending: number }>(context, A, 'GET', '/home/setup');
    if (setup.data.blocking_pending > 0) {
      await expect(sentence(await blockingNotice(page, context, 'Todavía no puedes facturar'))).not.toContainText('VeriFactu');
    } else {
      const panel = await openActionCenter(page);
      await expect(panel.locator('[data-testid=action-panel-loading]')).toHaveCount(0);
      await expect(noticeIn(panel, 'Todavía no puedes facturar')).toHaveCount(0);
    }
  } finally {
    await context.close();
  }
});
