// The business's clock on the screens (hub#687): a business in the Canaries reads the hour an automation inserts in a
// question, and until when it waits for an answer, on its own clock (FLOW-F29), whatever the deployment's is (Madrid);
// the agenda says it is on that clock and Schedules names it (SCHEDULE-F09). Its zone is the registry's, as the SaaS
// pushes it: the spec sets it in `base_hub` and puts it back. The time clock, Tasks and the WhatsApp inbox say every hour
// on that clock too (hub#779), on a device on yet another clock: neither the deployment's hour nor the device's can pass
// for the business's by chance.
// flow: FLOW-F29 SCHEDULE-F09 ATTENDANCE-F01 ATTENDANCE-F07 ATTENDANCE-F08 ATTENDANCE-F10 TASK-F04 WHATSAPP_INBOX-F05
import { type Browser, type BrowserContext, expect, test } from '@playwright/test';

import { manualFlow, signedIn } from './flow-helpers';
import { A, api, login, psql, shown } from './helpers';
import { VIEWPORTS } from './schedule-helpers';
import { cleanUp as cleanInbox, e2ePhone, keepPhoto, PREFIX, receive, restorePhoto } from './whatsapp-helpers';

const ZONE = 'Atlantic/Canary';
const DEVICE = 'Asia/Tokyo';
const TAG = 'E2E BusinessZone';
/** A staff record's first name, what its working days are found by. */
const PERSON = 'E2EZone';
const OWNER_DAYS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${PERSON}%')`;
let saved = '';

type Day = { id: string; clock_in_at: string; clock_out_at: string | null; work_date: string };

