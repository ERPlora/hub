// Every flow of Staff with a screen, one test each (its key in the title and in `// flow:`), done end to
// end on the real stack and seen at 390×844, 834×1112 and 1440×900: `threeShots` resizes, brings what the
// flow shows into sight, checks nothing scrolls sideways and saves `.artifacts/APP-STAFF-<key>-<width>.png`.
// The deeper cases of each flow live in the other staff-*.spec.ts and in the app's pytest and Vitest
// suites. STAFF-F07 (the batch add), F09 (the directory for other apps) and F16 (when a professional can
// work) have no screen of their own: their evidence is pytest and the e2e of the app that reads them.
// Everything created here is named «E2E…» and removed after the run (and before, if a run died half-way).
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, psql, shot, shown } from './helpers';

const TAG = 'E2E';
const VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

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

const stamp = (): string => Date.now().toString(36);
const day = (offset: number): string => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
const employeeUser = (): number => Number(psql(`select id from auth_user where email = '${EMPLOYEE.email}'`));

async function signedIn(browser: Browser, next: string, credentials?: Credentials): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, next, credentials);
  return { context, page };
}

/** How many pixels the shown page scrolls sideways (0 when everything fits its width). */
async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(async () => {
    const content = document.querySelector('ion-router-outlet > .ion-page:not(.ion-page-hidden) ion-content') as
      | (HTMLElement & { getScrollElement?: () => Promise<HTMLElement> })
      | null;
    const inner = content?.getScrollElement ? await content.getScrollElement() : null;
    const outer = document.documentElement.scrollWidth - window.innerWidth;
    const own = inner ? inner.scrollWidth - inner.clientWidth : 0;
    return Math.max(outer, own);
  });
}

/** At each of the three sizes: `target` in sight, no sideways scroll, and the screenshot. */
async function threeShots(page: Page, key: string, target: () => Locator): Promise<void> {
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    const seen = target();
    // A list turns its rows into cards on a phone: what was there is painted again, so it retries.
    await expect(async () => {
      await seen.scrollIntoViewIfNeeded({ timeout: 2000 });
      await expect(seen).toBeInViewport({ timeout: 1000 });
    }, `${key} at ${vp.label}`).toPass();
    await expect.poll(() => horizontalOverflow(page), `${key} at ${vp.label}: sideways scroll`).toBeLessThanOrEqual(1);
    await page.screenshot({ path: shot(`APP-STAFF-${key}-${vp.label}`) });
  }
}

/** A row (or, on a phone, a card) of a staff list by its id. */
const rowOf = (page: Page, table: string, id: string): Locator => shown(page).locator(`[data-testid=${table}-row][data-id="${id}"]`);

/** Clicks a row action, from its button or, when the box folded it, from the row's «⋮» menu. */
async function rowAction(page: Page, table: string, id: string, action: string): Promise<void> {
  await expect(rowOf(page, table, id)).toBeVisible();
  const button = shown(page).locator(`[data-testid=${table}-row-${id}-${action}]`);
  if (await button.isVisible()) {
    await button.click();
    return;
  }
  await shown(page).locator(`[data-testid=${table}-row-${id}-menu]`).click();
  await page.locator(`ion-popover [data-testid=${table}-row-${id}-${action}]`).click();
}

async function search(page: Page, table: string, text: string): Promise<void> {
  await shown(page).locator(`[data-testid=${table}-search] input`).fill(text);
}

interface Member {
  id: string;
  full_name: string;
}

async function member(context: BrowserContext, body: Record<string, unknown>): Promise<Member> {
  const res = await api<Member>(context, A, 'POST', '/staff/members', { first_name: `${TAG} Ana`, last_name: `Flow${stamp()}`, ...body });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data;
}

async function timeOff(context: BrowserContext, memberId: string, from: string, to: string, approve = false): Promise<string> {
  const res = await api<{ id: string }>(context, A, 'POST', '/staff/time_off', { member_id: memberId, start_date: from, end_date: to });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  if (approve) expect((await api(context, A, 'POST', '/staff/time_off/approve', { id: res.data.id })).status).toBe(200);
  return res.data.id;
}

