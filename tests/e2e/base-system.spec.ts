// System of the Hub (APP-BASE-7; the old hub's SystemPage, docs/reference/old-hub/system-*.png, system-updates-*.png,
// system-events-*.png and system-logs-*.png) in the three viewports, as the owner of hub `a`: its five tabs in the
// address («Usage and plan» by default, also from the old `#resources` and `#plan`; `#backups` lands on Settings › Data),
// «Usage and plan» with what the business uses and whether to upgrade (BASE-F40), once per colour of its line at the top,
// Updates with the version running, Failed events — seen from the bell, resent one
// by one, discarded in the product's dialog with a reason, resent all after a confirmation — and Logs; and the screen's
// own error reported by itself. The employee has three tabs, no Logs, and is told who may see the failed events. Each
// flow leaves its capture `APP-BASE-7-<G key>-<width>` once nothing scrolls sideways.
//
// The failed events (deliveries the relay gave up on) are written as the relay leaves them, tagged in their payload so
// the run removes them after; the relay giving up and its live notice are base/tests/test_services_system.py's. One
// of hub `b` is planted too, in `b`'s own database (S2a): `a` never sees it.
// flow: BASE-F40 BASE-G87 BASE-G88 BASE-G89 BASE-G90 BASE-G91 BASE-G92 BASE-G93 BASE-G94 BASE-G95
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, horizontalOverflow, hostPage, openBell, psql, shot, shown, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** What the run plants carries it in its payload, so it goes after. */
const TAG = 'e2e-base-system';

function cleanUp(): void {
  const events = `select id from live_outboxevent where payload->>'e2e' = '${TAG}'`;
  for (const hub of ['a', 'b']) {
    psql([`delete from base_eventdelivery where event_id in (${events})`, `delete from live_outboxevent where id in (${events})`].join('; '), hub);
  }
}

const YESTERDAY = "(now() at time zone 'utc')::date - 1";
const TODAY = "(now() at time zone 'utc')::date";

/** What the photo and the days of hub `a` say, kept to be put back: a test forces what a real week would take. */
async function withUsage(run: (hubId: string) => Promise<void>): Promise<void> {
  const hubId = psql("select id from base_hub where slug = 'a'");
  const before = psql("select state::text from base_hub where slug = 'a'");
  try {
    await run(hubId);
  } finally {
    psql(`update base_hub set state = '${before.replaceAll("'", "''").replaceAll('"', '\\"')}' where slug = 'a'`);
    psql(`delete from control_hubusagedaily where hub_id = '${hubId}'`);
    psql(`update control_hubactivitydaily set busy_requests = 0 where hub_id = '${hubId}'`);
  }
}

/** The plan of hub `a`, as erplora.com sends it: a Starter by default, with room for the sessions every spec leaves. */
function onPlan(plan: Record<string, number | string>): void {
  const whole = { slug: 'starter', max_users: 100, max_devices: 100, max_db_connections: 3, statement_timeout_seconds: 15, ...plan };
  psql(`update base_hub set state = state || '${JSON.stringify({ plan: whole }).replaceAll('"', '\\"')}' where slug = 'a'`);
}

/** What last night measured of hub `a`: what its files take up. */
function measuredFiles(hubId: string, bytes: number): void {
  psql(`delete from control_hubusagedaily where hub_id = '${hubId}'`);
  psql(
    'insert into control_hubusagedaily (id, hub_id, day, db_bytes, s3_bytes, active_users_1d, active_users_30d, measured_at) ' +
      `values (gen_random_uuid(), '${hubId}', ${YESTERDAY}, ${5 * 1024 * 1024}, ${bytes}, 2, 4, now())`,
  );
}

/** Today's requests of hub `a` that found no room, on top of what its tasks have counted. */
function foundNoRoom(hubId: string, count: number): void {
  psql(
    'insert into control_hubactivitydaily (id, hub_id, day, requests, peak_connections, busy_requests) ' +
      `values (gen_random_uuid(), '${hubId}', ${TODAY}, 0, 0, ${count}) ` +
      `on conflict (hub_id, day) do update set busy_requests = ${count}`,
  );
}

/** A failed event of `hub`, as the relay leaves it after its last attempt: `sale.sale.completed` that Invoicing could
 *  not take, with `error` as its last error. */
