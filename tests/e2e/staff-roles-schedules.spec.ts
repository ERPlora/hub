// Staff → Roles and Schedules in Chrome (WORKBOOK STAFF-F04, F13–F15). Roles: the owner creates a
// role (0 members), sees a duplicate name refused in the form (409), and retires it from «Edit»: it
// stays listed, marked «Retired». Schedules: for a member picked by searching the server, «+» proposes
// Monday to Friday with the default working day of Settings (as proposed: 09:00–18:00, break 13:00–14:00;
// STAFF-F22) and «Create schedule» lists it as the default one with its
// hours; a day ending before it starts is refused under that day (422); editing drops Friday; «Delete»
// asks first and empties the list. Everything this spec creates is named «E2E …» and removed after it.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, shot, shown } from './helpers';

const TAG = 'E2E';

function cleanup(): void {
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from staff_timeoff where member_id in (${members})`,
      `delete from staff_scheduleday where schedule_id in (select id from staff_schedule where member_id in (${members}))`,
      `delete from staff_schedule where member_id in (${members})`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from staff_role where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanup);
test.afterAll(cleanup);

async function ownerPage(browser: Browser, next: string) {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1280, height: 860 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return { context, page };
}

async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await shown(page).locator(`[data-testid=${table}-row-${id}-menu]`).click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

test('Roles: create, a duplicate refused in the form, retire from Edit (still listed, marked)', async ({ browser }) => {
  const name = `${TAG} Colourist ${Date.now().toString(36)}`;
  const { context, page } = await ownerPage(browser, '/staff/roles');
  try {
    const view = shown(page);
    await view.locator('[data-testid=staff-roles-empty], [data-testid=staff-roles-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=staff-roles-add]').click();
    await page.locator('[data-testid=staff-role-form-name] input').fill(name);
    await page.locator('[data-testid=staff-role-form-description] input').fill('Colour specialist');
    await page.locator('[data-testid=staff-role-form-color] input').fill('#7A3EA8');
    await page.screenshot({ path: shot('staff-roles-new') });
    await page.locator('[data-testid=staff-role-form-submit]').click();
    const row = view.locator('[data-testid=staff-roles-row]', { hasText: name });
    await expect(row).toContainText('Colour specialist');
    await expect(row).toContainText('0');

    // The same name, another case: refused in the form (409 staff.role_name_taken).
    await view.locator('[data-testid=staff-roles-add]').click();
    await page.locator('[data-testid=staff-role-form-name] input').fill(name.toUpperCase());
    await page.locator('[data-testid=staff-role-form-submit]').click();
    await expect(page.locator('[data-testid=staff-role-form-error]')).toContainText('A role with that name already exists.');
    await page.locator('[data-testid=staff-role-form-cancel]').click();

    // Retire it from «Edit · {name}».
    await row.getByText(name).click();
    await expect(page.locator('ion-modal[data-testid=staff-role-form] ion-title')).toHaveText(`Edit · ${name}`);
    await page.locator('[data-testid=staff-role-form-is_active]').click();
    await page.locator('[data-testid=staff-role-form-submit]').click();
    await expect(row.locator('[data-testid=staff-roles-retired]')).toBeVisible();
    await page.screenshot({ path: shot('staff-roles-desktop') });
  } finally {
    await context.close();
  }
});

test('Schedules: the default week, a day refused under its row, edit, delete', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const { context, page } = await ownerPage(browser, '/staff/schedules');
  try {
    const created = await api<{ id: string; full_name: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG} Sara`, last_name: `Shifts${stamp}` });
    expect(created.status).toBe(201);
    const name = created.data.full_name;
    const view = shown(page);

    // Pick the member by searching the server.
    const member = view.locator('[data-testid=staff-schedules-member] input');
    await member.click();
    await member.fill(`Shifts${stamp}`);
    await page.locator('[data-testid^=staff-schedules-member-option-]', { hasText: name }).first().click();
    await expect(view.locator('[data-testid=staff-schedules-member] input')).toHaveValue(name);
    await expect(view.locator('[data-testid=staff-schedules-empty]')).toContainText('This member has no schedules yet.');

    // «+»: Monday to Friday 09:00–18:00 with a break 13:00–14:00 (the working day of Settings as proposed);
    // a Monday ending before it starts is refused under Monday.
    await view.locator('[data-testid=staff-schedules-add]').click();
    await expect(page.locator('[data-testid=staff-schedule-form-day-5-off]')).toHaveText('Off');
    await page.locator('[data-testid=staff-schedule-form-day-0-end] input').fill('08:00');
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    await expect(page.locator('[data-testid=staff-schedule-form-day-0-error]')).toContainText('The start time must be before the end time.');
    await page.screenshot({ path: shot('staff-schedules-422') });
    await page.locator('[data-testid=staff-schedule-form-day-0-end] input').fill('18:00');
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    const row = view.locator('[data-testid=staff-schedules-row]').first();
    await expect(row).toContainText('Yes');
    await expect(row).toContainText(
      'Mon 09:00–18:00 (13:00–14:00) · Tue 09:00–18:00 (13:00–14:00) · Wed 09:00–18:00 (13:00–14:00) · Thu 09:00–18:00 (13:00–14:00) · Fri 09:00–18:00 (13:00–14:00)',
    );

    // Edit: Friday off; the week is replaced.
    await row.getByText('Regular schedule').click();
    await page.locator('[data-testid=staff-schedule-form-day-4-working]').click();
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-schedule-form]')).toBeHidden();
    await expect(row).not.toContainText('Fri');
    await page.screenshot({ path: shot('staff-schedules-desktop') });

    // Delete asks first.
    const scheduleId = psql(`select id from staff_schedule where member_id = '${created.data.id}'`);
    await rowAction(page, 'staff-schedules', scheduleId, 'delete');
    await expect(page.locator('ion-modal[data-testid=staff-schedule-delete]')).toContainText('Delete the schedule "Regular schedule"?');
    await page.locator('[data-testid=staff-schedule-delete-submit]').click();
    await expect(view.locator('[data-testid=staff-schedules-empty]')).toBeVisible();
  } finally {
    await context.close();
  }
});