/** Terminates a record: its account (if any) is free again for the next test. */
async function release(context: BrowserContext, id: string): Promise<void> {
  expect((await api(context, A, 'POST', '/staff/members/terminate', { id })).status).toBe(200);
}

async function pickMember(page: Page, field: string, text: string, name: string): Promise<void> {
  await page.locator(`[data-testid=${field}]`).click();
  await page.locator(`[data-testid=${field}-search] input`).fill(text);
  await page.locator(`[data-testid=${field}-option]`, { hasText: name }).click();
}

// flow: STAFF-F01 · gh:pm#478, gh:staff#72 — a refused save is told under its field and in sight, also on a phone
test('STAFF-F01: «+» adds a professional born Active; a refused email is told under its field at every width', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    const last = `New${stamp()}`;
    await shown(page).locator('[data-testid=staff-members-add]').click();
    const form = page.locator('ion-modal[data-testid=staff-member-form]');
    await expect(form.locator('ion-title')).toHaveText('New');
    await page.locator('[data-testid=staff-member-form-first_name] input').fill(`${TAG} Ana`);
    await page.locator('[data-testid=staff-member-form-last_name] input').fill(last);
    await page.locator('[data-testid=staff-member-form-email] input').fill('not-an-email@');
    await page.locator('[data-testid=staff-member-form-submit]').click();
    const email = page.locator('[data-testid=staff-member-form-email]');
    await expect(email).toHaveClass(/ion-invalid/);
    await threeShots(page, 'STAFF-F01', () => email);
    await page.locator('[data-testid=staff-member-form-email] input').fill('');
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(form).toBeHidden();
    await search(page, 'staff-members', last);
    await expect(shown(page).locator('[data-testid=staff-members-row]', { hasText: last })).toContainText('Active');
  } finally {
    await context.close();
  }
});

// flow: STAFF-F02 · gh:staff#38 — editing says «Edit · {name}», never «New»
test('STAFF-F02: a row opens «Edit · {name}» with the record; the saved change shows in the list', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    const ana = await member(context, { email: 'f02.before@example.com' });
    await search(page, 'staff-members', ana.full_name.split(' ').at(-1)!);
    await rowOf(page, 'staff-members', ana.id).getByText(ana.full_name).click();
    const form = page.locator('ion-modal[data-testid=staff-member-form]');
    await expect(form.locator('ion-title')).toHaveText(`Edit · ${ana.full_name}`);
    await expect(page.locator('[data-testid=staff-member-form-email] input')).toHaveValue('f02.before@example.com');
    await page.locator('[data-testid=staff-member-form-email] input').fill('f02.after@example.com');
    await threeShots(page, 'STAFF-F02', () => form.locator('ion-title'));
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(form).toBeHidden();
    await expect(rowOf(page, 'staff-members', ana.id)).toContainText('f02.after@example.com');
  } finally {
    await context.close();
  }
});

// flow: STAFF-F03 · gh:staff#10, gh:staff#55 — the record hangs from one account of this business
test('STAFF-F03: «Hub user» links the record to an account of the business, searched on the server', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    const bea = await member(context, { first_name: `${TAG} Bea` });
    await search(page, 'staff-members', bea.full_name.split(' ').at(-1)!);
    await rowOf(page, 'staff-members', bea.id).getByText(bea.full_name).click();
    await pickMember(page, 'staff-member-form-user_id', 'employee', 'employee@example.com');
    const picked = page.locator('[data-testid=staff-member-form-user_id]');
    await expect(picked.locator('input')).toHaveValue('employee@example.com');
    await threeShots(page, 'STAFF-F03', () => picked);
    await page.locator('[data-testid=staff-member-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-member-form]')).toBeHidden();
    await expect.poll(() => psql(`select user_id from staff_member where id = '${bea.id}'`)).toBe(String(employeeUser()));
    await release(context, bea.id);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F04 · gh:pm#254 — a retired role stays listed and marked