function plantFailed(hub: string, error: string): void {
  psql(
    [
      'with e as (insert into live_outboxevent (id, scope_kind, scope_key, name, payload, actor, created_at, delivered_at) ' +
        `values (gen_random_uuid(), 'host', '${hub}', 'sale.sale.completed', '{\\"e2e\\": \\"${TAG}\\"}', 'e2e', now(), now()) returning id)`,
      'insert into base_eventdelivery (id, event_id, app_label, depth, status, attempts, next_attempt_at, last_error, delivered_at) ' +
        `select gen_random_uuid(), e.id, 'invoice', 0, 'dead', 8, now(), '${error}', null from e`,
    ].join(' '),
    hub,
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);
test.describe.configure({ mode: 'serial' });

/** The capture of a flow, once the screen settled. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  // The pointer rests where the last click was: an iOS outline button under it is drawn at 60 % (hover).
  await page.mouse.move(0, 0);
  await expect(shown(page).locator('[data-testid$="-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  const overflow = await horizontalOverflow(page);
  expect(overflow, `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`APP-BASE-7-${key}-${width}`) });
}

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);
const rows = (page: Page) => shown(page).locator('[data-testid="failed-event-row"]');

async function signedIn(browser: Browser, viewport: { width: number; height: number }, next: string, employee = false) {
  return hostPage(browser, A, { viewport, next, credentials: employee ? EMPLOYEE : undefined });
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`BASE-G87 BASE-G88 BASE-G89 BASE-G90 — System and its tabs at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/system');
    try {
      // BASE-G87 — «Usage and plan» first, four tabs, each in the address.
      await expect(testid(page, 'tab-usage')).toHaveClass(/segment-button-checked/);
      await expect(shown(page).locator('ion-segment-button[data-testid^="tab-"]')).toHaveCount(4);

      // BASE-F40 — no night has measured the run's `a`: what comes every night says when, never a zero.
      await expect(testid(page, 'system-usage-info-database')).toContainText('Measured every night');
      for (const gone of ['PostgreSQL', 'Database of its own', 'Cloud resources', 'not measured per business']) {
        await expect(shown(page).getByText(gone)).toHaveCount(0);
      }
      await snap(page, 'BASE-G88', width);

      // The old addresses of the two tabs it took over open it.
      for (const old of ['#resources', '#plan']) {
        await page.goto(`${A}/system${old}`);
        await expect(testid(page, 'tab-usage')).toHaveClass(/segment-button-checked/);
        await expect(testid(page, 'system-usage-info-database')).toBeVisible();
      }

      // BASE-G89 — Updates: the version running and that the hub updates itself.
      await testid(page, 'tab-updates').click();
      await expect(page).toHaveURL(`${A}/system#updates`);
      await expect(testid(page, 'system-release-version')).toContainText('You are on ');
      await expect(testid(page, 'system-updates')).toContainText('This hub updates itself');
      await snap(page, 'BASE-G89', width);

      // BASE-G89 — until the status answers, the tab says it is reading: never an empty tab.
      let release: () => void = () => {};
      const held = new Promise<void>((resolve) => (release = resolve));
      await page.route(/\/api\/live\b/, async (route) => {
        await held;
        await route.continue();
      });
      await expect(page).toHaveURL(`${A}/system#updates`);
      await page.reload();
      await expect(testid(page, 'tab-updates')).toHaveClass(/segment-button-checked/);
      await expect(testid(page, 'system-release-loading')).toHaveText('Reading the version…');
      await expect(testid(page, 'system-release-version')).toHaveCount(0);
      await page.mouse.move(0, 0);
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-7-BASE-G89-loading-${width}`) });
      release();
      // The held streams go on first: unrouting under them would answer them twice.
      await page.unrouteAll({ behavior: 'wait' });
      await expect(testid(page, 'system-release-version')).toContainText('You are on ');
      await expect(testid(page, 'system-release-loading')).toHaveCount(0);

      // BASE-G90 — Logs: the hub's last events between apps, searchable.
      plantFailed('a', 'Conflict: Set up the issuer first.');
      await page.goto(`${A}/system#logs`);
      await expect(testid(page, 'tab-logs')).toHaveClass(/segment-button-checked/);
      // What happened is on the screen at every size, never pushed past its right edge (a phone gets cards).
      await expect(shown(page).getByText('Invoicing could not take it: it is in Failed events.').first()).toBeInViewport();
      await expect(shown(page).locator('[data-testid="system-log-level"]', { hasText: 'Error' }).first()).toBeVisible();
      await snap(page, 'BASE-G90', width);

      // BASE-G87 — the old `#backups` is no tab any more: Settings › Data.
      await page.goto(`${A}/system#backups`);
      await expect(page).toHaveURL(`${A}/settings#data`);
    } finally {
      cleanUp();
      await context.close();
    }
  });

  test(`BASE-F40 — green: the plan is enough, at ${width}`, async ({ browser }) => {
    await withUsage(async (hubId) => {
      onPlan({ max_storage_bytes: 1024 * 1024 });
      measuredFiles(hubId, 512 * 1024);
      const { context, page } = await signedIn(browser, viewport, '/system');
      try {
        // Who opens it knows in one line.
        await expect(shown(page).locator('h2', { hasText: 'Starter plan' })).toBeVisible();
        await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'success');
        await expect(testid(page, 'system-usage-verdict')).toContainText('Your plan is enough');
        await expect(testid(page, 'system-usage-upgrade')).toHaveAttribute('href', /\/store\/plans\?business=/);

        // What the plan includes, with this very screen's real traffic of a hub with its own database.
        await expect(testid(page, 'system-usage-included-heading')).toHaveText('What your plan includes');
        await expect(testid(page, 'system-usage-row-files')).toContainText('512 KB of 1 MB');
        await expect(testid(page, 'system-usage-row-files')).toContainText(/Measured on /);
        await expect(testid(page, 'system-usage-row-files').locator('.usage-meter')).toHaveAttribute('data-tone', 'success');
        await expect(testid(page, 'system-usage-row-capacity')).toContainText('Capacity');
        await expect(testid(page, 'system-usage-row-capacity')).toContainText(/[1-3] of 3 connections/);
        await expect(testid(page, 'system-usage-row-capacity')).not.toContainText('fell short');
        // A bar says nothing of its percentage on this screen: its amount is above it.
        await expect(testid(page, 'system-usage-row-capacity').locator('.usage-meter__percent')).toBeHidden();
        await expect(testid(page, 'system-usage-row-assistant')).toBeVisible();

        // What no plan limits.
        await expect(testid(page, 'system-usage-info-requests')).toContainText(/Requests this month\s*[1-9]/);
        await expect(testid(page, 'system-usage-info-active')).toContainText(/Active now\s*[1-9]/);
        await expect(testid(page, 'system-usage-info-month')).toContainText(/Last 30 days\s*4/);
        await expect(testid(page, 'system-usage-info-database')).toContainText('5 MB');
        await expect(shown(page).getByText(/\bCPU\b|PostgreSQL|Active yesterday/)).toHaveCount(0);
        await snap(page, 'BASE-F40-green', width);

        // Nothing amber or red: no row in the bell.
        await page.goto(`${A}/`);
        await openBell(page);
        await expect(page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: 'Plan limits' })).toHaveCount(0);

        // A plan with no limit on its files: the figure, with no bar or pill.
        onPlan({ max_storage_bytes: 0 });
        await page.goto(`${A}/system`);
        await expect(testid(page, 'system-usage-row-files')).toContainText('512 KB · No limit');
        await expect(testid(page, 'system-usage-row-files').locator('[role="progressbar"]')).toHaveCount(0);
      } finally {
        await context.close();
      }
    });
  });

  test(`BASE-F40 — amber: files from 80 %, at ${width}`, async ({ browser }) => {
    await withUsage(async (hubId) => {
      onPlan({ max_storage_bytes: 1024 * 1024 });
      measuredFiles(hubId, 900 * 1024);
      const { context, page } = await signedIn(browser, viewport, '/system');
      try {
        await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'warning');
        await expect(testid(page, 'system-usage-verdict')).toContainText('You should upgrade: you are almost out of space for files');
        await expect(testid(page, 'system-usage-row-files')).toContainText('Close');
        await expect(testid(page, 'system-usage-row-files').locator('.usage-meter')).toHaveAttribute('data-tone', 'warning');
        await expect(shown(page).locator('[data-testid^="system-usage-row-"]').first()).toHaveAttribute('data-testid', 'system-usage-row-files');
        await snap(page, 'BASE-F40-amber', width);

        // The bell says it too, and its row opens the tab.
        await page.goto(`${A}/`);
        await openBell(page);
        const row = page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: 'Plan limits (1)' });
        await expect(row).toBeVisible();
        await row.click();
        await expect(page).toHaveURL(`${A}/system#usage`);
        await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'warning');
      } finally {
        await context.close();
      }
    });
  });

  test(`BASE-F40 — red: capacity that fell short, and full files, at ${width}`, async ({ browser }) => {
    await withUsage(async (hubId) => {
      onPlan({ max_storage_bytes: 1024 * 1024 });
      measuredFiles(hubId, 512 * 1024);
      foundNoRoom(hubId, 4);
      const { context, page } = await signedIn(browser, viewport, '/system');
      try {
        await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'danger');
        await expect(testid(page, 'system-usage-verdict')).toContainText('You have to upgrade: your business runs out of capacity at its busiest moments');
        await expect(testid(page, 'system-usage-row-capacity')).toContainText(/fell short [4-9] times this week/);
        await expect(testid(page, 'system-usage-row-capacity').locator('.usage-meter')).toHaveAttribute('data-tone', 'danger');
        await expect(shown(page).locator('[data-testid^="system-usage-row-"]').first()).toHaveAttribute('data-testid', 'system-usage-row-capacity');
        await snap(page, 'BASE-F40-red', width);

        // Files full add their own motive to the bell.
        measuredFiles(hubId, 2 * 1024 * 1024);
        await page.goto(`${A}/`);
        await openBell(page);
        await expect(page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: 'Plan limits (2)' })).toBeVisible();
        await page.goto(`${A}/system`);
        await expect(testid(page, 'system-usage-verdict')).toContainText('You have to upgrade: no more files fit');
        await expect(testid(page, 'system-usage-row-files').locator('.usage-meter')).toHaveAttribute('data-tone', 'danger');
        await snap(page, 'BASE-F40-red-files', width);

        // A plan with all the service gives: its capacity never offers to upgrade, and 12 are 6 here.
        measuredFiles(hubId, 512 * 1024);
        onPlan({ slug: 'pro', max_db_connections: 12, max_storage_bytes: 1024 * 1024 });
        await page.goto(`${A}/system`);
        await expect(testid(page, 'system-usage-verdict')).toHaveAttribute('data-tone', 'success');
        await expect(testid(page, 'system-usage-row-capacity')).toContainText(/[1-6] of 6 connections/);
        await expect(testid(page, 'system-usage-row-capacity')).toContainText('You already have the maximum capacity: tell us in «Report a problem».');
        await expect(testid(page, 'system-usage-row-capacity').locator('.usage-meter')).toHaveAttribute('data-tone', 'success');
        await snap(page, 'BASE-F40-top-plan', width);
      } finally {
        await context.close();
      }
    });
  });

  test(`BASE-G91 BASE-G92 BASE-G94 BASE-G93 — Failed events at ${width}`, async ({ browser }) => {
    plantFailed('a', 'E2E one: Set up the issuer first.');
    plantFailed('a', 'E2E two: no such sale.');
    plantFailed('b', 'E2E of b: never seen in a.');
    const { context, page } = await signedIn(browser, viewport, '/');
    try {
      // BASE-G91 — the bell says how many and leads to them (BASE-F10).
      await openBell(page);
      const row = page.locator('ion-popover [data-testid="hub-bell-row"]', { hasText: 'Failed events (2)' });
      await expect(row).toBeVisible();
      await row.click();
      await expect(page).toHaveURL(`${A}/system#events`);
      await expect(rows(page)).toHaveCount(2);
      await expect(shown(page).getByText('E2E of b')).toHaveCount(0);
      await expect(rows(page).first()).toContainText('From Sales & POS to Invoicing');
      await expect(rows(page).first()).toContainText('Attempts: 8');
      await expect(testid(page, 'failed-events-retry-all')).toBeEnabled();
      await snap(page, 'BASE-G91', width);

      // BASE-G92 — resend one: it leaves the list at once, back in the queue.
      await rows(page).filter({ hasText: 'E2E one' }).getByTestId('failed-event-retry').click();
      await expect(rows(page)).toHaveCount(1);
      await expect(rows(page).first()).toContainText('E2E two');
      await snap(page, 'BASE-G92', width);

      // BASE-G94 — discard the other in the product's dialog, with a reason: kept, closed for good.
      await rows(page).first().getByTestId('failed-event-discard').click();
      const dialog = page.locator('[data-testid="failed-event-discard-dialog"]');
      await expect(dialog).toBeVisible();
      await expect(dialog).toContainText('will never reach Invoicing again');
      await dialog.locator('[data-testid="failed-event-discard-reason"] textarea').fill('Invoiced by hand.');
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-7-BASE-G94-${width}`) });
      await page.locator('[data-testid="failed-event-discard-dialog-submit"]').click();
      await expect(testid(page, 'failed-events-empty')).toContainText('All in order');
      expect(
        psql(
          `select d.status || '|' || d.close_reason from base_eventdelivery d join live_outboxevent e on e.id = d.event_id ` +
            `where e.payload->>'e2e' = '${TAG}' and e.scope_key = 'a' order by d.status`,
        ).split('\n'),
      ).toEqual(['discarded|Invoiced by hand.', 'pending|']);

      // BASE-G93 — two more fail; «Resend all» asks, then sends them all back.
      plantFailed('a', 'E2E three: printer off.');
      plantFailed('a', 'E2E four: printer off.');
      await page.reload();
      await expect(rows(page)).toHaveCount(2);
      await testid(page, 'failed-events-retry-all').click();
      const confirm = page.locator('.ep-confirm-dialog').last();
      await expect(confirm).toContainText('Resend every failed event?');
      // In the DOM is not on screen: the capture waits for the dialog presented whole.
      await expect(confirm.getByRole('button', { name: 'Resend all' })).toBeInViewport({ ratio: 1 });
      await untilStill(page);
      await page.screenshot({ path: shot(`APP-BASE-7-BASE-G93-${width}`) });
      await confirm.getByRole('button', { name: 'Resend all' }).click();
      await expect(testid(page, 'failed-events-empty')).toContainText('All in order');
      await snap(page, 'BASE-G91-empty', width);
      // Hub b's is still failed: `a` never touched it.
      expect(
        psql(
          `select d.status from base_eventdelivery d join live_outboxevent e on e.id = d.event_id ` +
            `where e.payload->>'e2e' = '${TAG}' and e.scope_key = 'b'`,
          'b',
        ),
      ).toBe('dead');
    } finally {
      cleanUp();
      await context.close();
    }
  });
}

test('BASE-F40 — what a task counted reaches control within its minute, under Daphne', async ({ browser }) => {
  test.setTimeout(180_000);
  const hubId = psql("select id from base_hub where slug = 'a'");
  const { context, page } = await signedIn(browser, VIEWPORTS[1440], '/system');
  try {
    await expect(testid(page, 'system-usage-row-capacity')).toBeVisible();
    const requests = () => Number(psql(`select coalesce(sum(requests), 0) from control_hubactivitydaily where hub_id = '${hubId}'`));
    const before = requests();
    await page.reload();
    await expect(testid(page, 'system-usage-row-capacity')).toBeVisible();
    await expect.poll(requests, { timeout: 90_000, intervals: [5_000] }).toBeGreaterThan(before);
    await expect
      .poll(() => Number(psql(`select count(*) from control_hubvisit where host = 'a' and last_seen_at > now() - interval '3 minutes'`)), {
        timeout: 90_000,
        intervals: [5_000],
      })
      .toBeGreaterThan(0);
  } finally {
    await context.close();
  }
});

test('BASE-G95 — the screen reports an error nobody caught, by itself', async ({ browser }) => {
  const { context, page } = await signedIn(browser, VIEWPORTS[1440], '/system');
  try {
    await expect(testid(page, 'tab-usage')).toBeVisible();
    const reported = page.waitForResponse((response) => response.url().endsWith('/api/error-report'));
    await page.evaluate(() => {
      window.dispatchEvent(new ErrorEvent('error', { message: 'E2E boom', error: new Error('E2E boom') }));
    });
    expect((await reported).status()).toBe(204);
  } finally {
    await context.close();
  }
});

test('BASE-G87 BASE-G91 — the employee has three tabs, and is told who may see the failed events', async ({ browser }) => {
  const { context, page } = await signedIn(browser, VIEWPORTS[390], '/system', true);
  try {
    await expect(shown(page).locator('ion-segment-button[data-testid^="tab-"]')).toHaveCount(3);
    await expect(testid(page, 'tab-logs')).toHaveCount(0);
    await expect(testid(page, 'system-usage-denied')).toContainText('Only the owner or an administrator');
    await snap(page, 'BASE-G87-employee', 390);
    await page.goto(`${A}/system#events`);
    await expect(testid(page, 'system-events-denied')).toContainText('Only the owner or an administrator can see the failed events.');
    await expect(shown(page).getByText('All in order')).toHaveCount(0);
    await snap(page, 'BASE-G91-employee', 390);
    // Logs in the address opens Resources for them.
    await page.goto(`${A}/system#logs`);
    await expect(testid(page, 'tab-usage')).toHaveClass(/segment-button-checked/);
  } finally {
    await context.close();
  }
});
