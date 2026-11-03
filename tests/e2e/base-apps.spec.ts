// Apps and System › «Usage and plan» of the Hub (APP-BASE-4; the old hub's AppsPage and SystemPage,
// docs/reference/old-hub/apps-*.png, apps-all-*.png, apps-paid-*.png and system-plan-*.png) in the three viewports,
// as the owner of hub `a`: «My apps» with each app's state and «Open», «Add apps» (`#all`) with its search and
// neither «Paid» nor «Price» (every app in every plan, PLAN §32: no app of this deployment is sold apart, so an old
// link to `#paid` opens «Add apps»), and the plan's limits against
// the people of the business — followed live: the SaaS's photo with a plan moves the screen without a reload. The
// employee reads the apps too (no notice cuts the list on a phone: gh:hub#2570) and is told that «Usage and plan»
// is for whoever runs the business. Each flow leaves its capture `APP-BASE-4-<G key>-<width>` once nothing scrolls
// sideways. A paid app without its right (BASE-G74, BASE-G132, BASE-G134) cannot be reached here: no module of the
// deployment is premium; the Vitest of AppsPage and AppBlockedPage and base/tests/test_entitlement.py cover it.
// The photo is sent the way the SaaS sends it (`PUT /internal/hubs/{id}/state`, signed) and `a`'s photo is put
// back after the run.
// flow: BASE-G67 BASE-G68 BASE-G69 BASE-G70 BASE-G81
import { createHmac } from 'node:crypto';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, horizontalOverflow, hostPage, psql, shot, shown, turnOn, untilStill } from './helpers';
import { STACK } from './stack';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** The secret `/internal` is signed with; the local default of both projects. */
const SECRET = process.env.INTERNAL_SHARED_SECRET || 'local-internal-shared-secret';
/** The copy the run keeps of `a`'s photo. */
const BACKUP = 'e2e_base_apps_photo_before';

let hubId = '';
/** Monotonic photo versions: an older one changes nothing. */
let version = Math.floor(Date.now() / 1000);

/** The SaaS's photo of hub `a`, with `plan` (its limits; 0 = none) or without one. */
async function pushPhoto(plan?: { slug: string; max_users: number; max_devices: number }): Promise<void> {
  version += 1;
  const body = JSON.stringify({ hub_id: hubId, slug: 'a', version, ...(plan ? { plan } : {}) });
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
  psql(
    [
      `update base_hub h set state = b.state, state_version = b.state_version from ${BACKUP} b where b.id = h.id`,
      `drop table ${BACKUP}`,
    ].join('; '),
  );
});

/** The capture of a flow, once the screen settled and nothing of it is still loading. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await expect(shown(page).locator('ion-skeleton-text:visible, [data-testid="apps-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-4-${key}-${width}`) });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const appRow = (page: Page, id: string) => shown(page).locator(`[data-testid="apps-row"][data-id="${id}"]`);

/** The active members of `a`, the people the plan's limit counts. */
const people = (): number => Number(psql("select count(*) from base_membership m join auth_user u on u.id = m.user_id where m.host = 'a' and u.is_active"));

async function signedIn(browser: Browser, viewport: { width: number; height: number }, next: string, employee = false) {
  return hostPage(browser, A, { viewport, next, credentials: employee ? EMPLOYEE : undefined });
}

