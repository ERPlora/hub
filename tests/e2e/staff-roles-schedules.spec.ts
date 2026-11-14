// Staff → Roles and Schedules in Chrome (WORKBOOK STAFF-F04, F13–F15). Roles: the owner creates a
// role (0 members), sees a duplicate name refused in the form (409), and retires it from «Edit»: it
// stays listed, marked «Retired». Schedules: for a member picked by searching the server, «+» proposes
// Monday to Friday with the default working day of Settings (as proposed: 09:00–18:00, break 13:00–14:00;
// STAFF-F22) and «Create schedule» lists it as the default one with its
// hours; a day ending before it starts is refused under that day (422), and its reason goes as soon as that
// day is changed, while another refused day keeps its own; editing drops Friday; «Delete» asks first and
// empties the list. Everything this spec creates is named «E2E …» and removed after it.
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, api, capture, psql, shot, shown } from './helpers';
import { signedIn } from './flow-helpers';
import { shoot } from './inventory-helpers';
import { staffCleanUp } from './staff-helpers';
import { rowAction } from './service-helpers';
import { discardChanges } from './unsaved-back-helpers';

const TAG = 'E2E';

const cleanup = (): void => staffCleanUp(TAG);

test.beforeAll(cleanup);
test.afterAll(cleanup);

/** The owner on `next` at a desk's size, in English. */
const ownerPage = (browser: Browser, next: string) => signedIn(browser, next, { width: 1280, height: 860 });

/** Picks the member called `name` in Schedules by searching the server for `search`. */
async function pickMember(page: Page, search: string, name: string): Promise<void> {
  const member = shown(page).locator('[data-testid=staff-schedules-member] input');
  await member.click();
  await member.fill(search);
  await page.locator('[data-testid^=staff-schedules-member-option-]', { hasText: name }).first().click();
}

/** The sizes the week of a schedule is read at: a small and a common phone, a tablet upright and a desk. */
const WEEK_SIZES = [
  { width: 375, height: 667 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 820, height: 1180 },
  { width: 1440, height: 900 },
] as const;

/** What is wrong with how the schedule window lays out each day's name: on more than one line, cut short, running
 *  under what follows it (its hours or «Off», which go beside the name or, without room, below it), or the days off
 *  not starting their «Off» at the same place (the names are one column, as wide as the longest). Empty when the
 *  week reads right. */
