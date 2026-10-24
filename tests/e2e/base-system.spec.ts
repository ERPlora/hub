// System of the Hub (APP-BASE-7; the old hub's SystemPage, docs/reference/old-hub/system-*.png, system-updates-*.png,
// system-events-*.png and system-logs-*.png) in the three viewports, as the owner of hub `a`: its five tabs in the
// address (Resources by default; `#backups` lands on Settings › Data), Resources with the database the business is on
// and why there are no usage figures, Updates with the version running, Failed events — seen from the bell, resent one
// by one, discarded in the product's dialog with a reason, resent all after a confirmation — and Logs; and the screen's
// own error reported by itself. The employee has four tabs, no Logs, and is told who may see the failed events. Each
// flow leaves its capture `APP-BASE-7-<G key>-<width>` once nothing scrolls sideways.
//
// The e2e stack runs no worker: the failed events (deliveries the relay gave up on) are written as the relay leaves
// them, tagged in their payload so the run removes them after; the relay giving up and its live notice are
// base/tests/test_services_system.py's. One of hub `b` is planted too: `a` never sees it.
// flow: BASE-G87 BASE-G88 BASE-G89 BASE-G90 BASE-G91 BASE-G92 BASE-G93 BASE-G94 BASE-G95
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, EMPLOYEE, hostPage, psql, shot, shown, untilStill } from './helpers';

const VIEWPORTS = {
  390: { width: 390, height: 844 },
  834: { width: 834, height: 1112 },
  1440: { width: 1440, height: 900 },
} as const;

/** What the run plants carries it in its payload, so it goes after. */
const TAG = 'e2e-base-system';

function cleanUp(): void {
  const events = `select id from live_outboxevent where payload->>'e2e' = '${TAG}'`;
  psql([`delete from base_eventdelivery where event_id in (${events})`, `delete from live_outboxevent where id in (${events})`].join('; '));
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
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
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
      // BASE-G87 — Resources first, five tabs, each in the address.
      await expect(testid(page, 'tab-resources')).toHaveClass(/segment-button-checked/);
      await expect(shown(page).locator('ion-segment-button[data-testid^="tab-"]')).toHaveCount(5);

      // BASE-G88 — the database the business is on, and why there are no usage figures.
      await expect(testid(page, 'system-resources-database')).toContainText('PostgreSQL');
      await expect(testid(page, 'system-resources-database')).toContainText('Shared database');
      await expect(testid(page, 'system-resources-not-measured')).toContainText('not measured per business');
      await snap(page, 'BASE-G88', width);

      // BASE-G89 — Updates: the version running and that the hub updates itself.
      await testid(page, 'tab-updates').click();
      await expect(page).toHaveURL(`${A}/system#updates`);
      await expect(testid(page, 'system-release-version')).toContainText('You are on ');
      await expect(testid(page, 'system-updates')).toContainText('This hub updates itself');
      await snap(page, 'BASE-G89', width);

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

  test(`BASE-G91 BASE-G92 BASE-G94 BASE-G93 — Failed events at ${width}`, async ({ browser }) => {
    plantFailed('a', 'E2E one: Set up the issuer first.');
    plantFailed('a', 'E2E two: no such sale.');
    plantFailed('b', 'E2E of b: never seen in a.');
    const { context, page } = await signedIn(browser, viewport, '/');
    try {
      // BASE-G91 — the bell says how many and leads to them (BASE-F10).
      await testid(page, 'hub-bell').click();
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
        ),
      ).toBe('dead');
    } finally {
      cleanUp();
      await context.close();
    }
  });
}

test('BASE-G95 — the screen reports an error nobody caught, by itself', async ({ browser }) => {
  const { context, page } = await signedIn(browser, VIEWPORTS[1440], '/system');
  try {
    await expect(testid(page, 'tab-resources')).toBeVisible();
    const reported = page.waitForResponse((response) => response.url().endsWith('/api/error-report'));
    await page.evaluate(() => {
      window.dispatchEvent(new ErrorEvent('error', { message: 'E2E boom', error: new Error('E2E boom') }));
    });
    expect((await reported).status()).toBe(204);
  } finally {
    await context.close();
  }
});

test('BASE-G87 BASE-G91 — the employee has four tabs, and is told who may see the failed events', async ({ browser }) => {
  const { context, page } = await signedIn(browser, VIEWPORTS[390], '/system', true);
  try {
    await expect(shown(page).locator('ion-segment-button[data-testid^="tab-"]')).toHaveCount(4);
    await expect(testid(page, 'tab-logs')).toHaveCount(0);
    await expect(testid(page, 'system-resources-denied')).toContainText('Only the owner or an administrator');
    await snap(page, 'BASE-G87-employee', 390);
    await page.goto(`${A}/system#events`);
    await expect(testid(page, 'system-events-denied')).toContainText('Only the owner or an administrator can see the failed events.');
    await expect(shown(page).getByText('All in order')).toHaveCount(0);
    await snap(page, 'BASE-G91-employee', 390);
    // Logs in the address opens Resources for them.
    await page.goto(`${A}/system#logs`);
    await expect(testid(page, 'tab-resources')).toHaveClass(/segment-button-checked/);
  } finally {
    await context.close();
  }
});
