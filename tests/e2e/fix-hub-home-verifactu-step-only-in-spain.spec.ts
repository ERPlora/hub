// flow: BASE-F01 («Termina de configurar tu negocio») with VeriFactu's step (VERIFACTU-F01, VERIFACTU-F08); hub#682
// VeriFactu is Spanish law, so «Configura VeriFactu» is only for a business in Spain. With `a` filing in production and
// ERPlora's authorisation revoked (the step a ⛔ wall: the case that shows most), erplora.com registers `a`'s business
// in Poland: the owner's Home has no «Configura VeriFactu» in «Termina de configurar tu negocio», not even under «Ver
// todo», counts one step fewer, and the action center's «Todavía no puedes facturar» does not name it. Registered in
// Spain, or with no country (a demo, ERPlora's own hub: ERPlora's market, Spain), the step is there with «Necesario
// para facturar» and that notice names it. In 375, 768 and 1440, with the captures `<KEY>-<PL|ES|none>-<width>` of the
// Home.
// The registration and the photo are sent the way the SaaS sends them (`verifactu-helpers.ts`); production is the
// configuration's environment, set in the database for the run (nothing is sent). What the run changes in `a`'s
// registration, its photo and VeriFactu's configuration is put back after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { bellSays, bellTotal, featureNotice, noticeIn, openActionCenter } from './action-center';
import { A, api, capture, horizontalOverflow, saveSessionForTheSweep, signedInSpanish, testid } from './helpers';
import { registerBusinessIn, type Registration, registrationOf } from './business';
import { keepVerifactu, putVerifactuBack, revokedIn } from './verifactu-helpers';

const KEY = 'FIX-HUB-HOME-VERIFACTU-STEP-ONLY-IN-SPAIN';
const STEP = 'verifactu.sending_route';
const TITLE = 'Configura VeriFactu';
const BLOCKING = 'Todavía no puedes facturar';
const SIZES = [
  { label: '375', width: 375, height: 667 },
  { label: '768', width: 768, height: 1024 },
  { label: '1440', width: 1440, height: 900 },
];
/** The countries of the run: Poland, Spain and none (ERPlora's market), each with whether the step is for it. */
const COUNTRIES = [
  { label: 'PL', country: 'PL', told: false },
  { label: 'ES', country: 'ES', told: true },
  { label: 'none', country: '', told: true },
];

/** `a`'s registration as the run found it (put back after). */
let original: Registration;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  original = registrationOf('a');
  keepVerifactu('e2e_fix_vf_spain');
  await revokedIn('production');
});

test.afterAll(async () => {
  if (original) await registerBusinessIn(original, original.country);
  putVerifactuBack();
});

/** «Termina de configurar tu negocio» and VeriFactu's row in it. */
const checklist = (page: Page) => testid(page, 'setup-card');
const step = (page: Page) => checklist(page).locator(`[data-testid="setup-row"][data-key="${STEP}"]`);

/** How many steps the checklist counts («{done} de {total} hechos»). */
async function counted(page: Page): Promise<number> {
  const text = (await checklist(page).locator('[data-testid="setup-progress"]').textContent()) ?? '';
  const total = /de (\d+) hechos/.exec(text);
  expect(total, `the progress says how many steps there are: ${JSON.stringify(text)}`).not.toBeNull();
  return Number(total![1]);
}

/** Every step of the checklist in sight: «Ver todo» pressed when the fold leaves some out. */
async function unfolded(page: Page): Promise<void> {
  const toggle = checklist(page).locator('[data-testid="setup-toggle"]');
  if ((await toggle.count()) && (await toggle.textContent())?.trim() === 'Ver todo') {
    await toggle.click();
    await expect(toggle).toHaveText('Ver menos');
  }
}

/** Whether the action center's «Todavía no puedes facturar» names VeriFactu's wall in its sentence. With no ⛔ pending
 *  the notice is not there at all; another ⛔ (the business's tax details, while the hub has no issuer) keeps it
 *  without the step. */
async function wallNamed(page: Page, context: BrowserContext): Promise<boolean> {
  const setup = await api<{ blocking_pending: number }>(context, A, 'GET', '/home/setup');
  expect(setup.status).toBe(200);
  await bellSays(page, await bellTotal(context));
  if (setup.data.blocking_pending === 0) {
    const panel = await openActionCenter(page);
    await expect(panel.locator('[data-testid=action-panel-loading]')).toHaveCount(0);
    await expect(noticeIn(panel, BLOCKING)).toHaveCount(0);
    return false;
  }
  const featured = await featureNotice(page, BLOCKING);
  return ((await featured.locator('.action-featured__body').textContent()) ?? '').includes(TITLE);
}

for (const size of SIZES) {
  test(`BASE-F01 VERIFACTU-F01 hub#682 at ${size.label}: «Configura VeriFactu» and its wall only for a business in Spain or without a country`, async ({ browser }) => {
    const totals: Record<string, number> = {};
    for (const { label, country, told } of COUNTRIES) {
      await registerBusinessIn(original, country);
      const { context, page } = await signedInSpanish(browser, { width: size.width, height: size.height }, '/');
      try {
        await expect(checklist(page)).toHaveAttribute('aria-busy', 'false');
        await saveSessionForTheSweep(context);
        // Folded, the ⛔ go first: the capture shows the wall where it applies, and its absence in Poland.
        if (told) await expect(step(page).locator('[data-testid="setup-pill"]')).toHaveText('Necesario para facturar');
        await checklist(page).scrollIntoViewIfNeeded();
        expect(await horizontalOverflow(page), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
        await capture(page, `${KEY}-${label}-${size.label}`);

        await unfolded(page);
        totals[label] = await counted(page);
        if (told) {
          await expect(step(page).locator('.setup-row-title')).toHaveText(TITLE);
        } else {
          await expect(checklist(page).locator('[data-testid="setup-row"]').first()).toBeVisible();
          await expect(step(page)).toHaveCount(0);
          await expect(checklist(page).getByText(TITLE)).toHaveCount(0);
        }

        // The action center's «Todavía no puedes facturar» names the wall only where the step is for the business.
        expect(await wallNamed(page, context), `VeriFactu's wall named in the action center, ${label}`).toBe(told);
      } finally {
        await context.close();
      }
    }
    // The same Home, one step fewer for the business in Poland: the step is gone, nothing else.
    expect([totals.PL + 1, totals.none]).toEqual([totals.ES, totals.ES]);
  });
}
