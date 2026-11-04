// hub#694: Apps never offers turning on what would always be refused. `a`'s business registered in Poland (`PUT
// /internal/hubs/{id}`, signed the way the SaaS sends it), in the three viewports and in Spanish, as its owner: a
// VeriFactu already on stays as it is and can go off, with what it needs; once off, «Add apps» says «No disponible» with
// the reason and offers no «Activar», and the server refuses it when asked directly, changing nothing. Back in Spain it
// is «Desactivada» with its «Activar» again, it goes on, and from then on Apps says it never goes off (hub#618). In
// English too, at 1440. Captures `FIX-HUB-APPS-REFUSED-OUTSIDE-SPAIN-{pl-on,pl-off,es-off,es-on}-<width>` and
// `…-pl-off-en-1440`. `a`'s rows and its registration are put back after each test.
// flow: VERIFACTU-F01 VERIFACTU-F32 BASE-F25
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, capture, hostPage, horizontalOverflow, login, psql, type Registration, registerBusinessIn, registrationOf, shown } from './helpers';

const KEY = 'FIX-HUB-APPS-REFUSED-OUTSIDE-SPAIN';
const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

const ONLY_IN_SPAIN_ES = 'VeriFactu solo es para negocios de España.';
const ONLY_IN_SPAIN_EN = 'VeriFactu is only for businesses in Spain.';
const NEVER_OFF_ES = 'VeriFactu no se puede desactivar una vez activada: la ley obliga a que tus facturas sigan llegando a la AEAT.';
/** The copy the run keeps of `a`'s rows. */
const ROWS = 'e2e_apps_refused_outside_spain_rows';

let registration: Registration;

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const verifactu = (page: Page) => shown(page).locator('[data-testid="apps-row"][data-id="verifactu"]');
const stateOf = (page: Page) => verifactu(page).locator('[data-testid="apps-state"]');
const reasonOf = (page: Page) => verifactu(page).locator('[data-testid="apps-refusal"]');

/** `a`'s row of VeriFactu as `state:chosen`, or `none`. */
const stored = () =>
  psql("select coalesce((select state || ':' || chosen from base_appactivation where host = 'a' and app = 'verifactu'), 'none')");

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

/** The list searched for VeriFactu: the rows are paged, an app far down the list is not on screen. */
async function findIt(page: Page): Promise<void> {
  await testid(page, 'apps-search').locator('input').fill('VeriFactu');
  await expect(verifactu(page)).toBeVisible();
}