test('STAFF-F04: «+» in Roles creates a role that is listed with 0 members', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/roles');
  try {
    const name = `${TAG} Colourist ${stamp()}`;
    await shown(page).locator('[data-testid=staff-roles-add]').click();
    await page.locator('[data-testid=staff-role-form-name] input').fill(name);
    await page.locator('[data-testid=staff-role-form-description] input').fill('Colour specialist');
    await page.locator('[data-testid=staff-role-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-role-form]')).toBeHidden();
    await search(page, 'staff-roles', name);
    const row = shown(page).locator('[data-testid=staff-roles-row]', { hasText: name });
    await expect(row).toContainText('Colour specialist');
    await threeShots(page, 'STAFF-F04', () => row);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F05 · gh:hub#2162 — the confirmation is styled, in sight and takes the first tap
test('STAFF-F05: «Deactivate» asks first; confirmed, the row is Inactive', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    const ana = await member(context, {});
    await search(page, 'staff-members', ana.full_name.split(' ').at(-1)!);
    await rowAction(page, 'staff-members', ana.id, 'deactivate');
    const dialog = page.locator('ion-modal[data-testid=staff-member-deactivate]');
    await expect(dialog).toContainText(`Take ${ana.full_name} off the floor?`);
    const confirm = page.locator('[data-testid=staff-member-deactivate-submit]');
    await threeShots(page, 'STAFF-F05', () => confirm);
    await confirm.click();
    await expect(dialog).toBeHidden();
    await expect(rowOf(page, 'staff-members', ana.id)).toContainText('Inactive');
  } finally {
    await context.close();
  }
});

// flow: STAFF-F06 · gh:hub#2162 — the termination dialog is styled, in sight and takes the first tap
test('STAFF-F06: «Terminate» asks the last day and the reason; confirmed, the person leaves the list', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    const ana = await member(context, {});
    await search(page, 'staff-members', ana.full_name.split(' ').at(-1)!);
    await rowAction(page, 'staff-members', ana.id, 'terminate');
    await page.locator('[data-testid=staff-member-terminate-reason] textarea').fill('Moves abroad');
    const confirm = page.locator('[data-testid=staff-member-terminate-submit]');
    await threeShots(page, 'STAFF-F06', () => confirm);
    await confirm.click();
    await expect(page.locator('ion-modal[data-testid=staff-member-terminate]')).toBeHidden();
    await expect(rowOf(page, 'staff-members', ana.id)).toHaveCount(0);
    expect(psql(`select status || '|' || termination_reason from staff_member where id = '${ana.id}'`)).toBe('terminated|Moves abroad');
  } finally {
    await context.close();
  }
});

// flow: STAFF-F08 · gh:staff#19 — the employee has a door to their own record and their own time off
test('STAFF-F08: «My record» shows the employee their own record with their own rate', async ({ browser }) => {
  const owner = await signedIn(browser, '/staff/members');
  const mine = await member(owner.context, { first_name: `${TAG} Eva`, user_id: employeeUser(), hourly_rate: 1450 });
  await owner.context.close();
  const { context, page } = await signedIn(browser, '/staff/members', EMPLOYEE);
  try {
    await shown(page).locator('[data-testid=staff-members-mine]').click();
    const record = page.locator('[data-testid=staff-my-record-fields]');
    await expect(record).toContainText(mine.full_name);
    await expect(record).toContainText(/14[.,]50/);
    await threeShots(page, 'STAFF-F08', () => record);
    await page.locator('[data-testid=staff-my-record-done]').click();
  } finally {
    await context.close();
    const admin = await signedIn(browser, '/staff/members');
    await release(admin.context, mine.id);
    await admin.context.close();
  }
});

async function openSchedules(page: Page, who: Member): Promise<void> {
  await pickMember(page, 'staff-schedules-member', who.full_name.split(' ').at(-1)!, who.full_name);
  await expect(shown(page).locator('[data-testid=staff-schedules-member] input')).toHaveValue(who.full_name);
}

