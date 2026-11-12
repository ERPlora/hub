// A hub without rows of its apps has every app off (PLAN-HUB round 2026-10-27; a business signs up with Taxes on since
// hub#997: base-sign-up-taxes-on.spec.ts) and «Start with a business like yours» on the
// Home turns on the apps of the template it uses, then loads its catalogue (BASE-G131; `base.blueprint.import`), in the
// three viewports, as the owner of hub `a` put back to how a business is born:
//   - Apps says nothing is on: «My apps» is empty with its notice, and an app of the catalogue is «Off» in «Add apps»;
//   - the Home offers the card; «Use this one» on the restaurant ends in «Your apps and your catalogue are ready», and
//     the Home's «My apps» has the apps it turned on without a reload;
//   - the template's apps are on (its roots chosen, what they need along), «Active» in «My apps», and its products
//     and tables are in, through the apps' own lists.
// `a` is emptied of what a template brings first (phase 1: `a` and `b` share those rows), and after each test the load
// is undone and `a` gets back its rows with every app on (the ones `seed_local_hubs` wrote, as every other spec finds
// it). Each step leaves its capture `APPS-BORN-OFF-<step>-<width>`.
// And in a business of Spain (hub#998, PLAN-HUB round 2026-11-07), at 375, 768 and 1440: Settings › Data › «Use
// template» reviews the restaurant's without VeriFactu (Invoicing and Kitchen «turn on»), the load goes in whole and
// VeriFactu stays «Off» in Apps with nothing refusing it, for its owner to turn on (captures `APPS-BORN-OFF-spain-…`).
// flow: BASE-G131 BASE-G67 BASE-F31 VERIFACTU-F01
import { expect, type Page, test } from '@playwright/test';

import { bounceTasks } from './app-rows-helpers';
import {
  A,
  api,
  emptyOfTemplateData,
  horizontalOverflow,
  hostPage,
  psql,
  registerBusinessIn,
  registrationOf,
  shot,
  shown,
  untilStill,
} from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The copy the run keeps of `a`'s rows (every app on), put back after each test. */
const ROWS = 'e2e_base_apps_born_off_rows';
const TEMPLATE = 'restaurant.en';

interface App {
  id: string;
  state: string;
  chosen: boolean;
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const appRow = (page: Page, id: string) => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** The capture of a step, once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, step: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${step} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APPS-BORN-OFF-${step}-${width}`) });
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  const kept = Number(psql("select count(*) from base_appactivation where host = 'a' and state = 'on'"));
  if (!kept) throw new Error("`a` has no app on: run `manage.py seed_local_hubs` on this run's database first.");
  psql(`drop table if exists ${ROWS}; create table ${ROWS} as select * from base_appactivation where host = 'a'`);
});

test.afterAll(() => {
  psql(`drop table if exists ${ROWS}`);
});

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-G131 — a business born with every app off starts from a template at ${width}`, async ({ browser }) => {
    test.setTimeout(240_000);
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    let loadId = '';
    try {
      await emptyOfTemplateData(context, A);
      // `a` as a business is born: every app off. Its rows go, and Tasks on and off again through Apps makes the Hub
      // forget what it keeps of the apps off for a minute (its first change writes every app down, off).
      psql("delete from base_appactivation where host = 'a'");
      await bounceTasks(context, 'enable', 'disable');
      const born = await api<{ apps: App[] }>(context, A, 'GET', '/apps');
      expect(born.status).toBe(200);
      expect(born.data.apps.filter((app) => app.state !== 'off')).toEqual([]);

      // BASE-G67 — Apps: nothing in «My apps»; in «Add apps», an app of the catalogue is «Off».
      await page.goto(`${A}/apps`);
      await expect(testid(page, 'tab-mine')).toHaveClass(/segment-button-checked/);
      await expect(testid(page, 'apps-empty')).toContainText('You have no apps yet.');
      await snap(page, 'mine-empty', width);
      // The Home says the same: no app in «My apps».
      await page.goto(`${A}/`);
      await expect(testid(page, 'home-my-apps-empty')).toBeVisible();
      await expect(testid(page, 'home-my-app')).toHaveCount(0);
      await page.goto(`${A}/apps#all`);
      await testid(page, 'apps-search').locator('input').fill('Inventory');
      await expect(appRow(page, 'inventory').locator('[data-testid="apps-state"]')).toContainText('Off');
      await snap(page, 'all-off', width);

      // BASE-G131 — the Home offers the card; «Use this one» turns on the template's apps, then loads it.
      await page.goto(`${A}/`);
      const card = testid(page, 'blueprint-card');
      await expect(card).toBeVisible();
      const use = card.locator(`[data-testid="blueprint-card-use-${TEMPLATE}"]`);
      await expect(use).toBeVisible();
      await expect(card).toContainText('we turn on its apps and load its catalogue in one go');
      await snap(page, 'card', width);
      const imported = page.waitForResponse(
        (response) => response.url().endsWith('/api/settings/data/blueprints/import') && response.request().method() === 'POST',
      );
      await use.click();
      const answer = await imported;
      const load = (await answer.json()) as { id: string; status: string; report: { apps: { id: string; reason?: string }[] } };
      loadId = load.id;
      expect([answer.status(), load.status], JSON.stringify(load.report)).toEqual([200, 'complete']);
      await expect(card.locator('[data-testid="blueprint-card-outcome"]')).toContainText('Your apps and your catalogue are ready');
      // Without a reload, «My apps» on the Home has the apps it turned on (the session is read again); a phone shows
      // the first four and «View all apps».
      await expect(testid(page, 'home-my-apps-empty')).toHaveCount(0);
      await expect(testid(page, 'home-my-app').first()).toBeVisible();
      await snap(page, 'card-ready', width);

      // The template's apps are on, and nothing else; its products and tables are in.
      const catalogue = await api<{ templates: { key: string; apps: { id: string }[] }[] }>(
        context,
        A,
        'GET',
        '/settings/data/blueprints',
      );
      const wanted = catalogue.data.templates.find((template) => template.key === TEMPLATE)?.apps.map((app) => app.id) ?? [];
      expect(wanted.length, `${TEMPLATE} lists its apps`).toBeGreaterThan(0);
      const after = await api<{ apps: App[] }>(context, A, 'GET', '/apps');
      const on = after.data.apps.filter((app) => app.state === 'on').map((app) => app.id);
      expect(on.sort()).toEqual([...wanted].sort());
      expect(after.data.apps.filter((app) => app.chosen).length).toBeLessThan(wanted.length); // what came along is not chosen
      for (const list of ['/inventory/products', '/table/tables']) {
        const rows = await api<{ rows: unknown[] }>(context, A, 'GET', `${list}?limit=100&offset=0`);
        expect(rows.status, list).toBe(200);
        expect(rows.data.rows.length, `${list} after the template`).toBeGreaterThan(0);
      }

      // «My apps» has them, «Active».
      await page.goto(`${A}/apps`);
      await testid(page, 'apps-search').locator('input').fill('Inventory');
      await expect(appRow(page, 'inventory').locator('[data-testid="apps-state"]')).toContainText('Active');
      await snap(page, 'mine-after', width);
    } finally {
      if (loadId) {
        const undone = await api(context, A, 'POST', '/settings/data/imports/undo', { id: loadId });
        expect(undone.status, 'the load is undone').toBe(200);
      }
      // `a` back to every app on; a change through Apps forgets what the Hub keeps of its apps off for a minute.
      psql(`delete from base_appactivation where host = 'a'; insert into base_appactivation select * from ${ROWS}`);
      await bounceTasks(context, 'disable', 'enable');
      await context.close();
    }
  });
}

