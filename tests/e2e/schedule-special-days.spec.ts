// Schedules → Special days in Chrome (SCHEDULE-F04, F05, F06, F13; apps/schedule/WORKBOOK.md). The owner of
// hub `a` adds a closed special day, sees the same date refused (409 under the form), corrects it into an
// open day with hours, and deletes it after confirming; then adds an override, sees a second one over the
// same dates refused, and deletes it. «is it open?» answers from what the screen saved. Screenshots in the
// three viewports. Each list filters behind its own funnel, named after the list, with its count. Everything it creates is named «E2E …» on dates of 2099 and removed after the file.
import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const TAG = 'E2E';

function cleanup(): void {
  psql(
    [
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like '${TAG}%')`,
      `delete from schedule_override where reason like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanup);
test.afterAll(cleanup);

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

/** The widths of the filter panel's screenshots: a phone (the panel is a sheet), a tablet and a desk
 *  (two columns), as the SaaS panel's `VIEWPORTS`. */
const FILTER_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

async function listsReady(page: Page): Promise<void> {
  const view = shown(page);
  await view.locator('[data-testid=schedule-special-days-row], [data-testid=schedule-special-days-empty]').first().waitFor({ state: 'visible' });
  await view.locator('[data-testid=schedule-overrides-row], [data-testid=schedule-overrides-empty]').first().waitFor({ state: 'visible' });
}

/** A row action: its button, or the «⋮» menu when the row folded its actions (waits for either). */
async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  const menu = shown(page).locator(`[data-testid=${table}-row-${id}-menu]`);
  await expect(button.or(menu).first()).toBeVisible();
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await menu.click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

test('SCHEDULE-F04, F13, F06: a special day added, a taken date refused, corrected with hours, deleted', async ({ page, context }) => {
  const name = `${TAG} Christmas ${Date.now().toString(36)}`;
  await login(page, A, '/schedule/special-days');
  await listsReady(page);
  const view = shown(page);
  await expect(view.locator('[data-testid=schedule-special-days-heading]')).toHaveText('Special days');
  await expect(view.locator('[data-testid=schedule-overrides-heading]')).toHaveText('Overrides');

  // «+»: Date, Name; closed by default.
  await view.locator('[data-testid=schedule-special-days-add]').click();
  await page.locator('[data-testid=schedule-special-day-form-date] input').fill('2099-12-25');
  await page.locator('[data-testid=schedule-special-day-form-name] input').fill(name);
  await page.screenshot({ path: shot('schedule-special-day-new-1280') });
  await page.locator('[data-testid=schedule-special-day-form-submit]').click();
  const row = view.locator('[data-testid=schedule-special-days-row]', { hasText: name });
  await expect(row).toContainText('12/25/2099');
  await expect(row).toContainText('Closed');

  // The same date again: refused in the form (409 schedule.special_day_exists).
  await view.locator('[data-testid=schedule-special-days-add]').click();
  await page.locator('[data-testid=schedule-special-day-form-date] input').fill('2099-12-25');
  await page.locator('[data-testid=schedule-special-day-form-name] input').fill(`${TAG} Again`);
  await page.locator('[data-testid=schedule-special-day-form-submit]').click();
  await expect(page.locator('[data-testid=schedule-special-day-form-error]')).toContainText('There is already a special day on that date.');
  await page.screenshot({ path: shot('schedule-special-day-409-1280') });
  await page.locator('[data-testid=schedule-special-day-form-cancel]').click();

  // Correct it: open 10:00–14:00 (SCHEDULE-F13).
  await row.getByText(name).click();
  await expect(page.locator('ion-modal[data-testid=schedule-special-day-form] ion-title')).toHaveText(`Edit · ${name}`);
  await page.locator('[data-testid=schedule-special-day-form-status]').click();
  await page.locator('ion-popover ion-radio', { hasText: 'Open (with hours)' }).click();
  await page.locator('[data-testid=schedule-special-day-form-intervals-open-0] input').fill('10:00');
  await page.locator('[data-testid=schedule-special-day-form-intervals-close-0] input').fill('14:00');
  await page.locator('[data-testid=schedule-special-day-form-submit]').click();
  await expect(row).toContainText('10:00 AM–02:00 PM');

  // «Is it open?» answers from what the screen saved (SCHEDULE-F10).
  const open = await api<{ is_open: boolean; source: string; reason: string }>(context, A, 'GET', '/schedule/is_open?when=2099-12-25T11:00');
  expect([open.data.is_open, open.data.source, open.data.reason]).toEqual([true, 'special_day', name]);

  // Delete asks first.
  const id = psql(`select id from schedule_specialday where name = '${name}'`);
  await rowAction(page, 'schedule-special-days', id, 'delete');
  await expect(page.locator('ion-modal[data-testid=schedule-special-day-delete]')).toContainText(`«${name}» will be deleted. This cannot be undone.`);
  await page.locator('[data-testid=schedule-special-day-delete-submit]').click();
  await expect(row).toHaveCount(0);
});

test('SCHEDULE-F05, F06: an override added, another over the same dates refused, deleted', async ({ page }) => {
  const reason = `${TAG} Summer ${Date.now().toString(36)}`;
  await login(page, A, '/schedule/special-days');
  await listsReady(page);
  const view = shown(page);

  await view.locator('[data-testid=schedule-overrides-add]').click();
  await page.locator('[data-testid=schedule-override-form-start_date] input').fill('2099-07-01');
  await page.locator('[data-testid=schedule-override-form-end_date] input').fill('2099-08-31');
  await page.locator('[data-testid=schedule-override-form-reason] input').fill(reason);
  await page.locator('[data-testid=schedule-override-form-submit]').click();
  const row = view.locator('[data-testid=schedule-overrides-row]', { hasText: reason });
  await expect(row).toContainText('07/01/2099');
  await expect(row).toContainText('08/31/2099');

  // Another one over those dates: refused (409 schedule.override_overlaps).
  await view.locator('[data-testid=schedule-overrides-add]').click();
  await page.locator('[data-testid=schedule-override-form-start_date] input').fill('2099-08-15');
  await page.locator('[data-testid=schedule-override-form-end_date] input').fill('2099-09-15');
  await page.locator('[data-testid=schedule-override-form-reason] input').fill(`${TAG} More`);
  await page.locator('[data-testid=schedule-override-form-submit]').click();
  await expect(page.locator('[data-testid=schedule-override-form-error]')).toContainText(`Those dates overlap the temporary change “${reason}”`);
  await page.screenshot({ path: shot('schedule-override-409-1280') });
  await page.locator('[data-testid=schedule-override-form-cancel]').click();

  const id = psql(`select id from schedule_override where reason = '${reason}'`);
  await rowAction(page, 'schedule-overrides', id, 'delete');
  await page.locator('[data-testid=schedule-override-delete-submit]').click();
  await expect(row).toHaveCount(0);
});

test('Special days in the three viewports: no horizontal scroll; cards on a phone', async ({ page }) => {
  await login(page, A, '/schedule/special-days');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/schedule/special-days`);
    await listsReady(page);
    await noHorizontalScroll(page, vp.label);
    await page.screenshot({ path: shot(`schedule-special-days-${vp.label}`), fullPage: true });
  }
});

// flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
test('FIX-DATATABLE-HUB-FILTERS-1: Special days filter by Name behind their own funnel, with its count, the panel open at every width', async ({ page, context }) => {
  const stamp = Date.now().toString(36);
  const kept = `${TAG} Fil${stamp} One`;
  const other = `${TAG} Fil${stamp} Two`;
  await login(page, A, '/schedule/special-days');
  for (const [date, name] of [['2099-11-02', kept], ['2099-11-03', other]]) {
    const res = await api(context, A, 'POST', '/schedule/special_days', { date, name });
    expect(res.status, JSON.stringify(res.data)).toBe(201);
  }
  const days = (name: string) => shown(page).locator('[data-testid=schedule-special-days-row]', { hasText: name });
  for (const vp of FILTER_VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/schedule/special-days`);
    await listsReady(page);
    await expect(days(other)).toBeVisible();
    // Two lists, two funnels: each is named after its own list (schedules#58).
    await expect(shown(page).getByRole('button', { name: /^(Special day filters|Filtros de días especiales)$/ })).toHaveCount(1);
    await expect(shown(page).getByRole('button', { name: /^(Override filters|Filtros de cambios temporales)$/ })).toHaveCount(1);
    const panel = shown(page).locator('[data-testid=schedule-special-days-filters-panel]');
    const toggle = shown(page).locator('[data-testid=schedule-special-days-filters-toggle]');
    await toggle.click();
    await expect(panel).toBeVisible();
    await panel.locator('[data-testid=schedule-special-days-filter-name] input').fill(kept);
    await panel.locator('[data-testid=schedule-special-days-filters-apply]').click();
    await expect(panel).toBeHidden();
    await expect(shown(page).locator('[data-testid=schedule-special-days-filters-count]')).toHaveText('1');
    await expect(shown(page).getByRole('button', { name: /^(Special day filters|Filtros de días especiales) \(1 (active|activo)\)$/ })).toHaveCount(1);
    await expect(days(kept)).toBeVisible();
    await expect(days(other)).toHaveCount(0);
    await toggle.click();
    await expect(panel).toBeVisible();
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot(`FIX-DATATABLE-HUB-FILTERS-1-schedule-${vp.label}`) });
    await panel.locator('[data-testid=schedule-special-days-filters-clear]').click();
    await expect(shown(page).locator('[data-testid=schedule-special-days-filters-count]')).toHaveCount(0);
    await panel.locator('[data-testid=schedule-special-days-filters-close]').click();
    await expect(panel).toBeHidden();
  }
});
