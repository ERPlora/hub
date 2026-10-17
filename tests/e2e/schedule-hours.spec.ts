// Schedules → Hours and Settings in Chrome (SCHEDULE-F01, F02, F03, F08, F09; apps/schedule/WORKBOOK.md).
// The owner of hub `a` finds the default week (Monday to Friday 09:00–18:00, weekend closed) with the
// yellow notice, edits Monday into a split shift, sees two overlapping intervals refused under the
// intervals (422), confirms the week (the notice goes), makes the week start on Sunday in Settings and
// finds the table opening on Sunday. An employee reads the week without editing. Screenshots in the three
// viewports. The week and the settings the hub had before the file are put back after it (`afterAll`).
import { expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shot, shown } from './helpers';

/** The default week of migration 0002, unconfirmed, as the database's own hand (hub `a`'s, shared with `b`). */
const DEFAULT_WEEK = [
  'delete from schedule_weekdayinterval',
  'delete from schedule_weekday',
  'delete from schedule_schedulesettings',
  'insert into schedule_weekday (id, weekday, is_closed, updated_at) select gen_random_uuid(), d, d >= 5, now() from generate_series(0, 6) d',
  "insert into schedule_weekdayinterval (id, position, open_time, close_time, day_id) select gen_random_uuid(), 0, '09:00', '18:00', id from schedule_weekday where weekday < 5",
].join('; ');

/** The SQL that writes back the week and the settings as they are now (rows, ids and dates included). */
const SNAPSHOT = [
  "select format('insert into schedule_weekday (id, weekday, is_closed, updated_at) values (%L, %s, %L, %L)', id, weekday, is_closed, updated_at) from schedule_weekday",
  "select format('insert into schedule_weekdayinterval (id, position, open_time, close_time, day_id) values (%L, %s, %L, %L, %L)', id, position, open_time, close_time, day_id) from schedule_weekdayinterval",
  "select format('insert into schedule_schedulesettings (id, slot, week_starts_on, hours_confirmed, updated_at) values (%L, %s, %s, %L, %L)', id, slot, week_starts_on, hours_confirmed, updated_at) from schedule_schedulesettings",
];
const CLEAR = ['delete from schedule_weekdayinterval', 'delete from schedule_weekday', 'delete from schedule_schedulesettings'];

/** What the hub had before this file: its rows as INSERT statements, read in `beforeAll`. */
let before: string[] = [];

test.beforeAll(() => {
  before = SNAPSHOT.flatMap((query) => psql(query).split('\n')).filter(Boolean);
  psql(DEFAULT_WEEK);
});
test.afterAll(() => {
  psql([...CLEAR, ...before].join('; '));
});

const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1194 },
  { label: '1440', width: 1440, height: 900 },
];

async function weekReady(page: Page): Promise<void> {
  await expect(shown(page).locator('[data-testid=schedule-hours-row]')).toHaveCount(7);
}

const rowTexts = (page: Page) => shown(page).locator('[data-testid=schedule-hours-row]').allInnerTexts();

async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

