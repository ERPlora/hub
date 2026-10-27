// flow: ATTENDANCE-F01 ATTENDANCE-F02 ATTENDANCE-F03 ATTENDANCE-F04 ATTENDANCE-F05 ATTENDANCE-F06 ATTENDANCE-F07 ATTENDANCE-F08 ATTENDANCE-F09 ATTENDANCE-F10 ATTENDANCE-F11 ATTENDANCE-F12
// Every flow of the time clock with a screen (apps/attendance/WORKBOOK.md), end to end in each of the three
// sizes, against the real Staff app, with one screenshot per flow and size (`APP-ATTENDANCE-<flow>-<width>`).
// An employee clocks a day with a break (F01, F02) and reads their own month (F06); a manager clocks
// someone else by name (F12), sees who is in (F11) and the whole team (F07), finds a forgotten day waiting
// for review (F05), closes it with a reason (F08), reads its history (F09) and exports the month (F10); the
// settings fix the workplace and the review hours (F04), while «Require location» stays off and every
// device clocks as the counter (F03, partial). What the specs create carries `E2EAtt` and goes away.
import { readFileSync } from 'node:fs';

import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, psql, shot, shown } from './helpers';
import { noHorizontalScroll, rowAction, settled, VIEWPORTS } from './schedule-helpers';

type Rows<T> = { rows: T[]; total: number };
type Day = { id: string; member_name: string; status: string; clock_in_at: string };
type Settings = { require_location: boolean; geofence_radius_m: number; workplace_set: boolean; auto_close_after_hours: number };

const TAG = 'E2EAtt';
const ZONE = 'Europe/Madrid';
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;
const SETTINGS_ROWS =
  "select format('insert into attendance_attendancesettings (id, slot, require_location, geofence_radius_m, workplace_lat, workplace_lng, auto_close_after_hours, updated_at) values (%L, %s, %L, %s, %L, %L, %s, %L)', id, slot, require_location, geofence_radius_m, workplace_lat, workplace_lng, auto_close_after_hours, updated_at) from attendance_attendancesettings";

function cleanup(): void {
  psql(
    [
      `delete from attendance_correction where record_id in (${RECORDS})`,
      `delete from attendance_break where record_id in (${RECORDS})`,
      `delete from attendance_record where id in (${RECORDS})`,
      `delete from staff_member where first_name like '${TAG}%'`,
    ].join('; '),
  );
}

// The settings the hub had are put back after the file; each test starts without the spec's people.
let savedSettings: string[] = [];
test.beforeAll(() => {
  savedSettings = psql(SETTINGS_ROWS).split('\n').filter(Boolean);
});
test.beforeEach(cleanup);
test.afterAll(() => {
  cleanup();
  psql(['delete from attendance_attendancesettings', ...savedSettings].join('; '));
});

async function signedIn(browser: Browser, next: string, viewport: { width: number; height: number }, credentials?: Credentials) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US', timezoneId: ZONE, acceptDownloads: true });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** A staff record made through Staff's API, linked to the account found by `search` (its email) if any. */
async function member(owner: BrowserContext, firstName: string, search?: string): Promise<string> {
  let user_id: number | undefined;
  if (search) {
    const accounts = await api<Rows<{ user_id: number }>>(owner, A, 'GET', `/staff/accounts?search=${encodeURIComponent(search)}&limit=5`);
    expect(accounts.data.rows.length, `account ${search}`).toBeGreaterThan(0);
    user_id = accounts.data.rows[0].user_id;
  }
  const created = await api<{ id: string }>(owner, A, 'POST', '/staff/members', { first_name: firstName, last_name: 'Clock', ...(user_id ? { user_id } : {}) });
  expect(created.status, `staff record ${firstName}`).toBe(201);
  return created.data.id;
}

/** `iso` on the business clock, as a `datetime-local` input takes it (`2026-10-20T09:05`). */
function businessLocal(iso: string): string {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: ZONE, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .format(new Date(iso))
    .replace(' ', 'T');
}

const recordRow = (page: Page, id: string) => shown(page).locator(`[data-testid=attendance-records-row][data-id="${id}"]`);

async function snap(page: Page, flow: string, label: string): Promise<void> {
  await noHorizontalScroll(page, `${flow} ${label}`);
  await settled(page);
  await page.screenshot({ path: shot(`APP-ATTENDANCE-ATTENDANCE-${flow}-${label}`) });
}

