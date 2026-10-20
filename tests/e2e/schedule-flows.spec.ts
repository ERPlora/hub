// flow: SCHEDULE-F01 SCHEDULE-F02 SCHEDULE-F03 SCHEDULE-F04 SCHEDULE-F05 SCHEDULE-F06 SCHEDULE-F08 SCHEDULE-F09 SCHEDULE-F13
// Every flow of Schedules that has a screen, end to end in each of the three sizes (apps/schedule/WORKBOOK.md),
// with one screenshot per flow and size (`APP-SCHEDULE-<flow>-<width>`): the owner of hub `a` reads the
// default week (F01) and its notice (F03), edits a day (F02), confirms the week, reads the business zone
// (F09) and makes the week start on Sunday (F08); then adds a special day (F04), corrects it (F13), adds an
// override (F05) and deletes both after confirming (F06). What the hub had is put back after the file.
import { expect, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';
import {
  cleanupExceptions,
  DEFAULT_WEEK,
  listsReady,
  noHorizontalScroll,
  restoreWeek,
  rowAction,
  rowTexts,
  settled,
  snapshotWeek,
  TAG,
  VIEWPORTS,
  weekReady,
} from './schedule-helpers';

let saved: string[] = [];

test.beforeAll(() => {
  saved = snapshotWeek();
  cleanupExceptions();
});
test.afterAll(() => {
  restoreWeek(saved);
  cleanupExceptions();
});

for (const vp of VIEWPORTS) {
  test(`SCHEDULE-F01, F02, F03, F08, F09 at ${vp.label}: the week, a day edited, the week confirmed and the settings`, async ({ page, context }) => {
    psql(DEFAULT_WEEK);
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await login(page, A, '/schedule/hours');
    await weekReady(page);
    const view = shown(page);

    // F01: seven fixed rows, Monday first; no «+».
    const rows = await rowTexts(page);
    expect(rows[0]).toContain('Monday');
    expect(rows[0]).toContain('09:00 AM–06:00 PM');
    expect(rows[6]).toContain('Closed');
    await expect(view.locator('[data-testid=schedule-hours-add]')).toHaveCount(0);
    await noHorizontalScroll(page, `hours ${vp.label}`);
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F01-${vp.label}`) });

    // F03: the default week says so, with «Yes, these are my hours».
    const notice = view.locator('[data-testid=schedule-hours-default-week]');
    await expect(notice).toContainText('These are default opening hours we set up for you.');
    await expect(notice.locator('[data-testid=schedule-hours-confirm-week]')).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F03-${vp.label}`) });

    // F02: Saturday opens 10:00–14:00.
    await rowAction(page, 'schedule-hours', '5', 'edit');
    const dialog = page.locator('ion-modal[data-testid=schedule-day-form]');
    await expect(dialog.locator('ion-title')).toHaveText('Edit hours — Saturday');
    await page.locator('[data-testid=schedule-day-form-closed]').click();
    await page.locator('[data-testid=schedule-day-form-intervals-open-0] input').fill('10:00');
    await page.locator('[data-testid=schedule-day-form-intervals-close-0] input').fill('14:00');
    await expect(page.locator('[data-testid=schedule-day-form-submit]')).toBeInViewport({ ratio: 1 });
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F02-${vp.label}`) });
    await page.locator('[data-testid=schedule-day-form-submit]').click();
    await expect(dialog).toBeHidden();
    expect((await rowTexts(page))[5]).toContain('10:00 AM–02:00 PM');
    // Whoever saves a day has seen the week: the notice goes, and the server agrees.
    await expect(notice).toHaveCount(0);
    const week = await api<{ confirmed: boolean; days: { weekday: number; is_closed: boolean }[] }>(context, A, 'GET', '/schedule/week');
    expect([week.data.confirmed, week.data.days[5].is_closed]).toEqual([true, false]);

    // F09 and F08: the business zone, read only; the week starts on Sunday, and Hours opens on it.
    await page.goto(`${A}/schedule/settings`);
    await expect(view.locator('[data-testid=schedule-settings-timezone]')).toContainText('Europe/Madrid');
    await noHorizontalScroll(page, `settings ${vp.label}`);
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F09-${vp.label}`) });
    await view.locator('[data-testid=schedule-settings-week-start]').click();
    await page.locator('ion-popover ion-radio', { hasText: 'Sunday' }).click();
    await expect(page.locator('ion-popover.select-popover')).toHaveCount(0);
    await view.locator('[data-testid=schedule-settings-submit]').click();
    await expect(view.locator('[data-testid=schedule-settings-saved]')).toHaveText('Saved');
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F08-${vp.label}`) });
    await page.goto(`${A}/schedule/hours`);
    await weekReady(page);
    expect((await rowTexts(page))[0]).toContain('Sunday');
  });

  test(`SCHEDULE-F04, F13, F05, F06 at ${vp.label}: a special day added and corrected, an override added, both deleted`, async ({ page, context }) => {
    const stamp = `${vp.label} ${Date.now().toString(36)}`;
    const name = `${TAG} Christmas ${stamp}`;
    const reason = `${TAG} Summer ${stamp}`;
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await login(page, A, '/schedule/special-days');
    await listsReady(page);
    const view = shown(page);
    await noHorizontalScroll(page, `special days ${vp.label}`);

    // F04: «+» → Date and Name, closed by default → «Add day».
    await view.locator('[data-testid=schedule-special-days-add]').click();
    await page.locator('[data-testid=schedule-special-day-form-date] input').fill('2099-12-25');
    await page.locator('[data-testid=schedule-special-day-form-name] input').fill(name);
    await expect(page.locator('[data-testid=schedule-special-day-form-submit]')).toBeInViewport({ ratio: 1 });
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F04-${vp.label}`) });
    await page.locator('[data-testid=schedule-special-day-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=schedule-special-day-form]')).toBeHidden();
    const day = view.locator('[data-testid=schedule-special-days-row]', { hasText: name });
    await expect(day).toContainText('12/25/2099');
    await expect(day).toContainText('Closed');

    // F13: the row opens it with what it has; open 10:00–13:00 and «Save».
    await day.getByText(name).click();
    await expect(page.locator('ion-modal[data-testid=schedule-special-day-form] ion-title')).toHaveText(`Edit · ${name}`);
    await page.locator('[data-testid=schedule-special-day-form-status]').click();
    await page.locator('ion-popover ion-radio', { hasText: 'Open (with hours)' }).click();
    await expect(page.locator('ion-popover.select-popover')).toHaveCount(0);
    await page.locator('[data-testid=schedule-special-day-form-intervals-open-0] input').fill('10:00');
    await page.locator('[data-testid=schedule-special-day-form-intervals-close-0] input').fill('13:00');
    await expect(page.locator('[data-testid=schedule-special-day-form-submit]')).toBeInViewport({ ratio: 1 });
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F13-${vp.label}`) });
    await page.locator('[data-testid=schedule-special-day-form-submit]').click();
    await expect(day).toContainText('10:00 AM–01:00 PM');
    const open = await api<{ is_open: boolean; source: string }>(context, A, 'GET', '/schedule/is_open?when=2099-12-25T12:00');
    expect([open.data.is_open, open.data.source]).toEqual([true, 'special_day']);

    // F05: «+» on Overrides → From, To and Reason, closed → «Add override».
    await view.locator('[data-testid=schedule-overrides-add]').click();
    await page.locator('[data-testid=schedule-override-form-start_date] input').fill('2099-08-01');
    await page.locator('[data-testid=schedule-override-form-end_date] input').fill('2099-08-15');
    await page.locator('[data-testid=schedule-override-form-reason] input').fill(reason);
    await expect(page.locator('[data-testid=schedule-override-form-submit]')).toBeInViewport({ ratio: 1 });
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F05-${vp.label}`) });
    await page.locator('[data-testid=schedule-override-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=schedule-override-form]')).toBeHidden();
    const change = view.locator('[data-testid=schedule-overrides-row]', { hasText: reason });
    await expect(change).toContainText('08/01/2099');

    // F06: «Delete» asks first, then the row goes; the date is free again.
    const dayId = psql(`select id from schedule_specialday where name = '${name}'`);
    await rowAction(page, 'schedule-special-days', dayId, 'delete');
    const confirm = page.locator('ion-modal[data-testid=schedule-special-day-delete]');
    await expect(confirm).toContainText(`«${name}» will be deleted. This cannot be undone.`);
    await expect(page.locator('[data-testid=schedule-special-day-delete-submit]')).toBeInViewport({ ratio: 1 });
    await settled(page);
    await page.screenshot({ path: shot(`APP-SCHEDULE-SCHEDULE-F06-${vp.label}`) });
    await page.locator('[data-testid=schedule-special-day-delete-submit]').click();
    await expect(confirm).toBeHidden();
    await expect(day).toHaveCount(0);
    const changeId = psql(`select id from schedule_override where reason = '${reason}'`);
    await rowAction(page, 'schedule-overrides', changeId, 'delete');
    await page.locator('[data-testid=schedule-override-delete-submit]').click();
    await expect(page.locator('ion-modal[data-testid=schedule-override-delete]')).toBeHidden();
    await expect(change).toHaveCount(0);
    expect(psql(`select count(*) from schedule_specialday where date = '2099-12-25'`)).toBe('0');
  });
}