const clock = (options: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat('en-GB', { timeZone: ZONE, hourCycle: 'h23', ...options });
/** An instant as the screens say it on the business's clock. */
const hour = (iso: string): string => clock({ hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
/** The same, with its day: `15/10/2026, 09:30`, as Tasks says a moment. */
const moment = (iso: string): string =>
  clock({ day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
/** The same in the form of the CSV and of a `datetime-local` field, `YYYY-MM-DD<separator>HH:MM`. */
function wall(iso: string, separator: string): string {
  const parts = Object.fromEntries(
    clock({ year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
      .formatToParts(new Date(iso))
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}${separator}${parts.hour}:${parts.minute}`;
}

/** The owner on a device on another clock than the business's and the deployment's. */
async function onADeviceElsewhere(browser: Browser, next: string, viewport: { width: number; height: number }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US', timezoneId: DEVICE });
  const page = await context.newPage();
  await login(page, A, next);
  return { context, page };
}

/** The owner's own staff record, and so a working day of their own to clock. */
async function linkOwner(context: BrowserContext): Promise<void> {
  const accounts = await api<{ rows: { user_id: string }[] }>(context, A, 'GET', '/staff/accounts?search=owner%40');
  expect(accounts.data.rows.length).toBeGreaterThan(0);
  const body = { first_name: PERSON, last_name: 'Clock', user_id: accounts.data.rows[0].user_id };
  expect((await api(context, A, 'POST', '/staff/members', body)).status).toBe(201);
}

function cleanUp(): void {
  psql(
    [
      `delete from attendance_correction where record_id in (${OWNER_DAYS})`,
      `delete from attendance_break where record_id in (${OWNER_DAYS})`,
      `delete from attendance_record where id in (${OWNER_DAYS})`,
      `delete from staff_member where first_name like '${PERSON}%'`,
      `delete from task_comment where task_id in (select id from task_task where title like '${TAG}%')`,
      `delete from task_task where title like '${TAG}%'`,
    ].join('; '),
  );
  cleanInbox();
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
    ].join('; '),
  );
}

test.beforeAll(() => {
  keepPhoto();
  cleanUp();
  saved = psql("select timezone from base_hub where slug = 'a'");
  psql(`update base_hub set timezone = '${ZONE}' where slug = 'a'`);
});

test.afterAll(() => {
  // A sweep of the screens looks at what the run leaves: its stack's database is dropped after it.
  if (process.env.E2E_SAVE_STORAGE_STATE) return;
  psql(`update base_hub set timezone = '${saved}' where slug = 'a'`);
  cleanUp();
  restorePhoto();
});

test.beforeEach(cleanUp);

for (const viewport of VIEWPORTS) {
  test(`the time clock, a task and the inbox say each hour on the business's clock, on a device elsewhere, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await onADeviceElsewhere(browser, '/attendance/clock', viewport);
    try {
      await linkOwner(context);
      const opened = await api<Day>(context, A, 'POST', '/attendance/clock_in', {});
      expect(opened.status).toBe(200);
      await page.goto('/attendance/clock');
      await expect(shown(page).locator('[data-testid=attendance-clock-status]')).toHaveText(`Clocked in since ${hour(opened.data.clock_in_at)}`);
      await expect(shown(page).locator('[data-testid=attendance-clock-recent-row]').first()).toContainText(hour(opened.data.clock_in_at));

      await page.goto('/attendance/records');
      await expect(shown(page).locator('[data-testid=attendance-presence-row]', { hasText: PERSON })).toContainText(hour(opened.data.clock_in_at));
      await expect(shown(page).locator('[data-testid=attendance-records-row]', { hasText: PERSON })).toContainText(hour(opened.data.clock_in_at));
      expect((await api(context, A, 'POST', '/attendance/clock_out', {})).status).toBe(200);

      const title = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
      const task = await api<{ created_at: string }>(context, A, 'POST', '/task/tasks', { title });
      expect(task.status).toBe(201);
      await page.goto('/task/tasks');
      await shown(page).locator('[data-testid=task-tasks-row]', { hasText: title }).click();
      await expect(page.locator('[data-testid=task-sheet-created]')).toContainText(moment(task.data.created_at));

      const phone = e2ePhone();
      const said = new Date().toISOString();
      receive(phone, 'Hola', `${PREFIX}Zona`, { sent_at: said });
      await page.goto('/whatsapp_inbox/inbox');
      await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
      const row = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) });
      await expect(row).toContainText(hour(said));
      await row.click();
      const message = shown(page).locator('[data-testid=whatsapp-inbox-detail] [data-testid=whatsapp-inbox-message]');
      await expect(message).toContainText(hour(said));
    } finally {
      await context.close();
    }
  });
}

test("a correction is shown and read on the business's clock, and the CSV says it on it", async ({ browser }) => {
  test.setTimeout(120_000);
  const { context, page } = await onADeviceElsewhere(browser, '/attendance/records', { width: 1440, height: 900 });
  try {
    await linkOwner(context);
    const opened = await api<Day>(context, A, 'POST', '/attendance/clock_in', {});
    expect(opened.status).toBe(200);
    expect((await api(context, A, 'POST', '/attendance/clock_out', {})).status).toBe(200);
    const day = opened.data;

    await page.goto('/attendance/records');
    await shown(page).locator(`[data-testid=attendance-records-row-${day.id}-correct]`).click();
    const dialog = page.locator('ion-modal[data-testid=attendance-correct]');
    const clockIn = dialog.locator('[data-testid=attendance-correct-clock_in] input');
    await expect(clockIn).toHaveValue(wall(day.clock_in_at, 'T'));

    // Ten minutes earlier, typed on the business's clock: the same instant comes back, whatever the device's or the
    // deployment's is.
    const earlier = new Date(Date.parse(day.clock_in_at) - 10 * 60_000).toISOString();
    await clockIn.fill(wall(earlier, 'T'));
    await dialog.locator('[data-testid=attendance-correct-reason] textarea').fill('Arrived earlier, forgot to clock in');
    await dialog.locator('[data-testid=attendance-correct-submit]').click();
    await expect(shown(page).locator('[data-testid=attendance-records-corrected]')).toContainText('Working day corrected.');
    const stored = psql(`select to_char(clock_in_at at time zone '${ZONE}', 'YYYY-MM-DD HH24:MI') from attendance_record where id = '${day.id}'`);
    expect(stored).toBe(wall(earlier, ' '));

    const exported = await api<{ csv: string }>(context, A, 'GET', `/attendance/records/export?date_from=${day.work_date}&date_to=${day.work_date}`);
    expect(exported.status).toBe(200);
    expect(exported.data.csv).toContain(wall(earlier, ' '));
  } finally {
    await context.close();
  }
});

for (const viewport of VIEWPORTS) {
  test(`a question, the agenda and Schedules are on the business's clock, at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const name = `${TAG} ${viewport.label} ${Date.now().toString(36)}`;
    const { context, page } = await signedIn(browser, '/flow/automations', viewport);
    try {
      const step = { id: 's1', kind: 'ask', title: 'Visit {{input.at}}?' };
      const flowId = await manualFlow(context, name, [step], []);
      // 10:00 in Madrid, 9:00 in the Canaries.
      const input = { at: '2026-11-02T10:00:00+01:00' };
      expect((await api(context, A, 'POST', '/flow/flows/run', { id: flowId, input })).status).toBe(200);

      await page.goto('/flow/automations');
      const card = shown(page).locator('[data-testid=flow-inbox] article').filter({ hasText: name });
      await expect(card.locator('[data-testid^=flow-question-title-]')).toHaveText('Visit Nov 2, 2026, 9:00 AM?');
      const expires = psql(`select to_char(expires_at at time zone '${ZONE}', 'HH12:MI') from flow_question q join flow_flow f on f.id = q.flow_id where f.name = '${name}'`);
      await expect(card.locator('[data-testid^=flow-question-silence-]')).toContainText(expires.replace(/^0/, ''));

      await page.goto('/appointment/agenda');
      await expect(shown(page).getByText(`The agenda always shows the business clock: ${ZONE}`)).toBeVisible();

      await page.goto('/schedule/settings');
      await expect(shown(page).locator('[data-testid=schedule-settings-timezone]')).toContainText(ZONE);
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    } finally {
      await context.close();
    }
  });
}