async function weekNamesProblems(page: Page): Promise<string[]> {
  return page.locator('ion-modal[data-testid=staff-schedule-form] .staff-week').evaluate((week) => {
    const problems = [...week.querySelectorAll('.staff-week__day')].flatMap((row) => {
      const box = row.querySelector('ion-checkbox') as HTMLElement;
      const name = (box.textContent ?? '').trim();
      const text = document.createRange();
      text.selectNodeContents(box);
      const lines = new Set([...text.getClientRects()].filter((rect) => rect.width > 0).map((rect) => Math.round(rect.top))).size;
      const label = box.shadowRoot?.querySelector('[part~="label"]') as HTMLElement;
      const whole = text.getBoundingClientRect();
      const next = row.querySelector('.staff-week__hours, .staff-week__sep')!.getBoundingClientRect();
      const found: string[] = [];
      if (lines !== 1) found.push(`«${name}» on ${lines} lines`);
      if (label.scrollWidth > label.clientWidth + 1) found.push(`«${name}» cut short`);
      if (next.left < whole.right - 1 && next.top < whole.bottom - 1) found.push(`«${name}» runs under what follows it`);
      return found;
    });
    const offs = new Set([...week.querySelectorAll('[data-testid$="-off"]')].map((off) => Math.round(off.getBoundingClientRect().left)));
    if (offs.size > 1) problems.push(`«Off» starts at ${[...offs].join(', ')} px, not in one column`);
    return problems;
  });
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
    // «Cancel» asks before losing what was typed (BASE-F05): the person discards it.
    await page.locator('[data-testid=staff-role-form-cancel]').click();
    await discardChanges(page);

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

test('Schedules: a week without working days is refused on top of it, and the line goes as soon as a day is ticked', async ({ browser }) => {
  // flow: STAFF-F13 (hub#1448)
  const stamp = Date.now().toString(36);
  const noDays = 'A schedule needs at least one working day with hours.';
  const { context, page } = await ownerPage(browser, '/staff/schedules');
  try {
    const created = await api<{ id: string; full_name: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG} Iris`, last_name: `Week${stamp}` });
    expect(created.status).toBe(201);
    const view = shown(page);
    await pickMember(page, `Week${stamp}`, created.data.full_name);
    await view.locator('[data-testid=staff-schedules-add]').click();
    for (const weekday of [0, 1, 2, 3, 4]) await page.locator(`[data-testid=staff-schedule-form-day-${weekday}-working]`).click();
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    const refused = page.locator('[data-testid=staff-schedule-form-week-error]');
    await expect(refused).toContainText(noDays);
    await shoot(page, 'APP-STAFF-STAFF-F13-week-refused', { width: 1280, height: 860 });
    await page.locator('[data-testid=staff-schedule-form-day-2-working]').click();
    await expect(refused).toBeHidden();
    await shoot(page, 'APP-STAFF-STAFF-F13-week-ticked', { width: 1280, height: 860 });
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-schedule-form]')).toBeHidden();
    await expect(view.locator('[data-testid=staff-schedules-row]').first()).toContainText('Wed 09:00–18:00 (13:00–14:00)');
  } finally {
    await context.close();
  }
});

test('Schedules: the default week, a day refused under its row and corrected on its own, edit, delete', async ({ browser }) => {
  // flow: STAFF-F13, STAFF-F14 (hub#1460)
  const stamp = Date.now().toString(36);
  const { context, page } = await ownerPage(browser, '/staff/schedules');
  try {
    const created = await api<{ id: string; full_name: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG} Sara`, last_name: `Shifts${stamp}` });
    expect(created.status).toBe(201);
    const name = created.data.full_name;
    const view = shown(page);

    await pickMember(page, `Shifts${stamp}`, name);
    await expect(view.locator('[data-testid=staff-schedules-member] input')).toHaveValue(name);
    await expect(view.locator('[data-testid=staff-schedules-empty]')).toContainText('This member has no schedules yet.');

    // «+»: Monday to Friday 09:00–18:00 with a break 13:00–14:00 (the working day of Settings as proposed);
    // a Monday and a Tuesday ending before they start are refused, each under its own day. Correcting one takes
    // its reason away before saving again, typing an hour or unticking it, and leaves the other's (hub#1460).
    await view.locator('[data-testid=staff-schedules-add]').click();
    await expect(page.locator('[data-testid=staff-schedule-form-day-5-off]')).toHaveText('Off');
    await page.locator('[data-testid=staff-schedule-form-day-0-end] input').fill('08:00');
    await page.locator('[data-testid=staff-schedule-form-day-1-end] input').fill('08:00');
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    const order = 'The start time must be before the end time.';
    const monday = page.locator('[data-testid=staff-schedule-form-day-0-error]');
    const tuesday = page.locator('[data-testid=staff-schedule-form-day-1-error]');
    await expect(monday).toContainText(order);
    await expect(tuesday).toContainText(order);
    await page.screenshot({ path: shot('staff-schedules-422') });
    await page.locator('[data-testid=staff-schedule-form-day-0-end] input').fill('18:00');
    await expect(monday).toBeHidden();
    await expect(tuesday).toContainText(order);
    await shoot(page, 'APP-STAFF-STAFF-F13-day-corrected', { width: 1280, height: 860 });
    const tuesdayWorks = page.locator('[data-testid=staff-schedule-form-day-1-working]');
    await tuesdayWorks.click();
    await expect(tuesday).toBeHidden();
    await tuesdayWorks.click();
    await page.locator('[data-testid=staff-schedule-form-day-1-end] input').fill('18:00');
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

for (const language of ['en', 'es'] as const) {
  test(`Schedules: in ${language}, every day's name reads whole on one line, worked or off, from a phone to a desk`, async ({ browser }) => {
    // flow: STAFF-F13, STAFF-F14 (hub#1461)
    const stamp = Date.now().toString(36);
    const { context, page } = await ownerPage(browser, '/staff/schedules');
    try {
      const created = await api<{ id: string; full_name: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG} Wanda`, last_name: `Days${stamp}` });
      expect(created.status).toBe(201);
      if (language === 'es') {
        await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
        await page.goto(`${A}/staff/schedules`);
      }
      await pickMember(page, `Days${stamp}`, created.data.full_name);
      await shown(page).locator('[data-testid=staff-schedules-add]').click();
      // Wednesday and Miércoles are the longest names: proposed, Monday to Friday work and the weekend is off;
      // then every day is ticked or unticked, so each name is read beside its hours and beside «Off».
      await expect(page.locator('[data-testid=staff-schedule-form-day-2-working]')).toHaveText(language === 'en' ? 'Wednesday' : 'Miércoles');
      for (const week of ['proposed', 'flipped'] as const) {
        if (week === 'flipped') {
          for (const weekday of [0, 1, 2, 3, 4, 5, 6]) await page.locator(`[data-testid=staff-schedule-form-day-${weekday}-working]`).click();
          await expect(page.locator('[data-testid=staff-schedule-form-day-2-off]')).toBeVisible();
          await expect(page.locator('[data-testid=staff-schedule-form-day-6-start]')).toBeVisible();
        }
        for (const size of WEEK_SIZES) {
          const where = `${week} week at ${size.width}x${size.height}`;
          await page.setViewportSize(size);
          await capture(page, `APP-STAFF-STAFF-F13-day-names-${language}-${week}-${size.width}x${size.height}`);
          expect.soft(await weekNamesProblems(page), where).toEqual([]);
        }
      }
    } finally {
      await context.close();
    }
  });
}