/** The sizes of hub#998's check: a phone, a tablet upright and a desktop. */
const SPAIN_VIEWPORTS = {
  375: { width: 375, height: 667 },
  768: { width: 768, height: 1024 },
  1440: { width: 1440, height: 900 },
} as const;
/** The review's note on an app of the template that is off (`base.data.review.appTurnsOn`). */
const TURNS_ON = 'It is off in your business: loading it turns it on.';

for (const [label, viewport] of Object.entries(SPAIN_VIEWPORTS)) {
  const width = Number(label);

  test(`VERIFACTU-F01 BASE-F31 — a template reviewed and loaded in a business of Spain leaves VeriFactu off at ${width}`, async ({
    browser,
  }) => {
    test.setTimeout(240_000);
    const registration = registrationOf('a');
    const { context, page } = await hostPage(browser, A, { viewport, next: '/' });
    let loadId = '';
    try {
      await registerBusinessIn(registration, 'ES');
      await emptyOfTemplateData(context, A);
      psql("delete from base_appactivation where host = 'a'");
      await bounceTasks(context, 'enable', 'disable');

      // Settings › Data › «Use template»: the review names what the load turns on, and VeriFactu is not in it.
      await page.goto(`${A}/settings#data`);
      await shown(page).locator(`[data-testid="templates-row-${TEMPLATE}-use"]`).click();
      const review = testid(page, 'review');
      await expect(review).toBeVisible();
      const reviewed = (id: string) => review.locator(`[data-testid="review-app"][data-id="${id}"]`);
      await expect(reviewed('invoice')).toContainText(TURNS_ON);
      await expect(reviewed('kitchen')).toContainText(TURNS_ON);
      await expect(reviewed('verifactu')).toHaveCount(0);
      await snap(page, 'spain-review', width);

      const imported = page.waitForResponse(
        (response) => response.url().endsWith('/api/settings/data/blueprints/import') && response.request().method() === 'POST',
      );
      await review.locator('[data-testid="review-import"]').click();
      const answer = await imported;
      const load = (await answer.json()) as { id: string; status: string; report: { apps: { id: string }[] } };
      loadId = load.id;
      expect([answer.status(), load.status], JSON.stringify(load.report)).toEqual([200, 'complete']);
      expect(load.report.apps.map((app) => app.id)).not.toContain('verifactu');
      await expect(testid(page, 'report-status')).toContainText('Everything went in.');
      await snap(page, 'spain-report', width);

      // VeriFactu stays off, with nothing refusing it: its owner turns it on. What the sector needs came on.
      const after = await api<{ apps: App[] }>(context, A, 'GET', '/apps');
      const state = Object.fromEntries(after.data.apps.map((app) => [app.id, app.state]));
      expect([state.verifactu, state.invoice, state.kitchen]).toEqual(['off', 'on', 'on']);
      await page.goto(`${A}/apps#all`);
      await testid(page, 'apps-search').locator('input').fill('VeriFactu');
      const verifactu = appRow(page, 'verifactu');
      await expect(verifactu.locator('[data-testid="apps-state"]')).toContainText('Off');
      await expect(verifactu.locator('[data-testid="apps-refusal"]')).toHaveCount(0);
      await expect(verifactu).toContainText('Turn on');
      await snap(page, 'spain-apps', width);
    } finally {
      if (loadId) {
        const undone = await api(context, A, 'POST', '/settings/data/imports/undo', { id: loadId });
        expect(undone.status, 'the load is undone').toBe(200);
      }
      psql(`delete from base_appactivation where host = 'a'; insert into base_appactivation select * from ${ROWS}`);
      await bounceTasks(context, 'disable', 'enable');
      await registerBusinessIn(registration, registration.country);
      await context.close();
    }
  });
}
