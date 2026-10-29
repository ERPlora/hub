// flow: ATTENDANCE-F11
// The time clock's panel of the Home (FIX-ATTENDANCE-SETUP-HOOKS; the old module's one `widgets`, the old hub's
// dashboard in docs/reference/old-hub/dashboard-*.png), as the owner of hub `a` reads it in Spanish: «Fichados ahora» on
// the board by default with the server's count, which follows a clock-in and a clock-out made elsewhere (by the API, as
// the assistant would) without a reload; the employee, who does not see the whole team, never gets it. Captures
// `FIX-ATTENDANCE-SETUP-HOOKS-<width>`. Everything this file creates is named «E2E-PRESENCE …» and removed after it.
import { type Browser, type BrowserContext, expect, type Locator, type Page, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, horizontalOverflow, login, OWNER, psql, shot, shown, untilStill } from './helpers';
import { VIEWPORTS } from './inventory-helpers';
import { stamp } from './sale-helpers';

const KEY = 'FIX-ATTENDANCE-SETUP-HOOKS';
const TAG = 'E2E-PRESENCE';
const CLOCKED_IN_NOW = 'attendance.clocked_in_now';
/** Where the Home keeps this browser's board (base/frontend/lib/home.ts `BOARD_STORAGE_KEY`). */
const BOARD = 'dashboard-hub';
const RUN = stamp();
const count = new Intl.NumberFormat('es-ES');
const RECORDS = `select id from attendance_record where member_id in (select id from staff_member where first_name like '${TAG}%')`;

test.describe.configure({ mode: 'serial' });

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

async function member(context: BrowserContext, first: string): Promise<string> {
  const res = await api<{ id: string }>(context, A, 'POST', '/staff/members', { first_name: `${TAG} ${first}`, last_name: RUN });
  expect(res.status, JSON.stringify(res.data)).toBe(201);
  return res.data.id;
}

/** Clocks `memberId` in or out as the owner (ATTENDANCE-F12), never through the Home. */
async function clock(context: BrowserContext, memberId: string, way: 'in' | 'out'): Promise<void> {
  const res = await api(context, A, 'POST', `/attendance/clock_${way}`, { member_id: memberId });
  expect(res.status, JSON.stringify(res.data)).toBe(200);
}

async function presence(context: BrowserContext): Promise<number> {
  const res = await api<{ count: number }>(context, A, 'GET', '/attendance/presence/count');
  expect(res.status).toBe(200);
  return res.data.count;
}

// Ana is in for the whole file; Bea clocks in and out in the live test.
let ana = '';
let bea = '';

test.beforeAll(async ({ browser }) => {
  cleanup();
  const context = await browser.newContext({ baseURL: A });
  try {
    const page = await context.newPage();
    await login(page, A, '/attendance/records');
    ana = await member(context, 'Ana');
    bea = await member(context, 'Bea');
    await clock(context, ana, 'in');
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
  // The owner's Spanish session for the fleet's visual sweep (`ui-clip-sweep.sh --storage-state`).
  if (!options.who && process.env.E2E_SAVE_STORAGE_STATE) {
    await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
  }
  return { context, page };
}

const panel = (page: Page, key: string): Locator =>
  shown(page).locator(`[data-testid="widget-board"] [data-testid="widget"][data-key="${key}"]`);
const value = (page: Page, key: string): Locator => panel(page, key).locator('[data-testid="widget-value"]');

test('ATTENDANCE-F11: «Fichados ahora» on the owner\'s Home by default with the server\'s count, live', async ({ browser }) => {
  const { context, page } = await spanish(browser, { width: 1440, height: 900 });
  try {
    await expect(panel(page, CLOCKED_IN_NOW).locator('[data-testid="widget-title"]')).toHaveText('Fichados ahora');
    // A KPI says its name once (gh:hub#1105): the title, no second label inside.
    await expect(panel(page, CLOCKED_IN_NOW).getByText('Fichados ahora')).toHaveCount(1);
    const before = await presence(context);
    expect(before).toBeGreaterThanOrEqual(1); // Ana
    await expect(value(page, CLOCKED_IN_NOW)).toHaveText(count.format(before));

    // Bea clocks in elsewhere: the panel follows without a reload.
    await clock(context, bea, 'in');
    expect(await presence(context)).toBe(before + 1);
    await expect(value(page, CLOCKED_IN_NOW)).toHaveText(count.format(before + 1));

    // And she clocks out: it goes back down.
    await clock(context, bea, 'out');
    expect(await presence(context)).toBe(before);
    await expect(value(page, CLOCKED_IN_NOW)).toHaveText(count.format(before));
  } finally {
    await context.close();
  }
});

test('ATTENDANCE-F11: the employee, who does not see the whole team, never gets «Fichados ahora»', async ({ browser }) => {
  // Even with the panel on this browser's board: the Home offers only what the person may read.
  const { context, page } = await spanish(browser, { width: 1440, height: 900 }, { board: [CLOCKED_IN_NOW], who: EMPLOYEE });
  try {
    await expect(panel(page, CLOCKED_IN_NOW)).toHaveCount(0);
    expect((await api(context, A, 'GET', '/attendance/presence/count')).status).toBe(403);
  } finally {
    await context.close();
  }
});

for (const size of VIEWPORTS) {
  test(`ATTENDANCE-F11 at ${size.label}: «Fichados ahora» on the default board with the server's count`, async ({ browser }) => {
    const { context, page } = await spanish(browser, { width: size.width, height: size.height });
    try {
      const overflow = () => horizontalOverflow(page);
      await expect(panel(page, CLOCKED_IN_NOW)).toHaveAttribute('aria-busy', 'false');
      await expect(panel(page, CLOCKED_IN_NOW).locator('[data-testid="widget-error"]')).toHaveCount(0);
      await expect(value(page, CLOCKED_IN_NOW)).toHaveText(count.format(await presence(context)));
      await panel(page, CLOCKED_IN_NOW).evaluate((element) => element.scrollIntoView({ block: 'center' }));
      await untilStill(page);
      expect(await overflow(), `no sideways scroll at ${size.label}`).toBeLessThanOrEqual(0);
      await page.screenshot({ path: shot(`${KEY}-${size.label}`) });
    } finally {
      await context.close();
    }
  });
}
