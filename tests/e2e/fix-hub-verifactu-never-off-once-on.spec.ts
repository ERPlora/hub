// VeriFactu never goes off once on, in Spain (FIX-HUB-VERIFACTU-NEVER-OFF-ONCE-ON), in the three viewports, as the
// owner of hub `a`: with VeriFactu on and no record left to send to the AEAT, «Desactivar» in Apps is still refused
// with the legal reason — in Spanish, and in English for a Hub in English — and VeriFactu stays «Activa», with its row
// and Invoicing's untouched and both still in the topbar's «My apps». Each viewport leaves its capture
// `FIX-HUB-VERIFACTU-NEVER-OFF-ONCE-ON-<width>` (the Spanish refusal) and `…-en-<width>`. Nothing is written: a
// refusal changes no row, so there is nothing to put back.
// flow: VERIFACTU-F32
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, capture, horizontalOverflow, hostPage, login, psql, shown } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

const NEVER_OFF_ES =
  'VeriFactu no se puede desactivar una vez activada: la ley obliga a que tus facturas sigan llegando a la AEAT.';
const NEVER_OFF_EN = "VeriFactu can't be turned off once it's on: the law requires your invoices to keep reaching the AEAT.";

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const appRow = (page: Page, id: string) => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** `a`'s row of `app` as `state:chosen`, or `none`. */
const stored = (app: string) =>
  psql(`select coalesce((select state || ':' || chosen from base_appactivation where host = 'a' and app = '${app}'), 'none')`);

/** How many of `a`'s VeriFactu records are not in the AEAT yet (pending, or sent without an answer). */
const stillToSend = () => Number(psql("select count(*) from verifactu_record where status in ('pending', 'sent')"));

/** The names the topbar's «My apps» (the menu of the apps, from the session) lists now. */
async function menuApps(page: Page): Promise<string[]> {
  await testid(page, 'topbar-apps').click();
  const sheet = page.locator('[data-testid="apps-launcher"]').last();
  const tiles = sheet.locator('[data-testid="apps-launcher-app"]');
  await expect(tiles.first()).toBeVisible();
  const names = (await tiles.allInnerTexts()).map((name) => name.trim());
  await sheet.locator('[data-testid="apps-launcher-close"]').click();
  await expect(sheet).toBeHidden();
  return names;
}

/** The owner of `a` on `next`, with the Hub in Spanish (its language cookie, as the language picker leaves it). */
async function signedInSpanish(browser: Browser, viewport: { width: number; height: number }, next: string) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const page = await context.newPage();
  await login(page, A, next);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  // A reload, not a goto: the login already left the page on `next`.
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  return { context, page };
}

/** «Turn off» VeriFactu in Apps, confirmed in the dialog that asks: `title` and `confirm` in the page's language. */
async function turnOffVerifactu(page: Page, labels: { search: string; title: string; confirm: string }): Promise<void> {
  await testid(page, 'apps-search').locator('input').fill(labels.search);
  await testid(page, 'apps-row-verifactu-toggle').click();
  const askOff = page.locator('.ep-confirm-dialog').last();
  await expect(askOff).toContainText(labels.title);
  await askOff.getByRole('button', { name: labels.confirm, exact: true }).click();
}

/** The capture once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

test.describe.configure({ mode: 'serial' });

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`VERIFACTU-F32 — «Desactivar» VeriFactu with nothing left to send is refused with the legal reason and it stays on, at ${width}`, async ({ browser }) => {
    expect(stored('verifactu'), 'VeriFactu on in a (seed_local_hubs: every app on)').toMatch(/^on:/);
    expect(stillToSend(), 'no record of a is still to send to the AEAT').toBe(0);
    const before = [stored('verifactu'), stored('invoice')];

    const spanish = await signedInSpanish(browser, viewport, '/apps');
    try {
      const { page } = spanish;
      await turnOffVerifactu(page, { search: 'VeriFactu', title: '¿Desactivar VeriFactu?', confirm: 'Desactivar' });

      const refused = testid(page, 'apps-refused');
      await expect(refused).toContainText('No se ha cambiado nada');
      await expect(refused).toContainText(NEVER_OFF_ES);
      await expect(appRow(page, 'verifactu').locator('[data-testid="apps-state"]')).toHaveText('Activa');
      expect([stored('verifactu'), stored('invoice')], 'nothing written').toEqual(before);
      await snap(page, `FIX-HUB-VERIFACTU-NEVER-OFF-ONCE-ON-${width}`);
      expect(await menuApps(page)).toEqual(expect.arrayContaining(['VeriFactu', 'Facturación']));
    } finally {
      await spanish.context.close();
    }

    const { context, page } = await hostPage(browser, A, { viewport, next: '/apps' });
    try {
      await turnOffVerifactu(page, { search: 'VeriFactu', title: 'Turn off VeriFactu?', confirm: 'Turn off' });

      const refused = testid(page, 'apps-refused');
      await expect(refused).toContainText('Nothing was changed');
      await expect(refused).toContainText(NEVER_OFF_EN);
      await expect(appRow(page, 'verifactu').locator('[data-testid="apps-state"]')).toHaveText('Active');
      expect([stored('verifactu'), stored('invoice')], 'nothing written').toEqual(before);
      await snap(page, `FIX-HUB-VERIFACTU-NEVER-OFF-ONCE-ON-en-${width}`);
    } finally {
      await context.close();
    }
  });
}