// flow: STAFF-F13 · gh:staff#86 — the week reads in 24 h
test('STAFF-F13: «+» in Schedules creates the proposed week, Monday to Friday 09:00–18:00', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/schedules');
  try {
    const sara = await member(context, { first_name: `${TAG} Sara` });
    await openSchedules(page, sara);
    await shown(page).locator('[data-testid=staff-schedules-add]').click();
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-schedule-form]')).toBeHidden();
    const row = shown(page).locator('[data-testid=staff-schedules-row]').first();
    await expect(row).toContainText('Mon 09:00–18:00 · Tue 09:00–18:00 · Wed 09:00–18:00 · Thu 09:00–18:00 · Fri 09:00–18:00');
    await threeShots(page, 'STAFF-F13', () => row);
  } finally {
    await context.close();
  }
});

async function scheduleFor(context: BrowserContext, who: Member): Promise<string> {
  const week = [0, 1, 2, 3, 4].map((weekday) => ({ weekday, start_time: '09:00', end_time: '18:00' }));
  const res = await api<{ id: string }>(context, A, 'POST', '/staff/schedules', { member_id: who.id, is_default: true, days: week });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data.id;
}

// flow: STAFF-F14
test('STAFF-F14: a schedule row opens its week; a day switched off is «Off» once saved', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/schedules');
  try {
    const sara = await member(context, { first_name: `${TAG} Sara` });
    const id = await scheduleFor(context, sara);
    await openSchedules(page, sara);
    const row = rowOf(page, 'staff-schedules', id);
    await row.getByText('Regular schedule').click();
    await page.locator('[data-testid=staff-schedule-form-day-4-working]').click();
    await page.locator('[data-testid=staff-schedule-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-schedule-form]')).toBeHidden();
    await expect(row).not.toContainText('Fri');
    await threeShots(page, 'STAFF-F14', () => row);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F15 · gh:hub#2162 — deleting asks in a styled dialog that takes the first tap
test('STAFF-F15: «Activate / deactivate» switches a schedule at once; «Delete» asks first', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/schedules');
  try {
    const sara = await member(context, { first_name: `${TAG} Sara` });
    const id = await scheduleFor(context, sara);
    await openSchedules(page, sara);
    await rowAction(page, 'staff-schedules', id, 'toggle');
    await expect.poll(() => psql(`select is_active from staff_schedule where id = '${id}'`)).toBe('f');
    await rowAction(page, 'staff-schedules', id, 'delete');
    const dialog = page.locator('ion-modal[data-testid=staff-schedule-delete]');
    await expect(dialog).toContainText('Delete the schedule "Regular schedule"?');
    const confirm = page.locator('[data-testid=staff-schedule-delete-submit]');
    await threeShots(page, 'STAFF-F15', () => confirm);
    await confirm.click();
    await expect(shown(page).locator('[data-testid=staff-schedules-empty]')).toBeVisible();
  } finally {
    await context.close();
  }
});

