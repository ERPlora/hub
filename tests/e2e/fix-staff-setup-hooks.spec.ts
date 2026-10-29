// flow: STAFF-F20 STAFF-F23
// Staff's panels of the Home (FIX-STAFF-SETUP-HOOKS; the old module's `widgets`, the old hub's dashboard in
// docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads them in Spanish: «Plantilla activa», «Ausentes
// hoy» and «Ausencias de hoy» on the board by default with the figures and the list the server gives, which follow a
// new record and an approved time off of today without a reload; «Ausencias pendientes» and «Empleados por rol» to add
// from «Personalizar panel», grouped under «Personal», with the server's figure and a bar per role; and the employee,
// who sees the team and the time off (STAFF-F20 is everyone's), reads the same panels. Captures
// `FIX-STAFF-SETUP-HOOKS-<width>` (the board), `…-STAFF-F20-<width>` (who is away) and `…-STAFF-F23-<width>` (the
// figures and the roles). Everything this file creates is named «E2E-HOOKS …» and removed after it; it parks nothing.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, horizontalOverflow, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';
import { stamp } from './sale-helpers';

const KEY = 'FIX-STAFF-SETUP-HOOKS';
const TAG = 'E2E-HOOKS';
const HEADCOUNT = 'staff.headcount';
const ON_LEAVE = 'staff.on_leave_today';
const PENDING = 'staff.pending_time_off';
const AWAY = 'staff.time_off_today';
const BY_ROLE = 'staff.by_role';
const ALL = [HEADCOUNT, ON_LEAVE, PENDING, AWAY, BY_ROLE];
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';
const RUN = stamp();
const count = new Intl.NumberFormat('es-ES');

interface Stats {
  active: number;
  absent_today: number;
  pending_time_off: number;
}
interface Away {
  member_name: string;
  leave_type_label: string;
}
interface RoleRow {
  name: string;
  member_count: number;
}

test.describe.configure({ mode: 'serial' });

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

/** A civil day `days` away from this machine's today; ±1 covers the business's today whatever its time zone. */
function day(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

async function created<T>(context: BrowserContext, path: string, body: unknown): Promise<T> {
  const res = await api<T>(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBe(201);
  return res.data;
}

async function member(context: BrowserContext, first: string, body: Record<string, unknown> = {}): Promise<string> {
  return (await created<{ id: string }>(context, '/staff/members', { first_name: `${TAG} ${first}`, last_name: RUN, ...body })).id;
}

/** Time off from yesterday to tomorrow (today, in the business's day); approved unless said otherwise. */
async function timeOff(context: BrowserContext, memberId: string, leaveType: string, approved = true): Promise<void> {
  const row = await created<{ id: string }>(context, '/staff/time_off', {
    member_id: memberId,
    start_date: day(-1),
    end_date: day(1),
    leave_type: leaveType,
  });
  if (approved) expect((await api(context, A, 'POST', '/staff/time_off/approve', { id: row.id })).status).toBe(200);
}

test.beforeAll(async ({ browser }) => {
  cleanup();
  // A role with two people (one away today), another with one, and a request waiting for an answer.
  const context = await browser.newContext({ baseURL: A });
  try {
    const page = await context.newPage();
    await login(page, A, '/staff/members');
    const stylist = (await created<{ id: string }>(context, '/staff/roles', { name: `${TAG} ${RUN} Estilista` })).id;
    const reception = (await created<{ id: string }>(context, '/staff/roles', { name: `${TAG} ${RUN} Recepción` })).id;
    const ana = await member(context, 'Ana', { role_id: stylist });
    await member(context, 'Bea', { role_id: stylist });
    const carla = await member(context, 'Carla', { role_id: reception });
    await timeOff(context, ana, 'sick');
    await timeOff(context, carla, 'personal', false);
  } finally {
    await context.close();
  }
});

test.afterAll(cleanup);

/** A person of `a` in Spanish (the Hub's language cookie, as the sign-in sets it from the account), on the Home. */
async function spanish(
  browser: Browser,
  viewport: { width: number; height: number },
  options: { board?: string[]; who?: Credentials } = {},
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: A, viewport, locale: 'es-ES' });
  const { board } = options;
  if (board) await context.addInitScript(([key, keys]) => localStorage.setItem(key, keys), [BOARD, JSON.stringify(board)]);
  const page = await context.newPage();
  await login(page, A, '/', options.who ?? OWNER);
  await context.addCookies([{ name: 'django_language', value: 'es', domain: new URL(A).hostname, path: '/' }]);
  await page.goto(`${A}/`);
  await expect(page.locator('html')).toHaveAttribute('lang', /^es/);
  await expect(shown(page).locator('[data-testid="widget-board"]')).toBeVisible();
  // The owner's Spanish session with the five panels for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
  if (board && !options.who && process.env.E2E_SAVE_STORAGE_STATE) {
    await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  }
  return { context, page };
}

const panel = (page: Page, key: string): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);
const value = (page: Page, key: string): Locator => panel(page, key).locator('[data-testid="widget-value"]');

async function stats(context: BrowserContext): Promise<Stats> {
  const res = await api<Stats>(context, A, 'GET', '/staff/members/stats');
  expect(res.status).toBe(200);
  return res.data;
}

async function awayToday(context: BrowserContext): Promise<Away[]> {
  const res = await api<{ rows: Away[] }>(context, A, 'GET', '/staff/time_off/today');
  expect(res.status).toBe(200);
  return res.data.rows;
}

async function byRole(context: BrowserContext): Promise<RoleRow[]> {
  const res = await api<{ rows: RoleRow[] }>(context, A, 'GET', '/staff/roles?sort=-member_count&limit=10');
  expect(res.status).toBe(200);
  return res.data.rows;
}

