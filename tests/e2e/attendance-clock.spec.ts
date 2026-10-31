// Time clock (apps/attendance, WORKBOOK ATTENDANCE-F01, F02, F06–F11) against the real Staff app: the
// staff records the clock uses are created and linked to the PoC's accounts through Staff's own API.
// An employee clocks a whole day with a break on the Clock in screen and sees it in Records (no team,
// no Correct, and the API agrees); a manager sees who is in now, corrects that day with its reason,
// reads its history and exports the month in CSV. Everything the specs create carries `E2EAtt` and
// goes away afterwards (working days, then the staff records).
import { readFileSync } from 'node:fs';

import { type Browser, type BrowserContext, expect, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, psql, shot, shown } from './helpers';

type Envelope = { error?: { code: string } };
type Page<T> = { rows: T[]; total: number };
type Day = { id: string; member_name: string; status: string };

const TAG = 'E2EAtt';
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;

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

// Each test starts clean: an account holds one live staff record, and two tests link the owner's.
test.beforeEach(cleanup);
test.afterAll(cleanup);

async function signedIn(browser: Browser, next: string, credentials?: Credentials, viewport = { width: 1280, height: 860 }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US', acceptDownloads: true });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** A staff record linked to the account found by `search` (its email), made through Staff's API. */
async function linkedMember(owner: BrowserContext, search: string, firstName: string): Promise<string> {
  const accounts = await api<Page<{ user_id: string; name: string }>>(owner, A, 'GET', `/staff/accounts?search=${encodeURIComponent(search)}&limit=5`);
  expect(accounts.status).toBe(200);
  expect(accounts.data.rows.length, `account ${search}`).toBeGreaterThan(0);
  const member = await api<{ id: string }>(owner, A, 'POST', '/staff/members', {
    first_name: firstName,
    last_name: 'Clock',
    user_id: accounts.data.rows[0].user_id,
  });
  expect(member.status, `staff record for ${search}`).toBe(201);
  return member.data.id;
}

test('an employee clocks a whole day with a break and sees only their own days', async ({ browser }) => {
  const owner = await signedIn(browser, '/staff/members');
  const employee = await signedIn(browser, '/attendance/clock', EMPLOYEE);
  try {
    const anaName = `${TAG}Ana`;
    await linkedMember(owner.context, 'employee@', anaName);

    const view = shown(employee.page);
    await employee.page.goto(`${A}/attendance/clock`);
    await expect(view.locator('[data-testid=attendance-clock-greeting]')).toHaveText(`Hello, ${anaName} Clock`);
    await expect(view.locator('[data-testid=attendance-clock-status]')).toHaveText('You are clocked out');

    await view.locator('[data-testid=attendance-clock-in]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked in at');
    await expect(view.locator('[data-testid=attendance-clock-status]')).toContainText('Clocked in since');
    await expect(view.locator('[data-testid=attendance-clock-timer]')).toBeVisible();

    await view.locator('[data-testid=attendance-break-start]').click();
    await expect(view.locator('[data-testid=attendance-clock-status]')).toContainText('On break since');
    await view.locator('[data-testid=attendance-break-end]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Break ended at');
    await employee.page.screenshot({ path: shot('attendance-clock-in-progress') });

    await view.locator('[data-testid=attendance-clock-out]').click();
    await expect(view.locator('[data-testid=attendance-clock-message]')).toContainText('Clocked out at');
    await expect(view.locator('[data-testid=attendance-clock-status]')).toHaveText('You are clocked out');
    await expect(view.locator('[data-testid=attendance-clock-recent-row]').first()).toContainText('Closed');

    // Records: their own day, «History» but no «Correct», no Person, no «Clocked in now».
    await employee.page.goto(`${A}/attendance/records`);
    const records = shown(employee.page);
    const own = await api<Page<Day>>(employee.context, A, 'GET', '/attendance/records?limit=5');
    expect(own.status).toBe(200);
    expect(new Set(own.data.rows.map((d) => d.member_name))).toEqual(new Set([`${anaName} Clock`]));
    const dayId = own.data.rows[0].id;
    await expect(records.locator(`[data-testid=attendance-records-row-${dayId}-history]`)).toBeVisible();
    await expect(records.locator(`[data-testid=attendance-records-row-${dayId}-correct]`)).toHaveCount(0);
    await expect(records.locator('[data-testid=attendance-presence]')).toHaveCount(0);
    await expect(records.locator('[data-testid=attendance-records-person]')).toHaveCount(0);
    await employee.page.screenshot({ path: shot('attendance-records-employee') });

    // The API agrees: no team, no correction, no settings change.
    for (const [method, path, body] of [
      ['GET', '/attendance/presence', undefined],
      ['POST', '/attendance/records/correct', { record_id: dayId, clock_in_at: '2026-01-01T08:00:00Z', reason: 'Mine' }],
      ['POST', '/attendance/settings', { auto_close_after_hours: 3 }],
    ] as const) {
      const res = await api<Envelope>(employee.context, A, method, path, body);
      expect(res.status, path).toBe(403);
      expect(res.data.error?.code, path).toBe('permission_denied');
    }
    // Settings: read-only for an employee.
    await employee.page.goto(`${A}/attendance/settings`);
    await expect(shown(employee.page).locator('[data-testid=attendance-settings-read-only]')).toBeVisible();
    await expect(shown(employee.page).locator('[data-testid=attendance-settings-save]')).toHaveCount(0);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});

test('a manager sees who is in, corrects a day with its reason, reads its history and exports the month', async ({ browser }) => {
  const owner = await signedIn(browser, '/attendance/records');
  try {
    // Bea has no account: the manager clocks her (ATTENDANCE-F12).
    const created = await api<{ id: string }>(owner.context, A, 'POST', '/staff/members', { first_name: `${TAG}Bea`, last_name: 'Clock' });
    expect(created.status).toBe(201);
    const bea = created.data.id;
    await linkedMember(owner.context, 'owner@', `${TAG}Boss`);
    // Bea's day, clocked by the manager; the manager is in now.
    expect((await api(owner.context, A, 'POST', '/attendance/clock_in', { member_id: bea })).status).toBe(200);
    expect((await api(owner.context, A, 'POST', '/attendance/clock_out', { member_id: bea })).status).toBe(200);
    expect((await api(owner.context, A, 'POST', '/attendance/clock_in', {})).status).toBe(200);

    const page = owner.page;
    await page.goto(`${A}/attendance/records`);
    const view = shown(page);
    await expect(view.locator('[data-testid=attendance-presence-row]', { hasText: `${TAG}Boss Clock` })).toBeVisible();
    const days = await api<Page<Day>>(owner.context, A, 'GET', `/attendance/records?member_id=${bea}&limit=5`);
    const day = days.data.rows[0];
    const row = view.locator(`[data-testid=attendance-records-row-${day.id}-correct]`);
    await expect(row).toBeVisible();
    await page.screenshot({ path: shot('attendance-records-manager') });

    // Correct: ten minutes earlier on the business clock, with its reason.
    await row.click();
    const dialog = page.locator('ion-modal[data-testid=attendance-correct]');
    await expect(dialog).toBeVisible();
    const earlier = new Intl.DateTimeFormat('sv-SE', {
      timeZone: 'Europe/Madrid',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .format(new Date(Date.now() - 10 * 60_000))
      .replace(' ', 'T');
    await dialog.locator('[data-testid=attendance-correct-clock_in] input').fill(earlier);
    await dialog.locator('[data-testid=attendance-correct-reason] textarea').fill('Arrived earlier, forgot to clock in');
    await dialog.locator('[data-testid=attendance-correct-submit]').click();
    await expect(view.locator('[data-testid=attendance-records-corrected]')).toContainText('Working day corrected.');

    // History: who, before → after, and the reason.
    await view.locator(`[data-testid=attendance-records-row-${day.id}-history]`).click();
    const history = page.locator('ion-modal[data-testid=attendance-history]');
    await expect(history.locator('[data-testid=attendance-history-item]')).toHaveCount(1);
    await expect(history.locator('[data-testid=attendance-history-item]')).toContainText('Arrived earlier, forgot to clock in');
    await page.screenshot({ path: shot('attendance-history') });
    await history.locator('[data-testid=attendance-history-close-button]').click();

    // CSV of the month: every row of the filter, by the server.
    const download = page.waitForEvent('download');
    await view.locator('[data-testid=attendance-export-csv]').click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/^attendance-\d{4}-\d{2}\.csv$/);
    const text = readFileSync((await file.path()) as string, 'utf8').replace(/^﻿/, '');
    const [header, ...lines] = text.trim().split('\r\n');
    expect(header).toBe('date,user,clock_in,clock_out,break_minutes,worked_minutes,status,within_radius_in,within_radius_out');
    expect(lines.join('\n')).toContain(`${TAG}Bea Clock`);

    // The manager clocks out: nobody of the spec is in any more.
    expect((await api(owner.context, A, 'POST', '/attendance/clock_out', {})).status).toBe(200);
    await expect(view.locator('[data-testid=attendance-presence-row]', { hasText: `${TAG}Boss Clock` })).toHaveCount(0);
  } finally {
    await owner.context.close();
  }
});

test('the clock fits a phone', async ({ browser }) => {
  const owner = await signedIn(browser, '/attendance/clock', undefined, { width: 390, height: 844 });
  try {
    await linkedMember(owner.context, 'owner@', `${TAG}Phone`);
    await owner.page.goto(`${A}/attendance/clock`);
    const view = shown(owner.page);
    await expect(view.locator('[data-testid=attendance-clock-in]')).toBeVisible();
    const box = await view.locator('[data-testid=attendance-clock-in]').boundingBox();
    expect(box?.width ?? 0).toBeLessThanOrEqual(390);
    await owner.page.screenshot({ path: shot('attendance-clock-phone') });
  } finally {
    await owner.context.close();
  }
});
