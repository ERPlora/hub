// flow: KITCHEN-F25, KITCHEN-F26 — Kitchen → History and Kitchen → Settings in Chrome, with the real Kitchen app: a
// ticket made by hand and cancelled with a reason shows in the History, found by part of its number and by the
// «Cancelled» filter, with its reason and who did it (F25); in Settings, the amber minutes and the default type are
// changed, «Save» says «Settings saved.» and the server keeps them, the type chosen by its words (F26). Each screen in
// 390×844, 834×1112 and 1440×900 (`APP-KITCHEN-<flow>-<size>`). What a run creates — the ticket «e2e khs <run>» — is
// deleted after it, and the settings go back to what they were.
import { type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, psql, shot, shown } from './helpers';
import { stamp } from './sale-helpers';
import { ownerPage, settled } from './service-helpers';

const RUN = stamp();
const LABEL = `e2e khs ${RUN}`;
const SIZES = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

interface Settings {
  warning_minutes: number;
  critical_minutes: number;
  default_order_type: string;
}

function cleanUp(): void {
  const tickets = "select id from kitchen_ticket where label like 'e2e khs %'";
  psql(
    [
      `delete from printing_printjob where source_app = 'kitchen' and reference in (select number from kitchen_ticket where id in (${tickets}))`,
      `delete from kitchen_logentry where ticket_id in (${tickets})`,
      `delete from kitchen_ticketitem where ticket_id in (${tickets})`,
      `delete from kitchen_ticket where id in (${tickets})`,
    ].join('; '),
  );
}

async function post<T>(context: BrowserContext, path: string, body: unknown, status = 200): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(status);
  return res.data;
}

async function capture(page: Page, flow: string, ready: () => Promise<void>): Promise<void> {
  for (const size of SIZES) {
    await page.setViewportSize({ width: size.width, height: size.height });
    await ready();
    await settled(page);
    await page.screenshot({ path: shot(`APP-KITCHEN-${flow}-${size.label}`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
}

/** Picks `text` in an `ion-select` (popover interface). */
async function choose(page: Page, select: Locator, text: string): Promise<void> {
  await select.click();
  await page.locator('ion-popover.select-popover ion-radio').filter({ hasText: new RegExp(`^\\s*${text}\\s*$`) }).click();
  await page.locator('ion-popover.select-popover').waitFor({ state: 'detached' });
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('KITCHEN-F25: the History finds a cancelled ticket by part of its number and by «Cancelled», with its reason', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/history', { width: 1440, height: 900 });
  try {
    const ticket = await post<{ id: string; number: string; short_number: string }>(context, '/kitchen/tickets', { label: LABEL, items: [{ name: 'Salmon' }] }, 201);
    await post(context, '/kitchen/tickets/cancel', { ticket_id: ticket.id, reason: 'Out of salmon' });
    await page.reload();
    const view = shown(page);
    await expect(view.locator('[data-testid=kitchen-history-title]')).toHaveText('Kitchen history');

    // Part of its number finds both entries, newest first.
    await view.locator('[data-testid=kitchen-history-search] input').fill(ticket.number);
    const rows = view.locator('[data-testid=kitchen-history-row]').filter({ hasText: ticket.number });
    await expect(rows).toHaveCount(2);
    await expect(rows.first()).toContainText('Cancelled');
    await expect(rows.first()).toContainText('Out of salmon');
    await expect(rows.last()).toContainText('Created');
    // «Who» is the person as they read themselves, never the id of their session («saas:…»).
    await expect(rows.first()).toContainText('owner@example.com');
    await expect(rows.first()).not.toContainText('saas:');

    // «Cancelled» leaves only the cancel.
    await choose(page, view.locator('[data-testid=kitchen-history-filter-action]'), 'Cancelled');
    await expect(rows).toHaveCount(1);
    await expect(rows.first()).toContainText('Out of salmon');
    await capture(page, 'KITCHEN-F25', async () => {
      await expect(rows.first()).toBeVisible();
    });
  } finally {
    await context.close();
  }
});

test('KITCHEN-F26: Settings saves the amber minutes and the default type, and says so', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/kitchen/settings', { width: 1440, height: 900 });
  const read = await api<Settings>(context, A, 'GET', '/kitchen/settings');
  expect(read.status, JSON.stringify(read.data)).toBe(200);
  const before = read.data;
  try {
    const amber = before.warning_minutes > 1 ? before.warning_minutes - 1 : before.warning_minutes + 1;
    const view = shown(page);
    const save = view.locator('[data-testid=kitchen-settings-save]');
    await expect(view.locator('[data-testid=kitchen-settings-warning_minutes]')).toBeVisible();
    // Nothing touched, nothing to save (`ion-button` says it with aria-disabled).
    await expect(save).toHaveAttribute('aria-disabled', 'true');

    await view.locator('[data-testid=kitchen-settings-warning_minutes] input').fill(String(amber));
    const type = view.locator('[data-testid=kitchen-settings-default_order_type]');
    const other = before.default_order_type === 'takeaway' ? 'Dine in' : 'Takeaway';
    await choose(page, type, other);
    await expect(save).not.toHaveAttribute('aria-disabled', 'true');
    await capture(page, 'KITCHEN-F26', async () => {
      await save.scrollIntoViewIfNeeded();
      await expect(save).toBeInViewport();
    });
    await save.click();
    await expect(view.locator('[data-testid=kitchen-settings-saved]')).toHaveText('Settings saved.');

    const after = (await api<Settings>(context, A, 'GET', '/kitchen/settings')).data;
    expect([after.warning_minutes, after.default_order_type]).toEqual([amber, other === 'Takeaway' ? 'takeaway' : 'dine_in']);
  } finally {
    await post(context, '/kitchen/settings', { warning_minutes: before.warning_minutes, default_order_type: before.default_order_type });
    await context.close();
  }
});