test('SCHEDULE-F01–F03: the default week, a split Monday, an overlap refused, the week confirmed', async ({ page, context }) => {
  await login(page, A, '/schedule/hours');
  await weekReady(page);
  const view = shown(page);
  const rows = await rowTexts(page);
  expect(rows[0]).toContain('Monday');
  expect(rows[0]).toContain('09:00 AM–06:00 PM');
  expect(rows[5]).toContain('Closed');
  await expect(view.locator('[data-testid=schedule-hours-default-week]')).toContainText('These are default opening hours we set up for you.');
  await page.screenshot({ path: shot('schedule-hours-default-1280') });

  // Monday: a split shift, 10:00–14:00 and 17:00–20:00.
  await view.locator('[data-testid=schedule-hours-row-0-edit]').click();
  const dialog = page.locator('ion-modal[data-testid=schedule-day-form]');
  await expect(dialog.locator('ion-title')).toHaveText('Edit hours — Monday');
  await page.locator('[data-testid=schedule-day-form-intervals-open-0] input').fill('10:00');
  await page.locator('[data-testid=schedule-day-form-intervals-close-0] input').fill('14:00');
  await page.locator('[data-testid=schedule-day-form-intervals-add]').click();
  await page.locator('[data-testid=schedule-day-form-intervals-open-1] input').fill('13:00');
  await page.locator('[data-testid=schedule-day-form-intervals-close-1] input').fill('20:00');
  await page.locator('[data-testid=schedule-day-form-submit]').click();
  // Overlapping: refused under the intervals (422), the dialog stays with what was typed.
  await expect(page.locator('[data-testid=schedule-day-form-intervals-error]')).toContainText('Two intervals overlap');
  await page.screenshot({ path: shot('schedule-hours-422-1280') });
  await page.locator('[data-testid=schedule-day-form-intervals-open-1] input').fill('17:00');
  await page.locator('[data-testid=schedule-day-form-submit]').click();
  await expect(dialog).toBeHidden();
  await expect(view.locator('[data-testid=schedule-hours-row]').first()).toContainText('10:00 AM–02:00 PM · 05:00 PM–08:00 PM');
  // Saving a day confirms the week: the notice goes.
  await expect(view.locator('[data-testid=schedule-hours-default-week]')).toHaveCount(0);

  // Server-side evidence: Monday holds both intervals.
  const week = await api<{ confirmed: boolean; days: { weekday: number; intervals: { open_time: string }[] }[] }>(context, A, 'GET', '/schedule/week');
  expect(week.data.confirmed).toBe(true);
  expect(week.data.days[0].intervals.map((i) => i.open_time)).toEqual(['10:00:00', '17:00:00']);
});

test('SCHEDULE-F03: «Yes, these are my hours» confirms the default week without moving an hour', async ({ page, context }) => {
  psql(DEFAULT_WEEK);
  await login(page, A, '/schedule/hours');
  await weekReady(page);
  const before = await rowTexts(page);
  const notice = shown(page).locator('[data-testid=schedule-hours-default-week]');
  await expect(notice).toBeVisible();
  await notice.locator('[data-testid=schedule-hours-confirm-week]').click();
  await expect(notice).toHaveCount(0);
  expect(await rowTexts(page)).toEqual(before);
  const week = await api<{ confirmed: boolean }>(context, A, 'GET', '/schedule/week');
  expect(week.data.confirmed).toBe(true);
});

test('SCHEDULE-F08, F09: the business zone, and a week that starts on Sunday', async ({ page }) => {
  await login(page, A, '/schedule/settings');
  const view = shown(page);
  await expect(view.locator('[data-testid=schedule-settings-timezone]')).toContainText('Europe/Madrid');
  await view.locator('[data-testid=schedule-settings-week-start]').click();
  await page.locator('ion-popover ion-radio', { hasText: 'Sunday' }).click();
  await view.locator('[data-testid=schedule-settings-submit]').click();
  await expect(view.locator('[data-testid=schedule-settings-saved]')).toHaveText('Saved');
  await page.screenshot({ path: shot('schedule-settings-1280') });
  await page.goto(`${A}/schedule/hours`);
  await weekReady(page);
  expect((await rowTexts(page))[0]).toContain('Sunday');
});

test('An employee reads the week: no edit, no confirmation', async ({ page }) => {
  psql(DEFAULT_WEEK);
  await login(page, A, '/schedule/hours', EMPLOYEE);
  await weekReady(page);
  const view = shown(page);
  await expect(view.locator('[data-testid=schedule-hours-default-week]')).toBeVisible();
  await expect(view.locator('[data-testid=schedule-hours-confirm-week]')).toHaveCount(0);
  await expect(view.locator('[data-testid=schedule-hours-row-0-edit]')).toHaveCount(0);
});

test('Hours and Settings in the three viewports: no horizontal scroll; cards on a phone', async ({ page }) => {
  await login(page, A, '/schedule/hours');
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(`${A}/schedule/hours`);
    await weekReady(page);
    await noHorizontalScroll(page, `hours ${vp.label}`);
    if (vp.width === 390) await expect(shown(page).locator('.data-table__cards')).toBeVisible();
    await page.screenshot({ path: shot(`schedule-hours-${vp.label}`) });
    await page.goto(`${A}/schedule/settings`);
    await expect(shown(page).locator('[data-testid=schedule-settings-timezone]')).toBeVisible();
    await noHorizontalScroll(page, `settings ${vp.label}`);
    await page.screenshot({ path: shot(`schedule-settings-${vp.label}`) });
  }
});
