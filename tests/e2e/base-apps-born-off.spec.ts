// A business is born with every app off (PLAN-HUB round 2026-10-27) and «Start with a business like yours» on the
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
// flow: BASE-G131 BASE-G67
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, emptyOfTemplateData, hostPage, psql, shot, shown, untilStill } from './helpers';

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
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${step} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APPS-BORN-OFF-${step}-${width}`) });
}

/** Tasks turned `first` and then `then` through Apps (`/api/apps/<enable|disable>`): a change the Hub forgets its
 * cache of the apps off for, at its COMMIT, leaving the rest as it was (Tasks needs only Staff). */
async function bounceTasks(context: BrowserContext, first: 'enable' | 'disable', then: 'enable' | 'disable'): Promise<void> {
  for (const action of [first, then]) {
    const answer = await api(context, A, 'POST', `/apps/${action}`, { app: 'task' });
    expect(answer.status, `Tasks: ${action} ${JSON.stringify(answer.data)}`).toBe(200);
  }
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
