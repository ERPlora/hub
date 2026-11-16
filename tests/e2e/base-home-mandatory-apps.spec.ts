// The Home asks to turn on each app mandatory in the business's country while it is off (hub#997, BASE-F01), in the
// three viewports, as the owner of hub `a` (a business of Spain) with VeriFactu put off:
//   - «Finish setting up your business» has «Turn on VeriFactu», «Important», «It is mandatory for businesses in
//     Spain.», and its «Set up» opens Apps on «Add apps», where VeriFactu is «Off»;
//   - turned on (`base.app.enable`, as Apps does), the step leaves the open Home without a reload and VeriFactu's own
//     step («Set up VeriFactu») comes;
//   - in Spanish, «Activa VeriFactu» with «Es obligatoria para los negocios de España.».
// `a`'s rows of the apps are copied first and put back after each test (every app on, as every other spec finds them),
// and so is its country. Each step leaves its capture `HOME-MANDATORY-<step>-<width>`.
// flow: BASE-F01 VERIFACTU-F01
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { bounceTasks } from './app-rows-helpers';
import {
  A,
  api,
  capture,
  horizontalOverflow,
  hostPage,
  psql,
  registerBusinessIn,
  registrationOf,
  saveSessionForTheSweep,
  shown,
  signedInSpanish,
  type Registration,
} from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The copy the run keeps of `a`'s rows of the apps (every app on), put back after each test. */
const ROWS = 'e2e_base_home_mandatory_rows';
const STEP = 'base.mandatory.verifactu';

interface SetupDocument {
  items: { key: string; state: string; level: string }[];
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const setupRow = (page: Page, key: string) => testid(page, 'setup-card').locator(`[data-testid="setup-row"][data-key="${key}"]`);

/** VeriFactu off in `a`, as a business of Spain that never turned it on (in Spain, once on it never goes off through
 * Apps: VERIFACTU-F32). */
async function verifactuOff(context: BrowserContext): Promise<void> {
  psql("update base_appactivation set state = 'off', chosen = false where host = 'a' and app = 'verifactu'");
  await bounceTasks(context, 'disable', 'enable');
  const apps = await api<{ apps: { id: string; state: string }[] }>(context, A, 'GET', '/apps');
  expect(apps.data.apps.find((app) => app.id === 'verifactu')?.state).toBe('off');
}

/** `a`'s rows of the apps as the run found them. */
async function putTheAppsBack(context: BrowserContext): Promise<void> {
  psql(`delete from base_appactivation where host = 'a'; insert into base_appactivation select * from ${ROWS}`);
  await bounceTasks(context, 'disable', 'enable');
}

async function snap(page: Page, step: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  expect(await horizontalOverflow(page), `${step} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `HOME-MANDATORY-${step}-${width}`);
}

let registration: Registration;

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  const kept = Number(psql("select count(*) from base_appactivation where host = 'a' and app = 'verifactu' and state = 'on'"));
  if (!kept) throw new Error("`a` has VeriFactu off: run `manage.py seed_local_hubs` on this run's database first.");
  psql(`drop table if exists ${ROWS}; create table ${ROWS} as select * from base_appactivation where host = 'a'`);
  registration = registrationOf('a');
  if (registration.country !== 'ES') await registerBusinessIn(registration, 'ES');
});

test.afterAll(async () => {
  psql(`drop table if exists ${ROWS}`);
  if (registration && registration.country !== 'ES') await registerBusinessIn(registration, registration.country);
});

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F01 — a business of Spain with VeriFactu off is asked to turn it on, until it does, at ${width}`, async ({
    browser,
  }) => {
    test.setTimeout(240_000);
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    try {
      await verifactuOff(context);
      await page.goto(`${A}/`);

      const step = setupRow(page, STEP);
      await expect(step).toBeVisible();
      await expect(step).toContainText('Turn on VeriFactu');
      await expect(step).toContainText('It is mandatory for businesses in Spain.');
      await expect(step.locator('[data-testid="setup-pill"]')).toContainText('Important');
      // The icon «My apps» paints VeriFactu with (its first menu entry's), one the shell has: HubIcon draws it.
      await expect(step.locator('ion-icon.setup-row-icon')).toHaveAttribute('name', 'list-outline');
      await step.scrollIntoViewIfNeeded();
      await snap(page, 'step', width);

      await step.locator(`[data-testid="setup-configure-${STEP}"]`).click();
      await expect(page).toHaveURL(/\/apps#all$/);
      await testid(page, 'apps-search').locator('input').fill('VeriFactu');
      const verifactu = shown(page).locator('[data-testid="apps-row"][data-id="verifactu"]');
      await expect(verifactu.locator('[data-testid="apps-state"]')).toContainText('Off');
      await snap(page, 'apps', width);

      await page.goto(`${A}/`);
      await expect(setupRow(page, STEP)).toBeVisible();
      const turnedOn = await api(context, A, 'POST', '/apps/enable', { app: 'verifactu' });
      expect(turnedOn.status, JSON.stringify(turnedOn.data)).toBe(200);
      // The open Home follows it live: no reload.
      await expect(setupRow(page, STEP)).toHaveCount(0, { timeout: 30_000 });
      const after = await api<SetupDocument>(context, A, 'GET', '/home/setup');
      const keys = after.data.items.map((item) => item.key);
      expect(keys).not.toContain(STEP);
      expect(keys).toContain('verifactu.sending_route');
      await testid(page, 'setup-card').scrollIntoViewIfNeeded();
      await snap(page, 'on', width);
    } finally {
      await putTheAppsBack(context);
      await context.close();
    }
  });
}

test('BASE-F01 — in Spanish the step says «Activa VeriFactu» and why, at 1440', async ({ browser }) => {
  test.setTimeout(240_000);
  const { context, page } = await signedInSpanish(browser, VIEWPORTS[1440], '/');
  try {
    await verifactuOff(context);
    await page.reload();
    await saveSessionForTheSweep(context);

    const step = setupRow(page, STEP);
    await expect(step).toBeVisible();
    await expect(step).toContainText('Activa VeriFactu');
    await expect(step).toContainText('Es obligatoria para los negocios de España.');
    await expect(step.locator('[data-testid="setup-pill"]')).toContainText('Importante');
    await step.scrollIntoViewIfNeeded();
    await snap(page, 'step-es', 1440);
  } finally {
    await putTheAppsBack(context);
    await context.close();
  }
});