for (const vp of VIEWPORTS) {
  const size = { width: vp.width, height: vp.height };

  test(`ATTENDANCE-F01, F02, F06 at ${vp.label}: an employee clocks a day with a break and reads their own month`, async ({ browser }) => {
    const owner = await signedIn(browser, '/staff/members', size);
    const employee = await signedIn(browser, '/attendance/clock', size, EMPLOYEE);
    try {
      const name = `${TAG}${vp.label}Ana`;
      await member(owner.context, name, 'employee@');
      const page = employee.page;
      await page.goto(`${A}/attendance/clock`);
      const view = shown(page);

      // F01: greeted by the staff record's name, clocked out, no days yet.
      await expect(view.locator('[data-testid=attendance-clock-greeting]')).toHaveText(`Hello, ${name} Clock`);
      await expect(view.locator('[data-testid=attendance-clock-status]')).toHaveText('You are clocked out');
      await expect(view.locator('[data-testid=attendance-clock-empty]')).toBeVisible();
      await view.locator('[data-testid=attendance-clock-in]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked in at');
      await expect(view.locator('[data-testid=attendance-clock-status]')).toContainText('Clocked in since');
      await expect(view.locator('[data-testid=attendance-clock-timer]')).toBeVisible();
      // attendance#18: the open day reads «Open», as Records names it.
      await expect(view.locator('[data-testid=attendance-clock-recent-row]').first()).toContainText('Open');
      await snap(page, 'F01', vp.label);

      // F02: a break inside the day; «Clock out» stays at hand.
      await view.locator('[data-testid=attendance-break-start]').click();
      await expect(view.locator('[data-testid=attendance-clock-status]')).toContainText('On break since');
      await expect(view.locator('[data-testid=attendance-break-end]')).toBeVisible();
      await expect(view.locator('[data-testid=attendance-clock-out]')).toBeVisible();
      await snap(page, 'F02', vp.label);
      await view.locator('[data-testid=attendance-break-end]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Break ended at');

      await view.locator('[data-testid=attendance-clock-out]').click();
      await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked out at');
      await expect(view.locator('[data-testid=attendance-clock-status]')).toHaveText('You are clocked out');
      await expect(view.locator('[data-testid=attendance-clock-in]')).toBeVisible();
      await expect(view.locator('[data-testid=attendance-clock-recent-row]').first()).toContainText('Closed');

      // F06: their own month, with «History» and without the team's tools.
      const own = await api<Rows<Day>>(employee.context, A, 'GET', '/attendance/records?limit=5');
      expect(own.data.rows.map((d) => d.member_name)).toEqual([`${name} Clock`]);
      const day = own.data.rows[0];
      await page.goto(`${A}/attendance/records`);
      const records = shown(page);
      await expect(recordRow(page, day.id)).toContainText('Closed');
      await expect(records.locator('[data-testid=attendance-records-month]')).toBeVisible();
      await expect(records.locator('[data-testid=attendance-presence]')).toHaveCount(0);
      await expect(records.locator('[data-testid=attendance-records-person]')).toHaveCount(0);
      await expect(records.locator(`[data-testid=attendance-records-row-${day.id}-correct]`)).toHaveCount(0);
      await snap(page, 'F06', vp.label);
      await rowAction(page, 'attendance-records', day.id, 'history');
      const history = page.locator('ion-modal[data-testid=attendance-history]');
      await expect(history).toHaveClass(/show-modal/);
      await expect(history.locator('[data-testid=attendance-history-empty]')).toHaveText('This working day has never been corrected.');
      await history.locator('[data-testid=attendance-history-close-button]').click();
      await expect(history).toBeHidden();
    } finally {
      await owner.context.close();
      await employee.context.close();
    }
  });

  test(`ATTENDANCE-F05, F07, F08, F09, F10, F11, F12 at ${vp.label}: a manager runs the team's month`, async ({ browser }) => {
    const owner = await signedIn(browser, '/attendance/records', size);
    try {
      const ctx = owner.context;
      const page = owner.page;
      const boss = `${TAG}${vp.label}Boss`;
      const bea = `${TAG}${vp.label}Bea`;
      const cid = `${TAG}${vp.label}Cid`;
      await member(ctx, boss, 'owner@');
      const beaId = await member(ctx, bea);
      const cidId = await member(ctx, cid);

      // F12: the manager clocks Bea in by her name and out by her id; the Hub keeps who did it.
      expect((await api(ctx, A, 'POST', '/attendance/clock_in', { member: `${bea} Clock` })).status).toBe(200);
      expect((await api(ctx, A, 'POST', '/attendance/clock_out', { member_id: beaId })).status).toBe(200);
      const beaDay = (await api<Rows<Day>>(ctx, A, 'GET', `/attendance/records?member_id=${beaId}&limit=5`)).data.rows[0];
      expect(beaDay.status).toBe('closed');
      expect(psql(`select created_by_id is not null from attendance_record where id = '${beaDay.id}'`)).toBe('t');
      // F05: Cid forgot to clock out 13 hours ago (more than the 12 of the settings).
      psql(
        `insert into attendance_record (id, work_date, clock_in_at, status, source, note, created_at, updated_at, member_id) values (gen_random_uuid(), ((now() - interval '13 hours') at time zone '${ZONE}')::date, now() - interval '13 hours', 'open', 'shared', '', now(), now(), '${cidId}')`,
      );
      const cidDay = (await api<Rows<Day>>(ctx, A, 'GET', `/attendance/records?member_id=${cidId}&limit=5`)).data.rows[0];
      // F11: the manager is in now.
      expect((await api(ctx, A, 'POST', '/attendance/clock_in', {})).status).toBe(200);

      await page.goto(`${A}/attendance/records`);
      const view = shown(page);

      // F11: «Clocked in now» names the manager, never the forgotten day.
      const presence = view.locator('[data-testid=attendance-presence]');
      await expect(presence.locator('[data-testid=attendance-presence-row]', { hasText: `${boss} Clock` })).toBeVisible();
      await expect(presence.locator('[data-testid=attendance-presence-row]', { hasText: `${cid} Clock` })).toHaveCount(0);
      await snap(page, 'F11', vp.label);

      // F07: the whole team with each person's name, and the search narrows it to one person.
      await expect(recordRow(page, beaDay.id)).toContainText(`${bea} Clock`);
      await expect(recordRow(page, cidDay.id)).toContainText(`${cid} Clock`);
      if (vp.width >= 834) {
        // The list fits its box: nothing slides under the pinned actions. The list is the DataTable that
        // holds the days' rows: its `testid` only prefixes its hooks, and `[data-testid=attendance-records]`
        // is the page's notices, so a probe under it never met the list and always passed.
        const scroll = view.locator('.data-table', { has: page.locator('[data-testid=attendance-records-row]') }).locator('.data-table__scroll');
        await expect(scroll, `the list of days at ${vp.label}`).toHaveCount(1);
        await expect(scroll, `the list of days fits its box at ${vp.label}`).not.toHaveClass(/(^|\s)data-table__scroll--overflow(\s|$)/);
        // In the list, each person's whole name is read, never cut to «E2EAtt834B…».
        for (const id of [beaDay.id, cidDay.id]) {
          const name = recordRow(page, id).locator('[role=cell]').nth(1).locator('.data-table__text');
          expect(await name.evaluate((el) => el.scrollWidth - el.clientWidth), `the name of ${id} fits at ${vp.label}`).toBeLessThanOrEqual(0);
          // …and its whole status, on one line and inside its cell («Needs review», never «Needs / review»
          // nor «Needs revie» under the row's actions).
          const label = recordRow(page, id).locator('[role=cell] .status-pill__label').last();
          const [wrapped, spill] = await label.evaluate((el) => {
            const height = el.getBoundingClientRect().height;
            el.style.whiteSpace = 'nowrap';
            const oneLine = el.getBoundingClientRect().height;
            el.style.whiteSpace = '';
            const pill = el.closest('.status-pill') as HTMLElement;
            const actions = el.closest('[role=row]')?.querySelector('.data-table__cell--actions') as HTMLElement | null;
            const edge = actions ? actions.getBoundingClientRect().left : (el.closest('[role=cell]') as HTMLElement).getBoundingClientRect().right;
            return [height - oneLine, pill.getBoundingClientRect().right - edge];
          });
          expect(wrapped, `the status of ${id} on one line at ${vp.label}`).toBeLessThanOrEqual(0);
          expect(spill, `the status of ${id} clear of the row's actions at ${vp.label}`).toBeLessThanOrEqual(0);
        }
        // attendance#14: no header runs into the next one.
        const heads = await view.locator('[role=columnheader] > span:first-child').evaluateAll((spans) =>
          spans.map((span) => ({ text: span.textContent?.trim() ?? '', box: span.getBoundingClientRect().toJSON() as DOMRect })).filter((head) => head.text),
        );
        for (let i = 1; i < heads.length; i += 1) {
          expect(heads[i].box.left - heads[i - 1].box.right, `«${heads[i - 1].text}» and «${heads[i].text}» apart at ${vp.label}`).toBeGreaterThanOrEqual(8);
        }
      }
      await snap(page, 'F07', vp.label);
      await page.screenshot({ path: shot(`FIX-HUB-E2E-ATTENDANCE-OVERFLOW-PROBE-DEAD-${vp.label}`) });
      const search = view.locator('[data-testid=attendance-records-search] input');
      await search.fill(cid);
      await expect(recordRow(page, beaDay.id)).toHaveCount(0);

      // F05: the forgotten day waits for review, with no worked time.
      await expect(recordRow(page, cidDay.id)).toContainText('Needs review');
      await snap(page, 'F05', vp.label);

      // F08: a manager closes it with a clock-out and a reason; a short reason is refused first.
      await rowAction(page, 'attendance-records', cidDay.id, 'correct');
      const dialog = page.locator('ion-modal[data-testid=attendance-correct]');
      await expect(dialog).toHaveClass(/show-modal/);
      await expect(dialog.locator('[data-testid=attendance-correct-clock_in] input')).toHaveValue(businessLocal(cidDay.clock_in_at));
      const out = new Date(Date.parse(cidDay.clock_in_at) + 8 * 3600_000).toISOString();
      await dialog.locator('[data-testid=attendance-correct-clock_out] input').fill(businessLocal(out));
      await dialog.locator('[data-testid=attendance-correct-reason] textarea').fill('no');
      await dialog.locator('[data-testid=attendance-correct-submit]').click();
      await expect(dialog.locator('[data-testid=attendance-correct-reason]')).toContainText('Write a reason of at least 3 characters.');
      await dialog.locator('[data-testid=attendance-correct-reason] textarea').fill('Forgot to clock out');
      await snap(page, 'F08', vp.label);
      await dialog.locator('[data-testid=attendance-correct-submit]').click();
      await expect(dialog).toBeHidden();
      await expect(view.locator('[data-testid=attendance-records-corrected]')).toContainText('Working day corrected.');
      await expect(recordRow(page, cidDay.id)).toContainText('Closed');

      // F09: who corrected it, before → after and the reason.
      await rowAction(page, 'attendance-records', cidDay.id, 'history');
      const history = page.locator('ion-modal[data-testid=attendance-history]');
      // Ionic's sheet slides in after its content is there: the person sees it once it shows.
      await expect(history).toHaveClass(/show-modal/);
      const item = history.locator('[data-testid=attendance-history-item]');
      await expect(item).toHaveCount(1);
      await expect(item).toContainText('Forgot to clock out');
      await expect(item).toContainText('Before');
      await expect(item).toContainText('After');
      await snap(page, 'F09', vp.label);
      await history.locator('[data-testid=attendance-history-close-button]').click();
      await expect(history).toBeHidden();
      await search.fill('');
      await expect(recordRow(page, beaDay.id)).toBeVisible();

      // F10: the month in CSV, every day of the filter, written by the server.
      const download = page.waitForEvent('download');
      await view.locator('[data-testid=attendance-export-csv]').click();
      const file = await download;
      expect(file.suggestedFilename()).toMatch(/^attendance-\d{4}-\d{2}\.csv$/);
      const text = readFileSync((await file.path()) as string, 'utf8');
      expect(text.startsWith('﻿'), 'a BOM, so a spreadsheet reads the accents').toBe(true);
      const [header, ...lines] = text.slice(1).trim().split('\r\n');
      expect(header).toBe('date,user,clock_in,clock_out,break_minutes,worked_minutes,status,within_radius_in,within_radius_out');
      expect(lines.join('\n')).toContain(`${bea} Clock`);
      expect(lines.join('\n')).toContain(`${cid} Clock`);
      // A month without days: the table says so and the file only has the header.
      await view.locator('[data-testid=attendance-records-month]').click();
      await page.locator('ion-popover.select-popover ion-radio').nth(13).click();
      await expect(page.locator('ion-popover.select-popover')).toBeHidden();
      await expect(view.locator('[data-testid=attendance-records-empty]')).toBeVisible();
      const empty = page.waitForEvent('download');
      await view.locator('[data-testid=attendance-export-csv]').click();
      expect(readFileSync((await (await empty).path()) as string, 'utf8').slice(1).trim().split('\r\n')).toHaveLength(1);
      await expect(view.locator('[data-testid=attendance-records-export-notice]')).toContainText('the file only has the header');
      await snap(page, 'F10', vp.label);

      // F11 again: the manager clocks out and leaves «Clocked in now» at once.
      expect((await api(ctx, A, 'POST', '/attendance/clock_out', {})).status).toBe(200);
      await expect(presence.locator('[data-testid=attendance-presence-row]', { hasText: `${boss} Clock` })).toHaveCount(0);
    } finally {
      await owner.context.close();
    }
  });

  test(`ATTENDANCE-F03, F04 at ${vp.label}: the settings fix the workplace and the review hours; every device clocks as the counter`, async ({ browser }) => {
    psql('delete from attendance_attendancesettings');
    const owner = await signedIn(browser, '/attendance/settings', size);
    try {
      const { context, page } = owner;
      await context.grantPermissions(['geolocation'], { origin: A });
      await context.setGeolocation({ latitude: 40.4168, longitude: -3.7038, accuracy: 12 });
      await page.goto(`${A}/attendance/settings`);
      const view = shown(page);
      const form = view.locator('[data-testid=attendance-settings-form]');
      await expect(form).toBeVisible();
      // The whole form fits the screen: nothing runs past its right edge (a phone included).
      const past = await form.evaluate((el) => {
        const right = window.innerWidth;
        return Math.max(el.scrollWidth - el.clientWidth, ...[...el.querySelectorAll('*')].map((child) => child.getBoundingClientRect().right - right));
      });
      expect(past, `the settings fit ${vp.label}`).toBeLessThanOrEqual(0);

      // F03 (partial): «Require location» stays off and says why.
      await expect(view.locator('[data-testid=attendance-settings-require_location]')).toHaveClass(/toggle-disabled/);
      await expect(view.locator('[data-testid=attendance-settings-location-pending]')).toContainText("whether a device is the counter POS or someone's own phone");
      await snap(page, 'F03', vp.label);

      // F04: the workplace from this device, and the review hours (a wrong value is pointed at first).
      await view.locator('[data-testid=attendance-settings-use-location]').click();
      await expect(view.locator('[data-testid=attendance-settings-workplace_lat] input')).toHaveValue('40.4168');
      await expect(view.locator('[data-testid=attendance-settings-workplace_lng] input')).toHaveValue('-3.7038');
      await expect(view.locator('[data-testid=attendance-settings-accuracy]')).toContainText('±12 m');
      const hours = view.locator('[data-testid=attendance-settings-auto_close_after_hours]');
      await hours.locator('input').fill('30');
      await view.locator('[data-testid=attendance-settings-save]').click();
      await expect(hours).toContainText('Enter a whole number of hours between 1 and 24.');
      await hours.locator('input').fill('10');
      await view.locator('[data-testid=attendance-settings-save]').click();
      await expect(view.locator('[data-testid=attendance-settings-saved]')).toContainText('Settings saved.');
      await snap(page, 'F04', vp.label);
      const saved = await api<Settings>(context, A, 'GET', '/attendance/settings');
      expect([saved.data.workplace_set, saved.data.auto_close_after_hours, saved.data.require_location]).toEqual([true, 10, false]);

      // F03: even with the location asked for (the API takes it), the browser clocks as the counter POS:
      // no position is read and the day keeps no coordinates.
      expect((await api(context, A, 'POST', '/attendance/settings', { require_location: true })).status).toBe(200);
      const meId = await member(context, `${TAG}${vp.label}Counter`, 'owner@');
      await page.goto(`${A}/attendance/clock`);
      const clock = shown(page);
      await clock.locator('[data-testid=attendance-clock-in]').click();
      await expect(clock.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked in at');
      await expect(clock.locator('[data-testid=attendance-clock-location-note]')).toHaveCount(0);
      expect(psql(`select source || ',' || (in_lat is null) from attendance_record where member_id = '${meId}'`)).toBe('shared,true');
      expect((await api(context, A, 'POST', '/attendance/clock_out', {})).status).toBe(200);
    } finally {
      await owner.context.close();
    }
  });
}