test.describe.configure({ mode: 'serial' });

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-G67 BASE-G68 BASE-G69 BASE-G70 — Apps at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/apps');
    // The owner's session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`), when asked.
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    // A business is born with every app off (PLAN-HUB round 2026-10-27): the demo is turned on first, so «My apps»
    // has it whatever this run's `a` was left with (`seed_local_hubs` leaves every app on; then this changes nothing).
    await turnOn(context, A, 'demo');
    await page.reload();

    // BASE-G67 — «My apps»: the apps on, the demo among them, each with its state.
    await expect(page).toHaveURL(`${A}/apps`);
    await expect(testid(page, 'tab-mine')).toHaveClass(/segment-button-checked/);
    const demo = appRow(page, 'demo');
    await expect(demo).toBeVisible();
    await expect(demo.locator('[data-testid="apps-state"]')).toContainText('Active');
    await snap(page, 'BASE-G67', width);

    // BASE-G68 — «Open» leads to the app's first screen.
    await testid(page, 'apps-row-demo-open').click();
    await expect(page).toHaveURL(`${A}/demo/items`);
    await snap(page, 'BASE-G68', width);

    // BASE-G69 — «Add apps» (`#all`): the whole catalogue and its search; a search with no match says so.
    await page.goto(`${A}/apps#all`);
    await expect(testid(page, 'tab-all')).toHaveClass(/segment-button-checked/);
    const search = testid(page, 'apps-search').locator('input');
    await search.fill('Demo');
    await expect(shown(page).locator('[data-testid="apps-row"]')).toHaveCount(1);
    await expect(appRow(page, 'demo')).toBeVisible();
    await snap(page, 'BASE-G69', width);
    await search.fill('zz-no-such-app-zz');
    await expect(testid(page, 'apps-empty')).toContainText('No apps match your search.');
    await search.fill('');
    await expect(appRow(page, 'demo')).toBeVisible();

    // BASE-G70 — every app in every plan (PLAN §32): nothing is sold apart, so there is no «Paid» tab and «Add apps»
    // has no «Price» (it would say «Free» on every row), neither in the table nor in the phone's cards; «Comes with»
    // still names what an app brings (BASE-F19). The demo is «Installed» in the catalogue.
    const labels = shown(page).locator('[role="columnheader"], .data-table__field-label');
    await expect(labels.filter({ hasText: /^Category$/ }).first()).toBeVisible();
    await expect(labels.filter({ hasText: /^Price$/ })).toHaveCount(0);
    await expect(shown(page).locator('[data-testid="apps-price"]')).toHaveCount(0);
    await expect(testid(page, 'tab-all')).toBeVisible();
    await expect(testid(page, 'tab-paid')).toHaveCount(0);
    await expect(appRow(page, 'demo').locator('[data-testid="apps-state"]')).toContainText('Installed');
    await snap(page, 'BASE-G70', width);
    // An old link to «Paid» (`#paid`) opens «Add apps», where whatever was sold apart would be.
    await page.goto(`${A}/apps#paid`);
    await expect(testid(page, 'tab-all')).toHaveClass(/segment-button-checked/);
    await expect(appRow(page, 'demo')).toBeVisible();
    await expect(testid(page, 'tab-paid')).toHaveCount(0);
    await snap(page, 'BASE-G70-paid', width);
    // «My apps» takes the hash away again.
    await testid(page, 'tab-mine').click();
    await expect(page).toHaveURL(`${A}/apps`);
    await expect(appRow(page, 'demo')).toBeVisible();

    await context.close();
  });

  test(`BASE-F40 BASE-G81 — what the plan includes at ${width}, followed live`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/system#usage');
    // A photo without a plan: the limits are not known yet, never a made-up figure.
    await pushPhoto();
    await page.reload();
    await expect(testid(page, 'system-usage-unknown')).toBeVisible();
    await expect(testid(page, 'system-usage-verdict')).toHaveCount(0);
    const used = people();
    expect(used, 'the owner is a member of a').toBeGreaterThan(0);
    const peopleRow = testid(page, 'system-usage-row-people');
    await expect(peopleRow).toContainText(String(used));
    await snap(page, 'BASE-G81-unknown', width);

    // A plan with no limit (0), without a reload: the people of the business and «No limit».
    await pushPhoto({ slug: 'standard', max_users: 0, max_devices: 0 });
    await expect(testid(page, 'system-usage-unknown')).toHaveCount(0);
    await expect(peopleRow).toContainText(`${used} · No limit`);
    await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'success');

    // The SaaS's photo with every place taken moves the screen without a reload: the bar and «Full», and the line stays
    // green, because a business with all its people in is fine.
    await pushPhoto({ slug: 'starter', max_users: used, max_devices: 999 });
    await expect(peopleRow).toContainText(`${used} of ${used}`);
    await expect(peopleRow).toContainText('Full');
    await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'success');
    await expect(testid(page, 'system-usage-verdict')).toContainText('People at the limit: to add more, upgrade the plan.');
    await snap(page, 'BASE-G81', width);

    // Room again: within the plan.
    await pushPhoto({ slug: 'standard', max_users: used + 5, max_devices: 999 });
    await expect(peopleRow).toContainText(`${used} of ${used + 5}`);
    await expect(testid(page, 'system-usage-verdict')).not.toContainText('at the limit');
    await snap(page, 'BASE-G81-room', width);

    await context.close();
  });
}

test('BASE-G67 BASE-G81 — the employee reads the apps on a phone, and «Usage and plan» is for whoever runs the business', async ({ browser }) => {
  const viewport = VIEWPORTS[390];
  const { context, page } = await signedIn(browser, viewport, '/apps', true);
  try {
    // gh:hub#2570 — nothing above the list cuts it on a phone: the demo's row and «Open» are in view.
    const demo = appRow(page, 'demo');
    await expect(demo).toBeVisible();
    await expect(testid(page, 'apps-row-demo-open')).toBeInViewport();
    await snap(page, 'BASE-G67-employee', 390);

    await page.goto(`${A}/system#usage`);
    await expect(testid(page, 'system-usage-denied')).toBeVisible();
    await expect(testid(page, 'system-usage-retry')).toHaveCount(0);
    await snap(page, 'BASE-G81-employee', 390);
  } finally {
    await (context as BrowserContext).close();
  }
});
