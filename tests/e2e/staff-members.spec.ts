// Staff → Staff in Chrome (WORKBOOK STAFF-F01–F06, F21): the owner adds a professional without a Hub
// user and another one linked to the employee's account (picked in «Hub user», searched on the
// server), sees an invalid email refused under its field (422), edits a record, deactivates one
// (confirmed) and terminates the other with a reason; the list follows every change without reloading.
// The pay column «Rate/h» is the owner's. On a phone (390×844) the list is cards. Everything this spec
// creates is named «E2E …» and removed after it (and before, if a run died half-way).
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shot, shown } from './helpers';

const TAG = 'E2E';
const PHONE = { width: 390, height: 844 };

/** Removes every record this spec family creates (first names «E2E…», roles «E2E…»). */
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

/** The owner signed in on `a`, in English (the language follows the browser's Accept-Language). */
async function ownerPage(browser: Browser, next: string, viewport = { width: 1280, height: 860 }) {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next);
  return { context, page };
}

/** A row of the Staff list by the person's name. */
const rowOf = (page: Page, name: string) => shown(page).locator('[data-testid=staff-members-row]', { hasText: name });

/** Clicks a row action, from its button or, when the box folded it, from the row's «⋮» menu. */
async function rowAction(page: Page, id: string, action: string): Promise<void> {
  const button = shown(page).locator(`[data-testid=staff-members-row-${id}-${action}]`);
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await shown(page).locator(`[data-testid=staff-members-row-${id}-menu]`).click();
  await page.locator(`ion-popover [data-testid=staff-members-row-${id}-${action}]`).click();
}

async function fillNew(page: Page, first: string, last: string): Promise<void> {
  await shown(page).locator('[data-testid=staff-members-add]').click();
  await expect(page.locator('ion-modal[data-testid=staff-member-form] ion-title')).toHaveText('New');
  await page.locator('[data-testid=staff-member-form-first_name] input').fill(first);
  await page.locator('[data-testid=staff-member-form-last_name] input').fill(last);
}

async function memberId(context: Parameters<typeof api>[0], name: string): Promise<string> {
  const res = await api<{ rows: { id: string; full_name: string }[] }>(context, A, 'GET', `/staff/members?search=${encodeURIComponent(name)}`);
  const row = res.data.rows.find((r) => r.full_name === name);
  expect(row, name).toBeTruthy();
  return row!.id;
}

