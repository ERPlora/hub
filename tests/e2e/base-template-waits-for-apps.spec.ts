// A template that turns on an app still being set up (hub#609; BASE-F31, BASE-F32, BASE-F33, BASE-F38), in Spanish and in
// the three sizes, as the owner of hub `a`: its data comes in by itself, nothing pressed, on the report (which follows it
// live), on the Home's card and with the person gone from the screen; an app that could not be set up says so on the
// report, with «Retry what is missing», which brings it. `a` has every app's tables (`seed_local_hubs`): control is told it
// lacks Services and the row is held back (`next_attempt_at`), so each state is seen and captured whatever the worker's
// tick; released, the run's worker (`run_worker --databases-only`) goes through the whole path: `ensure_schema` and
// `base.app.activation_settle`, which loads what waited. The DDL and two real databases are pytest's
// (base/tests/test_blueprint_waits_for_apps.py). Captures `BASE-TEMPLATE-WAITS-<step>-<width>`.
// flow: BASE-F31 BASE-F32 BASE-F33 BASE-F38
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  A,
  api,
  APP_SET_UP_MS,
  emptyOfTemplateData,
  horizontalOverflow,
  hostPage,
  psql,
  shot,
  shown,
  signedInSpanish,
  testid,
  untilStill,
} from './helpers';

const VIEWPORTS = {
  375: { width: 375, height: 667 },
  820: { width: 820, height: 1180 },
  1440: { width: 1440, height: 900 },
} as const;

const APP = 'service';
const TEMPLATE = 'hair_salon.es';
/** In the seed. */
const SERVICES = 8;

let hubId = '';
let leaf = '';

/** Control believes `a`'s database lacks Services, and its row is being set up, put off so nothing happens yet. */
function heldBack(): void {
  psql(`update base_hub set schema_apps = schema_apps - '${APP}' where slug = 'a'`);
  psql(
    `update base_appactivation set state = 'creating', chosen = true, attempts = 0, last_error = '', ` +
      `next_attempt_at = now() + interval '10 minutes' where host = 'a' and app = '${APP}'`,
  );
}

/** Its time comes: the row is due and the worker is told, as `base.app.enable` tells it after its COMMIT. */
function released(): void {
  psql(`update base_appactivation set next_attempt_at = null where host = 'a' and app = '${APP}'`);
  psql(
    `insert into control_hubdue (hub_id, due_at, lease_owner) values ('${hubId}', now(), '') ` +
      'on conflict (hub_id) do update set due_at = least(control_hubdue.due_at, excluded.due_at)',
  );
}

/** As a failure leaves the row: its next try far off. */
function failing(): void {
  psql(
    `update base_appactivation set state = 'failed', attempts = 1, last_error = 'schema_failed: e2e', ` +
      `next_attempt_at = now() + interval '1 hour' where host = 'a' and app = '${APP}'`,
  );
}

/** `a` as the run found it: Services on, and control knowing its tables. */
function backToNormal(): void {
  psql(`update base_hub set schema_apps = schema_apps || jsonb_build_object('${APP}', '${leaf}') where slug = 'a'`);
  psql(
    `update base_appactivation set state = 'on', attempts = 0, last_error = '', next_attempt_at = null ` +
      `where host = 'a' and app = '${APP}'`,
  );
}

async function snap(page: Page, key: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`BASE-TEMPLATE-WAITS-${key}-${width}`) });
}

/** Settings › Data › Import, the template chosen and imported as it comes. */
async function loadIt(page: Page): Promise<void> {
  const row = shown(page).locator(`[data-testid="templates-row"][data-id="${TEMPLATE}"]`);
  await row.locator('[data-testid$="-use"]').click();
  await testid(page, 'review-import').click();
}

const appRow = (page: Page) => testid(page, 'report').locator(`[data-testid="report-app"][data-id="${APP}"]`);

async function services(context: BrowserContext): Promise<number> {
  const listed = await api<{ total: number }>(context, A, 'GET', '/service/services?limit=1&offset=0');
  return listed.status === 200 ? listed.data.total : -1;
}

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  leaf = psql(`select schema_apps ->> '${APP}' from base_hub where slug = 'a'`);
  expect(leaf, 'a seeded hub knows the tables of Services').not.toBe('');
});

