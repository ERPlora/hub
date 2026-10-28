// Shared by the schedule specs (apps/schedule/WORKBOOK.md): the default week of migration 0002 as the
// database's own hand, the SQL that saves and puts back what hub `a` had, the cleanup of what a spec
// creates (named «E2E …»), and the waits and row actions of the two screens.
import { expect, type Page } from '@playwright/test';

import { psql, shown } from './helpers';

/** The three sizes of a flow's screenshots: a phone, a tablet and a desk. */
export const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
];

/** The default week of migration 0002, unconfirmed (hub `a`'s, shared with `b` in phase 1). */
export const DEFAULT_WEEK = [
  'delete from schedule_weekdayinterval',
  'delete from schedule_weekday',
  'delete from schedule_schedulesettings',
  'insert into schedule_weekday (id, weekday, is_closed, updated_at) select gen_random_uuid(), d, d >= 5, now() from generate_series(0, 6) d',
  "insert into schedule_weekdayinterval (id, position, open_time, close_time, day_id) select gen_random_uuid(), 0, '09:00', '18:00', id from schedule_weekday where weekday < 5",
].join('; ');

const SNAPSHOT = [
  "select format('insert into schedule_weekday (id, weekday, is_closed, updated_at) values (%L, %s, %L, %L)', id, weekday, is_closed, updated_at) from schedule_weekday",
  "select format('insert into schedule_weekdayinterval (id, position, open_time, close_time, day_id) values (%L, %s, %L, %L, %L)', id, position, open_time, close_time, day_id) from schedule_weekdayinterval",
  "select format('insert into schedule_schedulesettings (id, slot, week_starts_on, hours_confirmed, updated_at) values (%L, %s, %s, %L, %L)', id, slot, week_starts_on, hours_confirmed, updated_at) from schedule_schedulesettings",
];
const CLEAR = ['delete from schedule_weekdayinterval', 'delete from schedule_weekday', 'delete from schedule_schedulesettings'];

/** The week and the settings as they are now, as INSERT statements (rows, ids and dates included). */
export function snapshotWeek(): string[] {
  return SNAPSHOT.flatMap((query) => psql(query).split('\n')).filter(Boolean);
}

/** Puts back a week saved with `snapshotWeek`. */
export function restoreWeek(saved: string[]): void {
  psql([...CLEAR, ...saved].join('; '));
}

/** What the schedule specs create is named «E2E …» (dates of 2099). */
export const TAG = 'E2E';

/** Deletes the special days and the overrides named «E2E …», with their intervals. */
export function cleanupExceptions(): void {
  psql(
    [
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      `delete from schedule_overrideinterval where override_id in (select id from schedule_override where reason like '${TAG}%')`,
      `delete from schedule_override where reason like '${TAG}%'`,
    ].join('; '),
  );
}

/** Hours: the seven rows are painted. */
export async function weekReady(page: Page): Promise<void> {
  await expect(shown(page).locator('[data-testid=schedule-hours-row]')).toHaveCount(7);
}

export const rowTexts = (page: Page) => shown(page).locator('[data-testid=schedule-hours-row]').allInnerTexts();

/** Special days: both lists answered (rows or their empty state). */
export async function listsReady(page: Page): Promise<void> {
  const view = shown(page);
  await view.locator('[data-testid=schedule-special-days-row], [data-testid=schedule-special-days-empty]').first().waitFor({ state: 'visible' });
  await view.locator('[data-testid=schedule-overrides-row], [data-testid=schedule-overrides-empty]').first().waitFor({ state: 'visible' });
}

/** A row action: its button, or the «⋮» menu when the row folded its actions (waits for either). */
export async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
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

export async function noHorizontalScroll(page: Page, label: string): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), { message: `no horizontal scroll at ${label}` })
    .toBeLessThanOrEqual(0);
}

/** Waits until nothing moves and the page is painted: helpers.ts's, the one every spec takes. */
export { settled } from './helpers';