test('the owner adds, links, edits, deactivates and terminates staff, live, with the 422 under its field', async ({ browser }) => {
  const stamp = Date.now().toString(36);
  const alone = { first: `${TAG} Ana`, last: `Solo ${stamp}` };
  const linked = { first: `${TAG} Bea`, last: `Linked ${stamp}` };
  const aloneName = `${alone.first} ${alone.last}`;
  const linkedName = `${linked.first} ${linked.last}`;
  const { context, page } = await ownerPage(browser, '/staff/members');
  try {
    const view = shown(page);
    await view.locator('[data-testid=staff-members-empty], [data-testid=staff-members-row]').first().waitFor({ state: 'visible' });
    // STAFF-F01: without a Hub user; an invalid email is refused under its field and nothing is lost.
    await fillNew(page, alone.first, alone.last);
    await expect(page.locator('[data-testid=staff-member-form-hub-user-hint]')).toBeVisible();
    await page.locator('[data-testid=staff-member-form-email] input').fill('not-an-email@');
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(page.locator('[data-testid=staff-member-form-email]')).toHaveClass(/ion-invalid/);
    await expect(page.locator('[data-testid=staff-member-form-email]').getByText('Enter a valid email address.')).toBeVisible();
    await expect(page.locator('[data-testid=staff-member-form-first_name] input')).toHaveValue(alone.first);
    await page.screenshot({ path: shot('staff-members-422') });
    await page.locator('[data-testid=staff-member-form-email] input').fill('ana.e2e@example.com');
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-member-form]')).toBeHidden();
    await expect(rowOf(page, aloneName)).toBeVisible();
    await expect(rowOf(page, aloneName)).toContainText('Active');
    // The pay column is the owner's.
    await expect(view.locator('[role=columnheader]', { hasText: 'Rate/h' })).toBeVisible();

    // STAFF-F03: linked to the employee's account, picked by searching the server.
    await fillNew(page, linked.first, linked.last);
    await page.locator('[data-testid=staff-member-form-user_id]').click();
    await page.locator('[data-testid=staff-member-form-user_id-search] input').fill('employee');
    await page.locator('[data-testid=staff-member-form-user_id-option]', { hasText: 'employee@example.com' }).click();
    await expect(page.locator('[data-testid=staff-member-form-user_id] input')).toHaveValue('employee@example.com');
    await expect(page.locator('[data-testid=staff-member-form-hub-user-hint]')).toHaveCount(0);
    await page.locator('[data-testid=staff-member-form-hourly_rate] input').fill('12,50');
    await page.screenshot({ path: shot('staff-members-new-linked') });
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(rowOf(page, linkedName)).toBeVisible();
    await expect(rowOf(page, linkedName)).toContainText(/12[.,]50/);
    const linkedId = await memberId(context, linkedName);
    expect(psql(`select user_id from staff_member where id = '${linkedId}'`)).toBe(psql(`select id from auth_user where email = '${EMPLOYEE.email}'`));

    // STAFF-F02: a row opens «Edit · {name}»; only what changed is saved.
    await rowOf(page, aloneName).getByText(aloneName).click();
    await expect(page.locator('ion-modal[data-testid=staff-member-form] ion-title')).toHaveText(`Edit · ${aloneName}`);
    await expect(page.locator('[data-testid=staff-member-form-email] input')).toHaveValue('ana.e2e@example.com');
    await page.locator('[data-testid=staff-member-form-email] input').fill('ana.changed@example.com');
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(rowOf(page, aloneName)).toContainText('ana.changed@example.com');

    // STAFF-F05: «Deactivate» asks first; the row turns Inactive by itself.
    const aloneId = await memberId(context, aloneName);
    await rowAction(page, aloneId, 'deactivate');
    await expect(page.locator('ion-modal[data-testid=staff-member-deactivate]')).toContainText(`Take ${aloneName} off the floor?`);
    await page.screenshot({ path: shot('staff-members-deactivate') });
    await page.locator('[data-testid=staff-member-deactivate-submit]').click();
    await expect(rowOf(page, aloneName)).toContainText('Inactive');

    // STAFF-F06: «Terminate» with a reason; the person leaves the list; the reason is kept.
    await rowAction(page, aloneId, 'terminate');
    await page.locator('[data-testid=staff-member-terminate-reason] textarea').fill('Moves abroad');
    await page.screenshot({ path: shot('staff-members-terminate') });
    await page.locator('[data-testid=staff-member-terminate-submit]').click();
    await expect(rowOf(page, aloneName)).toHaveCount(0);
    expect(psql(`select status || '|' || termination_reason from staff_member where id = '${aloneId}'`)).toBe('terminated|Moves abroad');
    await page.screenshot({ path: shot('staff-members-desktop') });
  } finally {
    await context.close();
  }
});

test('on a phone (390×844) Staff is cards, with the same actions', async ({ browser }) => {
  const { context, page } = await ownerPage(browser, '/staff/members', PHONE);
  try {
    const name = `${TAG} Cara Phone${Date.now().toString(36)}`;
    const res = await api(context, A, 'POST', '/staff/members', { first_name: `${TAG} Cara`, last_name: name.split(' ').at(-1) });
    expect(res.status).toBe(201);
    const card = rowOf(page, name);
    await expect(card).toBeVisible();
    await expect(card).toHaveClass(/data-table__card/);
    await expect(shown(page).locator('ion-footer ion-segment')).toBeVisible();
    await page.screenshot({ path: shot('staff-members-phone') });
  } finally {
    await context.close();
  }
});