// flow: STAFF-F17 · gh:staff#36, gh:staff#37 — time off is registered from the screen, its words translated
test('STAFF-F17: «+» in Time Off registers someone’s absence, Pending', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/time-off');
  try {
    const ana = await member(context, {});
    await shown(page).locator('[data-testid=staff-time-off-add]').click();
    await pickMember(page, 'staff-time-off-form-member_id', ana.full_name.split(' ').at(-1)!, ana.full_name);
    await page.locator('[data-testid=staff-time-off-form-start_date] input').fill(day(40));
    await page.locator('[data-testid=staff-time-off-form-end_date] input').fill(day(42));
    await page.locator('[data-testid=staff-time-off-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-time-off-form]')).toBeHidden();
    await search(page, 'staff-time-off', ana.full_name.split(' ').at(-1)!);
    const row = shown(page).locator('[data-testid=staff-time-off-row]', { hasText: ana.full_name });
    await expect(row).toContainText('Pending');
    await threeShots(page, 'STAFF-F17', () => row);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F18
test('STAFF-F18: «Approve» on a pending request turns its row Approved', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/time-off');
  try {
    const ana = await member(context, {});
    const id = await timeOff(context, ana.id, day(50), day(51));
    await search(page, 'staff-time-off', ana.full_name.split(' ').at(-1)!);
    await rowAction(page, 'staff-time-off', id, 'approve');
    const row = rowOf(page, 'staff-time-off', id);
    await expect(row).toContainText('Approved');
    await threeShots(page, 'STAFF-F18', () => row);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F19 · gh:pm#629 — an approved absence can be cancelled, after a confirmation
test('STAFF-F19: «Cancel» on an approved absence asks first; confirmed, it is Cancelled', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/time-off');
  try {
    const ana = await member(context, {});
    const id = await timeOff(context, ana.id, day(60), day(61), true);
    await search(page, 'staff-time-off', ana.full_name.split(' ').at(-1)!);
    await rowAction(page, 'staff-time-off', id, 'cancel');
    const confirm = page.locator('[data-testid=staff-time-off-cancel-submit]');
    await expect(page.locator('ion-modal[data-testid=staff-time-off-cancel]')).toContainText(ana.full_name);
    await threeShots(page, 'STAFF-F19', () => confirm);
    await confirm.click();
    await expect(rowOf(page, 'staff-time-off', id)).toContainText('Cancelled');
  } finally {
    await context.close();
  }
});

// flow: STAFF-F20, STAFF-G05 · gh:staff#58 — «today» is the business's day
test('STAFF-F20 and G05: «Today’s time off» above Time Off lists who is away today, live', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/time-off');
  try {
    const card = shown(page).locator('[data-testid=staff-away-today]');
    await expect(card.locator('h2')).toHaveText('Today’s time off');
    const ana = await member(context, { first_name: `${TAG} Away` });
    await timeOff(context, ana.id, day(-1), day(1), true);
    const row = card.locator('[data-testid=staff-away-today-row]', { hasText: ana.full_name });
    await expect(row).toContainText('Vacation · All day');
    await threeShots(page, 'STAFF-F20', () => card);
    await threeShots(page, 'STAFF-G05', () => row);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F21 · gh:staff#64 — the rate is whole cents, painted as money
test('STAFF-F21: the owner sees each professional’s rate in «Rate/h»', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    const ana = await member(context, { hourly_rate: 1825, commission_rate: '12.5' });
    await expect(shown(page).locator('[role=columnheader]', { hasText: 'Rate/h' })).toBeVisible();
    await search(page, 'staff-members', ana.full_name.split(' ').at(-1)!);
    const row = rowOf(page, 'staff-members', ana.id);
    await expect(row).toContainText(/18[.,]25/);
    await threeShots(page, 'STAFF-F21', () => row);
    const sheet = await api<{ rows: { id: string; commission_rate: string }[] }>(context, A, 'GET', `/staff/commissions?search=${encodeURIComponent(ana.full_name)}`);
    expect(sheet.data.rows.find((r) => r.id === ana.id)?.commission_rate).toBe('12.50');
  } finally {
    await context.close();
  }
});

// flow: STAFF-F22 · gh:hub#2541 — a read that fails offers «Retry», never values to save (Vitest)
test('STAFF-F22: Settings saves only what changed and says it is saved', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/settings');
  const before = await api<{ max_daily_hours: number }>(context, A, 'GET', '/staff/settings');
  try {
    const next = String(before.data.max_daily_hours === 11 ? 10 : 11);
    await shown(page).locator('[data-testid=staff-settings-max_daily_hours] input').fill(next);
    await shown(page).locator('[data-testid=staff-settings-save]').click();
    const saved = shown(page).locator('[data-testid=staff-settings-saved]');
    await expect(saved).toBeVisible();
    expect((await api<{ max_daily_hours: number }>(context, A, 'GET', '/staff/settings')).data.max_daily_hours).toBe(Number(next));
    await threeShots(page, 'STAFF-F22', () => saved);
  } finally {
    expect((await api(context, A, 'POST', '/staff/settings', { max_daily_hours: before.data.max_daily_hours })).status).toBe(200);
    await context.close();
  }
});

/** The value a figure above the staff list shows. */
const figure = (page: Page, id: string): Locator => shown(page).locator(`[data-testid=staff-figures-${id}] .staff-figure__value`);

// flow: STAFF-F23, STAFF-G02, STAFF-G03, STAFF-G04
test('STAFF-F23 and G02–G04: the figures above Staff follow a new person, an absence and a request live', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/members');
  try {
    await expect(figure(page, 'active')).toHaveText(/^\d+$/);
    const before = Number(await figure(page, 'active').textContent());
    const away = Number(await figure(page, 'away').textContent());
    const pending = Number(await figure(page, 'pending').textContent());
    const ana = await member(context, {});
    await expect(figure(page, 'active')).toHaveText(String(before + 1));
    await timeOff(context, ana.id, day(-1), day(1), true);
    await expect(figure(page, 'away')).toHaveText(String(away + 1));
    await timeOff(context, ana.id, day(70), day(71));
    await expect(figure(page, 'pending')).toHaveText(String(pending + 1));
    const figures = shown(page).locator('[data-testid=staff-figures]');
    // On a phone the three go on one line, so the list still shows below them.
    await page.setViewportSize({ width: 390, height: 844 });
    const tops = async () =>
      Promise.all(['active', 'away', 'pending'].map(async (id) => Math.round((await shown(page).locator(`[data-testid=staff-figures-${id}]`).boundingBox())?.y ?? -1)));
    await expect.poll(async () => new Set(await tops()).size, 'the figures share one line at 390').toBe(1);
    await threeShots(page, 'STAFF-F23', () => figures);
    await threeShots(page, 'STAFF-G02', () => shown(page).locator('[data-testid=staff-figures-active]'));
    await threeShots(page, 'STAFF-G03', () => shown(page).locator('[data-testid=staff-figures-away]'));
    await threeShots(page, 'STAFF-G04', () => shown(page).locator('[data-testid=staff-figures-pending]'));
  } finally {
    await context.close();
  }
});

