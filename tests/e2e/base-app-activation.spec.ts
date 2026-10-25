// Turning an app on and off, and the plan's limit of apps (PLAN-HUB §9, ronda 2026-10-24b; BASE-F18, F23, F24), in the
// three viewports, as the owner of hub `a`: Apps counts the apps the business chose against the plan's `max_apps`
// (Gratis, 20); «Turn off» Tasks asks with its name and, confirmed, takes it out of «My apps» and of the topbar's «My
// apps» (the menu), and its screens say why they do not open; «Turn on» brings it back. With 20 chosen apps on, the
// 21st is refused with the plan's notice and «Upgrade plan» (erplora.com's plans). Each flow leaves its capture
// `APP-BASE-ACTIVATION-<step>-<width>`. The photo is sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`,
// signed); `a`'s photo is put back after the run and its rows of `base_appactivation` are cleared before and after
// each test (a business without rows has every app on: the baseline).
// flow: BASE-F18 BASE-F23 BASE-F24 BASE-F26
import { createHmac } from 'node:crypto';

import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, hostPage, psql, shot, shown, untilStill } from './helpers';
import { STACK } from './stack';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The copy the run keeps of `a`'s photo. */
const BACKUP = 'e2e_base_app_activation_photo_before';
/** Gratis (PLAN §32): 20 apps the business chooses. */
const GRATIS = { slug: 'free', max_users: 0, max_devices: 0, max_apps: 20 };

let hubId = '';
let version = Math.floor(Date.now() / 1000);

async function pushPhoto(plan: Record<string, unknown>): Promise<void> {
  version += 1;
  const body = JSON.stringify({ hub_id: hubId, slug: 'a', version, plan });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const signature = createHmac('sha256', SECRET).update(`${timestamp}.${body}`).digest('hex');
  const response = await fetch(`http://127.0.0.1:${STACK.hubPort}/internal/hubs/${hubId}/state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-Erplora-Timestamp': timestamp, 'X-Erplora-Signature': signature },
    body,
  });
  const answer = await response.text();
  expect(response.status, answer).toBe(200);
  expect(JSON.parse(answer)).toMatchObject({ applied: true, version });
}

/** `a` back on its baseline: no rows, every app on. */
const baseline = () => psql("delete from base_appactivation where host = 'a'");

test.beforeAll(() => {
  hubId = psql("select id from base_hub where slug = 'a'");
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(hubId)) {
    throw new Error(`The registry of DB_NAME=${STACK.database} has no hub a (got ${JSON.stringify(hubId)}): run node tests/e2e/database.ts.`);
  }
  version = Math.max(version, Number(psql(`select state_version from base_hub where id = '${hubId}'`)));
  psql(
    [
      `drop table if exists ${BACKUP}`,
      `create table ${BACKUP} as select id, state, state_version from base_hub where id = '${hubId}'`,
    ].join('; '),
  );
});

test.afterAll(() => {
  baseline();
  psql(
    [
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP} b where b.id = h.id`,
      `drop table ${BACKUP}`,
    ].join('; '),
  );
});

test.beforeEach(baseline);
test.afterEach(baseline);

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const appRow = (page: Page, id: string) => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** The list searched for `name`: the rows are paged, an app far down the list is not on screen. */
async function search(page: Page, name: string): Promise<void> {
  await testid(page, 'apps-search').locator('input').fill(name);
}