/** «Ausencias de hoy» paints the server's list: each name with its type under it, in Spanish. */
async function expectAway(page: Page, context: BrowserContext): Promise<void> {
  const rows = await awayToday(context);
  const entries = panel(page, AWAY).locator('[data-testid="widget-entry"]');
  await expect(entries.locator('strong')).toHaveText(rows.map((row) => row.member_name));
  await expect(entries.locator('.widget-muted')).toHaveText(rows.map((row) => row.leave_type_label));
}

test('STAFF-F20 STAFF-F23: «Plantilla activa», «Ausentes hoy» and «Ausencias de hoy» by default with the server\'s figures, live', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    await expect(panel(page, HEADCOUNT).locator('[data-testid="widget-title"]')).toHaveText('Plantilla activa');
    await expect(panel(page, ON_LEAVE).locator('[data-testid="widget-title"]')).toHaveText('Ausentes hoy');
    await expect(panel(page, AWAY).locator('[data-testid="widget-title"]')).toHaveText('Ausencias de hoy');
    await expect(panel(page, PENDING)).toHaveCount(0);
    await expect(panel(page, BY_ROLE)).toHaveCount(0);
    const before = await stats(context);
    expect(before.active).toBeGreaterThanOrEqual(3);
    expect(before.absent_today).toBeGreaterThanOrEqual(1);
    await expect(value(page, HEADCOUNT)).toHaveText(count.format(before.active));
    await expect(value(page, ON_LEAVE)).toHaveText(count.format(before.absent_today));
    await expectAway(page, context);
    expect((await awayToday(context)).find((row) => row.member_name === `${TAG} Ana ${RUN}`)?.leave_type_label).toBe('Baja por enfermedad');

    // A new record (by the API, as the assistant would): the head count follows without a reload.
    const dora = await member(context, 'Dora');
    expect((await stats(context)).active).toBe(before.active + 1);
    await expect(value(page, HEADCOUNT)).toHaveText(count.format(before.active + 1));

    // Her vacation of today, approved: «Ausentes hoy» and «Ausencias de hoy» follow too.
    await timeOff(context, dora, 'vacation');
    expect((await stats(context)).absent_today).toBe(before.absent_today + 1);
    await expect(value(page, ON_LEAVE)).toHaveText(count.format(before.absent_today + 1));
    await expect(panel(page, AWAY).locator('[data-testid="widget-entry"]', { hasText: `${TAG} Dora ${RUN}` })).toContainText('Vacaciones');
    await expectAway(page, context);
  } finally {
    await context.close();
  }
});

test('STAFF-F20 STAFF-F23: «Ausencias pendientes» and «Empleados por rol» to add, under «Personal», with the server\'s figures', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    await shown(page).locator('[data-testid="widgets-customize"]').click();
    const picker = page.locator('ion-modal[data-testid="widgets-picker"]:not(.overlay-hidden)');
    await expect(picker).toContainText('Personal');
    await picker.locator(`[data-testid="widgets-add-${PENDING}"]`).click();
    await picker.locator(`[data-testid="widgets-add-${BY_ROLE}"]`).click();
    await picker.locator('[data-testid="widgets-close"]').click();

    await expect(panel(page, PENDING).locator('[data-testid="widget-title"]')).toHaveText('Ausencias pendientes');
    const { pending_time_off: pending } = await stats(context);
    expect(pending).toBeGreaterThanOrEqual(1);
    await expect(value(page, PENDING)).toHaveText(count.format(pending));

    await expect(panel(page, BY_ROLE).locator('[data-testid="widget-title"]')).toHaveText('Empleados por rol');
    const roles = await byRole(context);
    expect(roles.find((row) => row.name === `${TAG} ${RUN} Estilista`)?.member_count).toBe(2);
    const bars = panel(page, BY_ROLE).locator('[data-testid="widget-bar"]');
    await expect(bars.locator('.widget-bar-label')).toHaveText(roles.map((row) => row.name));
    await expect(bars.locator('.widget-bar-text')).toHaveText(roles.map((row) => count.format(row.member_count)));
  } finally {
    await context.close();
  }
});

test('STAFF-F20 STAFF-F23: the employee, who sees the team and the time off, reads the same five panels', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 }, { board: ALL, who: EMPLOYEE });
  try {
    for (const key of ALL) {
      await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
      await expect(panel(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
    }
    const figures = await stats(context);
    await expect(value(page, HEADCOUNT)).toHaveText(count.format(figures.active));
    await expect(value(page, ON_LEAVE)).toHaveText(count.format(figures.absent_today));
    await expect(value(page, PENDING)).toHaveText(count.format(figures.pending_time_off));
    await expectAway(page, context);
  } finally {
    await context.close();
  }
});

for (const size of VIEWPORTS) {
  test(`STAFF-F20 and STAFF-F23 at ${size.label}: the five panels with the server's figures`, async ({ browser }) => {
    const { context, page } = await spanish(browser, { width: size.width, height: size.height }, { board: ALL });
    try {
      const overflow = () => horizontalOverflow(page);
      for (const key of ALL) {
        await expect(panel(page, key)).toHaveAttribute('aria-busy', 'false');
        await expect(panel(page, key).locator('[data-testid="widget-error"]')).toHaveCount(0);
      }
      const figures = await stats(context);
      await expect(value(page, HEADCOUNT)).toHaveText(count.format(figures.active));
      await expect(panel(page, BY_ROLE).locator('[data-testid="widget-bar"]')).toHaveCount((await byRole(context)).length);
      await expectAway(page, context);
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });

      await panel(page, HEADCOUNT).evaluate((element) => element.scrollIntoView({ block: 'start' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-STAFF-F23-${size.label}`) });

      await panel(page, AWAY).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-STAFF-F20-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
