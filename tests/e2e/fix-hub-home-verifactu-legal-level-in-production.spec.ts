// flow: «Termina de configurar tu negocio» y la franja bloqueante del Inicio (BASE-F01, BASE-F04) con el paso de VeriFactu (VERIFACTU-F08)
// FIX-HUB-HOME-VERIFACTU-LEGAL-LEVEL-IN-PRODUCTION: a hub in production whose way to the AEAT broke (ERPlora's signed
// authorisation revoked) has every new sale refused, so its Home says so. «Configura VeriFactu» is «Necesario para
// facturar» in «Termina de configurar tu negocio», and the strip «Todavía no puedes facturar» names it over the other
// screens: to the owner with «Configurar», to the employee with «An administrator has to set this up.». In testing the
// same hub stays «Importante» with no strip: it sells without a way (gh:hub#1726).
// Production is the configuration's environment, set in the database for the run: no local server opens real filing
// and nothing is sent (the sale is refused before any record is made). The photo is sent the way the SaaS sends it
// (`PUT /internal/hubs/{id}/state`, signed); what the run changes in VeriFactu's configuration and in `a`'s photo is
// put back after it (or removed, if the run made it).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, horizontalOverflow, login, OWNER, shot, shown, untilStill } from './helpers';
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

const strip = (page: Page): Locator => shown(page).locator('[data-testid="blocking-strip"]');
/** The strip's line of the step (another ⛔, as the business's tax details, may stand beside it). */
const named = (page: Page, title: string): Locator =>
  strip(page).locator('[data-testid="blocking-item"]').filter({ hasText: title });

test.describe.configure({ mode: 'serial' });

for (const size of SIZES) {
  test(`BASE-F01 VERIFACTU-F08 at ${size.label}: in production with the authorisation revoked, «Configura VeriFactu» is «Necesario para facturar» and the strip names it`, async ({ browser }) => {
    await revokedIn('production');
    const { context, page } = await onHome(browser, { width: size.width, height: size.height });
    try {
      // The sale is refused from now on (what the strip warns of), and the Home says it is a wall.
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

      // On «Actividad» the strip stands over the screen: the consequence, the step and its «Configurar».
      await page.goto(`${A}/#actividad`);
      await expect(strip(page)).toBeVisible();
      await expect(strip(page).locator('.blocking-strip-title')).toHaveText('Todavía no puedes facturar');
      await expect(named(page, 'Configura VeriFactu')).toHaveCount(1);
      const configure = named(page, 'Configura VeriFactu').locator(`[data-testid="blocking-configure-${STEP}"]`);
      await expect(configure).toHaveText('Configurar');
      await expect(shown(page).locator('[data-testid="home-activity-loading"]')).toHaveCount(0);
      await untilStill(page);
      const overflow = await horizontalOverflow(page);
      expect(overflow, `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      await configure.click();
      await expect(page).toHaveURL(`${A}/verifactu/config`);
    } finally {
      await context.close();
    }
  });
}

for (const size of SIZES.filter((s) => s.label !== '834')) {
  test(`BASE-F01 VERIFACTU-F08 at ${size.label}: on VeriFactu's Configuration the strip names the step with no «Configurar» to that same screen`, async ({ browser }) => {
    await revokedIn('production');
    const { context, page } = await onHome(browser, { width: size.width, height: size.height });
    try {
      await page.goto(`${A}/verifactu/config`);
      await expect(strip(page).locator('.blocking-strip-title')).toHaveText('Todavía no puedes facturar');
      await expect(named(page, 'Configura VeriFactu')).toHaveCount(1);
      await expect(strip(page).locator(`[data-testid="blocking-configure-${STEP}"]`)).toHaveCount(0);
      await expect(named(page, 'Configura VeriFactu')).not.toContainText('Esto lo tiene que configurar un administrador.');
      await untilStill(page);
      await page.screenshot({ path: shot(`${KEY}-config-${size.label}`) });
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
    await page.goto(`${A}/#actividad`);
    await expect(strip(page).locator('.blocking-strip-title')).toHaveText('You cannot issue invoices yet');
    await expect(named(page, 'Set up VeriFactu')).toHaveCount(1);
    await expect(named(page, 'Set up VeriFactu').locator('.blocking-strip-note')).toHaveText('An administrator has to set this up.');
    await expect(strip(page).locator(`[data-testid="blocking-configure-${STEP}"]`)).toHaveCount(0);
    await expect(shown(page).locator('[data-testid="home-activity-loading"]')).toHaveCount(0);
    await untilStill(page);
    await page.screenshot({ path: shot(`${KEY}-employee-en-1440`) });
  } finally {
    await context.close();
  }
});

test('BASE-F01 gh:hub#1726: in testing the same revoked authorisation stays «Importante», out of the strip', async ({ browser }) => {
  await revokedIn('testing');
  const { context, page } = await onHome(browser, { width: 1440, height: 900 });
  try {
    const config = await api<{ environment: string; issue_blocker: unknown }>(context, A, 'GET', '/verifactu/config');
    expect([config.data.environment, config.data.issue_blocker]).toEqual(['testing', null]);
    await expect(row(page).locator('[data-testid="setup-pill"]')).toHaveText('Importante');
    await page.goto(`${A}/#actividad`);
    await expect(shown(page).locator('[data-testid="home-activity-loading"]')).toHaveCount(0);
    // The business's tax details may be a wall of their own while the hub has no issuer (FIX-INVOICE-SETUP-HOOKS);
    // VeriFactu's step in testing never is: nothing else is in the strip.
    await expect(strip(page).locator('[data-testid="blocking-item"]').filter({ hasNotText: 'Los datos de tu negocio' })).toHaveCount(0);
  } finally {
    await context.close();
  }
});