/** The capture of a step, once the screen settled and nothing scrolls sideways. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-ACTIVATION-${key}-${width}`) });
}

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

async function signedIn(browser: Browser, viewport: { width: number; height: number }, next: string) {
  return hostPage(browser, A, { viewport, next });
}

test.describe.configure({ mode: 'serial' });

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-F23 BASE-F24 — turn Tasks off and on again at ${width}`, async ({ browser }) => {
    await pushPhoto(GRATIS);
    const { context, page } = await signedIn(browser, viewport, '/apps');
    try {
      const listed = await api<{ apps: { id: string; path: string | null }[] }>(context, A, 'GET', '/apps');
      const tasksScreen = listed.data.apps.find((app) => app.id === 'task')?.path;
      expect(tasksScreen, 'Tasks has a screen for the owner').toBeTruthy();

      // The baseline: every app on, the roots chosen (17 with the reference app of development) of Gratis's 20.
      await expect(testid(page, 'apps-counter')).toHaveText('17 of 20 apps turned on');
      await search(page, 'Tasks');
      await expect(appRow(page, 'task')).toBeVisible();
      expect(await menuApps(page)).toContain('Tasks');
      await snap(page, 'counter', width);

      // BASE-F23 — «Turn off» asks with its name; confirmed, Tasks leaves «My apps» and the menu.
      await testid(page, 'apps-row-task-toggle').click();
      const confirm = page.locator('.ep-confirm-dialog').last();
      await expect(confirm).toContainText('Turn off Tasks?');
      await expect(confirm).toContainText('Nothing is deleted');
      await expect(confirm.getByRole('button', { name: 'Turn off' })).toBeInViewport({ ratio: 1 });
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-ACTIVATION-confirm-off-${width}`) });
      await confirm.getByRole('button', { name: 'Turn off' }).click();
      await expect(appRow(page, 'task')).toHaveCount(0);
      await expect(testid(page, 'apps-counter')).toHaveText('16 of 20 apps turned on');
      await expect.poll(() => menuApps(page), { message: 'the menu follows without a reload' }).not.toContain('Tasks');
      await snap(page, 'off', width);

      // Its screen says why it does not open, and its data is not touched (BASE-F26).
      await page.goto(`${A}${tasksScreen}`);
      await expect(testid(page, 'app-blocked-missing')).toBeVisible();
      await snap(page, 'blocked-screen', width);

      // BASE-F24 — «Add apps»: Tasks is there, «Off», with its name; «Turn on» brings it back to the menu.
      await page.goto(`${A}/apps#all`);
      await search(page, 'Tasks');
      await expect(appRow(page, 'task').locator('[data-testid="apps-state"]')).toHaveText('Off');
      await testid(page, 'apps-row-task-toggle').click();
      await expect(appRow(page, 'task').locator('[data-testid="apps-state"]')).toHaveText('Installed');
      await expect(testid(page, 'apps-counter')).toHaveText('17 of 20 apps turned on');
      await expect.poll(() => menuApps(page), { message: 'the menu follows without a reload' }).toContain('Tasks');
      await snap(page, 'on-again', width);
      expect(psql("select state || ':' || chosen from base_appactivation where host = 'a' and app = 'task'")).toBe('on:true');
    } finally {
      await context.close();
    }
  });

  test(`PLAN-HUB §9 — a Gratis business with 20 apps chosen cannot turn on the 21st at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/apps#all');
    try {
      // 20 apps chosen and on, Website off: what an existing business of Gratis may have, at its limit.
      const listed = await api<{ apps: { id: string }[] }>(context, A, 'GET', '/apps');
      const ids = listed.data.apps.map((app) => app.id).filter((id) => id !== 'website');
      expect(ids.length, 'the deployment has more than 20 apps besides Website').toBeGreaterThan(20);
      const values = [
        ...ids.map((id, index) => `('a', '${id}', 'on', ${index < 20 ? 'true' : 'false'})`),
        "('a', 'website', 'off', false)",
      ];
      psql(
        'insert into base_appactivation (id, host, app, state, chosen, changed_at) ' +
          `select gen_random_uuid(), v.host, v.app, v.state, v.chosen, now() from (values ${values.join(', ')}) as v(host, app, state, chosen)`,
      );
      await pushPhoto(GRATIS);
      await page.reload();

      await expect(testid(page, 'apps-counter')).toHaveText('20 of 20 apps turned on');
      await search(page, 'Website');
      await expect(appRow(page, 'website').locator('[data-testid="apps-state"]')).toHaveText('Off');
      await testid(page, 'apps-row-website-toggle').click();

      const notice = testid(page, 'apps-limit');
      await expect(notice).toContainText('You have reached the 20-app limit of your plan. Upgrade your plan or turn one off.');
      const upgrade = notice.locator('[data-testid="apps-limit-upgrade"]');
      await expect(upgrade).toHaveText('Upgrade plan');
      await expect(upgrade).toHaveAttribute('href', new RegExp(`/store/plans\\?business=${hubId}$`));
      await expect(appRow(page, 'website').locator('[data-testid="apps-state"]')).toHaveText('Off');
      expect(psql("select state from base_appactivation where host = 'a' and app = 'website'")).toBe('off');
      await snap(page, 'limit', width);
    } finally {
      await context.close();
    }
  });
}