/** The capture once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, name: string): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  expect(await horizontalOverflow(page), `${name}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, name);
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  registration = registrationOf('a');
  expect(stored(), 'VeriFactu on in a (seed_local_hubs: every app on)').toMatch(/^on:/);
  psql(`drop table if exists ${ROWS}; create table ${ROWS} as select * from base_appactivation where host = 'a'`);
});

test.afterEach(async () => {
  await registerBusinessIn(registration, registration.country);
  psql(`delete from base_appactivation where host = 'a'; insert into base_appactivation select * from ${ROWS}`);
});

test.afterAll(() => {
  psql(`drop table if exists ${ROWS}`);
});

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`VERIFACTU-F01 — outside Spain Apps offers no «Activar» for VeriFactu and says why; in Spain it goes on and stays, at ${width}`, async ({ browser }) => {
    await registerBusinessIn(registration, 'PL');
    const { context, page } = await signedInSpanish(browser, viewport, '/apps#all');
    try {
      // On, outside Spain: nothing binds it, so it can go off and nothing is refused.
      await findIt(page);
      await expect(stateOf(page)).toHaveText('Instalada');
      await expect(reasonOf(page)).toHaveCount(0);
      await snap(page, `${KEY}-pl-on-${width}`);

      await testid(page, 'apps-row-verifactu-toggle').click();
      const askOff = page.locator('.ep-confirm-dialog').last();
      await expect(askOff).toContainText('¿Desactivar VeriFactu?');
      await askOff.getByRole('button', { name: 'Desactivar', exact: true }).click();

      // Off, outside Spain: not offered, with the reason.
      await expect(stateOf(page)).toHaveText('No disponible');
      await expect(reasonOf(page)).toHaveText(ONLY_IN_SPAIN_ES);
      await expect(testid(page, 'apps-row-verifactu-toggle')).toHaveCount(0);
      await snap(page, `${KEY}-pl-off-${width}`);

      // The server refuses it all the same when asked directly, and changes nothing.
      const direct = await api<{ error: { code: string; message: string; app: string } }>(context, A, 'POST', '/apps/enable', { app: 'verifactu' });
      expect(direct.status).toBe(409);
      expect(direct.data.error).toMatchObject({ code: 'base.app_vetoed', message: ONLY_IN_SPAIN_ES, app: 'verifactu' });
      expect(stored(), 'nothing written').toBe('off:false');

      // Back in Spain: offered again, and once on it never goes off.
      await registerBusinessIn(registration, 'ES');
      await page.reload();
      await findIt(page);
      await expect(stateOf(page)).toHaveText('Desactivada');
      await expect(reasonOf(page)).toHaveCount(0);
      await snap(page, `${KEY}-es-off-${width}`);

      // «Activar» asks first only when it brings Invoicing back on with it (BASE-F18): decided by what is stored, never
      // by whether the dialog happened to be on screen yet.
      const bringsInvoice = psql("select state from base_appactivation where host = 'a' and app = 'invoice'") !== 'on';
      await testid(page, 'apps-row-verifactu-toggle').click();
      if (bringsInvoice) {
        const askOn = page.locator('.ep-confirm-dialog').last();
        await expect(askOn).toContainText('¿Activar VeriFactu?');
        await askOn.getByRole('button', { name: 'Activar', exact: true }).click();
      }
      await expect(stateOf(page)).toHaveText('Instalada');
      await expect(reasonOf(page)).toHaveText(NEVER_OFF_ES);
      await expect(testid(page, 'apps-row-verifactu-toggle')).toHaveCount(0);
      await snap(page, `${KEY}-es-on-${width}`);
    } finally {
      await context.close();
    }
  });
}

// hub#619: «Mis apps» in Spain, with VeriFactu on: what it needs says why it stays, a long sentence in a table column. It
// wraps and is read whole, never cut at the edge of the column, where the legal reason would be lost.
for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  test(`BASE-F25 — the reason a row gives is read whole, not cut at its column, at ${label}`, async ({ browser }) => {
    await registerBusinessIn(registration, 'ES');
    const { context, page } = await signedInSpanish(browser, viewport, '/apps');
    try {
      const reasons = shown(page).locator('[data-testid="apps-refusal"]');
      await expect(reasons.first()).toBeVisible();
      await expect(reasons.first()).toContainText('la ley obliga');
      const cut = await reasons.evaluateAll((all) =>
        all
          .map((reason) => reason.parentElement as HTMLElement)
          .filter((box) => box.scrollWidth > box.clientWidth)
          .map((box) => `${box.scrollWidth} > ${box.clientWidth}`),
      );
      expect(cut, 'every reason fits the width of its box').toEqual([]);
    } finally {
      await context.close();
    }
  });
}

test('VERIFACTU-F01 — in English, the reason and «Not available», at 1440', async ({ browser }) => {
  await registerBusinessIn(registration, 'PL');
  psql("update base_appactivation set state = 'off', chosen = false where host = 'a' and app = 'verifactu'");
  const { context, page } = await hostPage(browser, A, { viewport: VIEWPORTS[1440], next: '/apps#all' });
  try {
    await findIt(page);
    await expect(stateOf(page)).toHaveText('Not available');
    await expect(reasonOf(page)).toHaveText(ONLY_IN_SPAIN_EN);
    await expect(testid(page, 'apps-row-verifactu-toggle')).toHaveCount(0);
    await snap(page, `${KEY}-pl-off-en-1440`);
  } finally {
    await context.close();
  }
});