// Once the tests are over, `a` is emptied again of what the template brought: every later spec uses the same business.
test.afterAll(async ({ browser }) => {
  const { context } = await hostPage(browser, A, { next: '/' });
  try {
    backToNormal();
    await emptyOfTemplateData(context, A);
  } finally {
    await context.close();
  }
});

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F32 — what waited for its app comes in by itself, on the report, at ${width}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await signedInSpanish(browser, viewport, '/settings#data');
    try {
      await emptyOfTemplateData(context, A);
      heldBack();
      await page.reload();
      await loadIt(page);

      await expect(testid(page, 'report-waiting')).toContainText('lo que falta entrará solo');
      await expect(appRow(page).locator('[data-testid="report-app-status"]')).toHaveText('Preparándose');
      await expect(appRow(page).locator('[data-testid="report-app-reason"]')).toContainText('Sus datos se cargarán solos');
      await expect(testid(page, 'report-retry')).toHaveCount(0);
      await snap(page, 'waiting', width);

      released();

      await expect(testid(page, 'report-status')).toHaveText('Todo ha entrado.', { timeout: APP_SET_UP_MS });
      await expect(appRow(page).locator('[data-testid="report-app-status"]')).toHaveText('Aplicado');
      await expect(testid(page, 'report-waiting')).toHaveCount(0);
      expect(await services(context)).toBe(SERVICES);
      await snap(page, 'done', width);
    } finally {
      await context.close();
      backToNormal();
    }
  });

  test(`BASE-F33 — it comes in with nobody on the screen, and the report waits for who comes back, at ${width}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await signedInSpanish(browser, viewport, '/settings#data');
    try {
      await emptyOfTemplateData(context, A);
      heldBack();
      await page.reload();
      await loadIt(page);
      await expect(testid(page, 'report-waiting')).toBeVisible();

      // Coming back while it waits: its report opens first, still saying so, with nothing to press.
      await page.reload();
      await expect(testid(page, 'report-waiting')).toContainText('lo que falta entrará solo');
      await expect(testid(page, 'report-retry')).toHaveCount(0);
      await snap(page, 'back-waiting', width);

      // Gone from the screen, then it comes in; back, the catalogue again: nothing is unfinished.
      await testid(page, 'report-home').click();
      released();
      await expect.poll(() => services(context), { timeout: APP_SET_UP_MS }).toBe(SERVICES);
      await page.goto('/settings#data');
      await expect(shown(page).locator('[data-testid="templates-row"]').first()).toBeVisible();
      await expect(testid(page, 'report')).toHaveCount(0);
    } finally {
      await context.close();
      backToNormal();
    }
  });

  test(`BASE-F32 — an app that could not be set up says so, and the retry brings it, at ${width}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await signedInSpanish(browser, viewport, '/settings#data');
    try {
      await emptyOfTemplateData(context, A);
      heldBack();
      await page.reload();
      await loadIt(page);
      await expect(testid(page, 'report-waiting')).toBeVisible();

      failing();
      await page.reload();

      await expect(appRow(page).locator('[data-testid="report-app-status"]')).toHaveText('No se ha podido preparar');
      await expect(appRow(page).locator('[data-testid="report-app-reason"]')).toContainText('Se sigue intentando sola');
      await expect(testid(page, 'report-waiting')).toHaveCount(0);
      await snap(page, 'failed', width);

      await testid(page, 'report-retry').click();

      await expect(testid(page, 'report-status')).toHaveText('Todo ha entrado.', { timeout: APP_SET_UP_MS });
      await expect(appRow(page).locator('[data-testid="report-app-status"]')).toHaveText('Aplicado');
      expect(await services(context)).toBe(SERVICES);
    } finally {
      await context.close();
      backToNormal();
    }
  });

  test(`BASE-F38 — the Home's card says it comes by itself and turns ready, at ${width}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await signedInSpanish(browser, viewport, '/');
    try {
      await emptyOfTemplateData(context, A);
      heldBack();
      await page.reload();
      await shown(page).locator(`[data-testid="blueprint-card-use-${TEMPLATE}"]`).click();

      await expect(testid(page, 'blueprint-card-pending')).toContainText('Tus apps se están preparando');
      await expect(testid(page, 'blueprint-card-pending')).toContainText('Servicios');
      await expect(testid(page, 'blueprint-card-report')).toBeVisible();
      await snap(page, 'card-waiting', width);

      released();

      await expect(testid(page, 'blueprint-card-outcome')).toContainText('Ya tienes tus apps y tu catálogo', { timeout: APP_SET_UP_MS });
      await expect(testid(page, 'blueprint-card-pending')).toHaveCount(0);
      expect(await services(context)).toBe(SERVICES);
      await snap(page, 'card-ready', width);
    } finally {
      await context.close();
      backToNormal();
    }
  });
}