// flow: STAFF-G01
test('STAFF-G01: «Members» in Roles counts the Active people of each role', async ({ browser }) => {
  const { context, page } = await signedIn(browser, '/staff/roles');
  try {
    const role = await api<{ id: string; name: string }>(context, A, 'POST', '/staff/roles', { name: `${TAG} Barber ${stamp()}` });
    expect(role.status).toBe(201);
    await member(context, { role_id: role.data.id });
    await member(context, { role_id: role.data.id, first_name: `${TAG} Bea` });
    await search(page, 'staff-roles', role.data.name);
    const row = rowOf(page, 'staff-roles', role.data.id);
    await expect(row).toContainText('2');
    await threeShots(page, 'STAFF-G01', () => row);
  } finally {
    await context.close();
  }
});

// flow: STAFF-F24 · gh:staff#3 — the employee asks; the request waits for an answer
test('STAFF-F24: the employee asks for their own time off from «+», without choosing a member', async ({ browser }) => {
  const owner = await signedIn(browser, '/staff/members');
  const mine = await member(owner.context, { first_name: `${TAG} Eva`, user_id: employeeUser() });
  await owner.context.close();
  const { context, page } = await signedIn(browser, '/staff/time-off', EMPLOYEE);
  try {
    await shown(page).locator('[data-testid=staff-time-off-add]').click();
    await expect(page.locator('ion-modal[data-testid=staff-time-off-form] ion-title')).toHaveText('Request time off');
    await expect(page.locator('[data-testid=staff-time-off-form-member_id]')).toHaveCount(0);
    await page.locator('[data-testid=staff-time-off-form-start_date] input').fill(day(80));
    await page.locator('[data-testid=staff-time-off-form-end_date] input').fill(day(81));
    await page.locator('[data-testid=staff-time-off-form-submit]').click();
    await expect(page.locator('ion-modal[data-testid=staff-time-off-form]')).toBeHidden();
    await search(page, 'staff-time-off', mine.full_name.split(' ').at(-1)!);
    const row = shown(page).locator('[data-testid=staff-time-off-row]', { hasText: mine.full_name });
    await expect(row).toContainText('Pending');
    await threeShots(page, 'STAFF-F24', () => row);
  } finally {
    await context.close();
    psql(`delete from staff_timeoff where member_id = '${mine.id}'`);
    const admin = await signedIn(browser, '/staff/members');
    await release(admin.context, mine.id);
    await admin.context.close();
  }
});
