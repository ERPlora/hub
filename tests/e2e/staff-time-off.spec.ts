// Staff → Time Off in Chrome (WORKBOOK STAFF-F08, F17–F19, F24): the employee, whose account hangs a
// staff record, asks for time off (the form does not ask who); the owner, with Time Off open in another
// browser, sees the request arrive Pending without reloading and approves it; the employee sees it turn
// Approved, also without reloading. Asking again for the same days is refused with the overlap (409)
// inside the form. «My time off» shows the employee's own requests with their reason. Everything this
// spec creates is named «E2E …» and removed after it.
import { type Browser, type BrowserContext, expect, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, psql, shot, shown } from './helpers';

const TAG = 'E2E';

/** The employee's user id on this database (never a fixed number: it depends on the seed). */
const employeeUser = (): number => Number(psql(`select id from auth_user where email = '${EMPLOYEE.email}'`));

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

async function signedIn(browser: Browser, next: string, credentials?: Credentials): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1280, height: 860 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

const rowOf = (page: Page, text: string) => shown(page).locator('[data-testid=staff-time-off-row]', { hasText: text });

/** Clicks a row action, from its button or from the row's «⋮» menu when the box folded it. */
async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=staff-time-off-row-${id}-${action}]`);
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await shown(page).locator(`[data-testid=staff-time-off-row-${id}-menu]`).click();
  await page.locator(`ion-popover [data-testid=staff-time-off-row-${id}-${action}]`).click();
}

async function requestDays(page: Page, from: string, to: string, reason: string): Promise<void> {
  await shown(page).locator('[data-testid=staff-time-off-add]').click();
  await expect(page.locator('ion-modal[data-testid=staff-time-off-form] ion-title')).toHaveText('Request time off');
  await expect(page.locator('[data-testid=staff-time-off-form-member_id]')).toHaveCount(0);
  await page.locator('[data-testid=staff-time-off-form-start_date] input').fill(from);
  await page.locator('[data-testid=staff-time-off-form-end_date] input').fill(to);
  await page.locator('[data-testid=staff-time-off-form-reason] textarea').fill(reason);
  await page.locator('[data-testid=staff-time-off-form-submit]').click();
}

test('the employee asks, the owner approves live, an overlap is refused in the form, «My time off» has the reason', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const name = `${TAG} Emma Employee${stamp}`;
  const owner = await signedIn(browser, '/staff/time-off');
  const employee = await signedIn(browser, '/staff/time-off', EMPLOYEE);
  try {
    // The employee's account hangs a staff record (STAFF-F03), made by the owner.
    const created = await api<{ id: string }>(owner.context, A, 'POST', '/staff/members', {
      first_name: `${TAG} Emma`,
      last_name: `Employee${stamp}`,
      user_id: employeeUser(),
    });
    expect(created.status).toBe(201);
    const memberId = created.data.id;

    // Both lists are open and painted before anything happens.
    for (const { page } of [owner, employee]) {
      await shown(page).locator('[data-testid=staff-time-off-empty], [data-testid=staff-time-off-row]').first().waitFor({ state: 'visible' });
    }

    // STAFF-F24: the employee asks for their own time off.
    await requestDays(employee.page, '2027-03-01', '2027-03-05', 'Family wedding');
    await expect(employee.page.locator('ion-modal[data-testid=staff-time-off-form]')).toBeHidden();
    await expect(rowOf(employee.page, name)).toContainText('Pending');

    // The owner sees it arrive without reloading, and approves it (STAFF-F18).
    await expect(rowOf(owner.page, name)).toContainText('Pending');
    const timeOffId = psql(`select id from staff_timeoff where member_id = '${memberId}'`);
    await owner.page.screenshot({ path: shot('staff-time-off-owner-pending') });
    await rowAction(owner.page, timeOffId, 'approve');
    await expect(rowOf(owner.page, name)).toContainText('Approved');

    // …and the employee sees it Approved, still without reloading.
    await expect(rowOf(employee.page, name)).toContainText('Approved');
    await employee.page.screenshot({ path: shot('staff-time-off-employee-approved') });

    // An overlap is refused inside the form, with the server's words (409).
    await requestDays(employee.page, '2027-03-03', '2027-03-04', 'Again');
    await expect(employee.page.locator('[data-testid=staff-time-off-form-error]')).toContainText('already has pending or approved time off');
    await employee.page.screenshot({ path: shot('staff-time-off-overlap') });
    await employee.page.locator('[data-testid=staff-time-off-form-cancel]').click();

    // STAFF-F08: «My time off» lists one's own, with its reason.
    await shown(employee.page).locator('[data-testid=staff-time-off-whose]').click();
    await employee.page.locator('ion-popover ion-item', { hasText: 'My time off' }).click();
    await expect(rowOf(employee.page, 'Family wedding')).toBeVisible();
    await employee.page.screenshot({ path: shot('staff-time-off-mine') });

    // The employee may not approve: no such action on any row.
    await expect(shown(employee.page).locator(`[data-testid=staff-time-off-row-${timeOffId}-approve]`)).toHaveCount(0);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});
