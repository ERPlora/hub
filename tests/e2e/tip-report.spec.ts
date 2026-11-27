// flow: TIP-F13, TIP-F14 — the employee clocks in and serves a check that leaves a tip by card and one in cash, and
// the bar's jar goes to the pool. On Tips → Report the owner sees the day by person (the employee's line and the
// unassigned pool's) and by shift (her working day, and the pool outside every day), and exports it as CSV. The
// employee opens Tips → My tips and sees only hers, today's and this week's, with nothing of managing the tips. Both
// screens seen at a phone, an Android tablet and a desk. What this file makes is deleted after it, and the drawer and
// the apps it changed go back as they were.
import { readFileSync } from 'node:fs';

import { type BrowserContext, expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, login, psql, shown, turnOffTurnedOn, turnOnMissing } from './helpers';
import { cleanInventory, createProduct } from './inventory-helpers';
import { chargeByApi, cleanSales, drawerOff, restoreDrawer, stamp } from './sale-helpers';
import { capturedAtEachSize } from './screen';
import { ownerPage } from './service-helpers';
import { recordOf } from './staff-helpers';
import { pickSelect } from './tax-helpers';

const RUN = stamp();
const SKU = `E2E-TIPR-${RUN}`;

interface Figures {
  card: number;
  cash: number;
  total: number;
  count: number;
}
interface Line extends Figures {
  member_id: string | null;
  member_name: string;
  shift_id: string | null;
}

const turnedOn: string[] = [];
let started: string;
let bea: { id: string; full_name: string };

async function post(context: BrowserContext, path: string, body: Record<string, unknown>): Promise<void> {
  const res = await api(context, A, 'POST', path, body);
  expect(res.status, `${path} ${JSON.stringify(res.data)}`).toBeLessThan(300);
}

test.beforeAll(async ({ browser }) => {
  started = new Date().toISOString();
  // Her user has to have entered once for a record of Staff to be linked to it.
  const employee = await browser.newContext({ baseURL: A });
  await login(await employee.newPage(), A, '/tip/mine', EMPLOYEE);
  await employee.close();
  const { context } = await ownerPage(browser, '/sale/pos');
  await turnOnMissing(context, A, ['tip', 'attendance'], turnedOn);
  // The cash tip and the pool take cash: without the drawer on, no session has to be open for them.
  await drawerOff(context);
  bea = await recordOf(context, EMPLOYEE.email, `E2E Tip Bea ${RUN}`);
  const clockIn = await api(context, A, 'POST', '/attendance/clock_in', { member_id: bea.id });
  expect([200, 201, 409], JSON.stringify(clockIn.data)).toContain(clockIn.status);
  const product = await createProduct(context, { name: `E2E Tip report ${RUN}`, sku: SKU, price: 2000 });
  const sale = await chargeByApi(context, { lines: [{ product: product.sku, quantity: '1' }], payments: [{ method: 'card' }], staff_id: bea.id });
  await post(context, '/tip/tips', { sale: sale.number, method: 'card', amount: 300 });
  await post(context, '/tip/tips', { sale: sale.number, method: 'cash', amount: 150 });
  await post(context, '/tip/tips', { pool: true, amount: 1200 });
  await context.close();
});

test.afterAll(async ({ browser }) => {
  psql(`delete from tip_tip where created_at >= '${started}'`);
  psql(`delete from attendance_break where record_id in (select id from attendance_record where member_id = '${bea.id}' and clock_in_at >= '${started}')`);
  psql(`delete from attendance_record where member_id = '${bea.id}' and clock_in_at >= '${started}'`);
  cleanSales();
  cleanInventory();
  restoreDrawer();
  const { context } = await ownerPage(browser, '/sale/pos');
  await turnOffTurnedOn(context, A, turnedOn);
  await context.close();
});

test('TIP-F13: the owner sees the day’s tips by person and by shift, and exports them', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/tip/report');
  const report = shown(page);
  const byPerson = (await api<{ rows: Line[]; totals: Figures }>(page.context(), A, 'GET', '/tip/report?by=person')).data;
  const hers = byPerson.rows.find((line) => line.member_id === bea.id)!;
  expect([hers.card, hers.cash, hers.count]).toEqual([300, 150, 2]);
  expect(byPerson.rows.at(-1)!.member_id).toBeNull();

  await expect(report.locator('[data-testid=tip-report-figures-total]')).toBeVisible();
  await expect(report.locator('[data-testid=tip-report-row]', { hasText: bea.full_name }).first()).toBeVisible();
  await expect(report.locator('[data-testid=tip-report-row]', { hasText: /Unassigned|Sin asignar/ }).first()).toBeVisible();
  await capturedAtEachSize(page, 'tip-report-person', 'tip-report-row');

  await pickSelect(page, report.locator('[data-testid=tip-report-by]'), /^(By shift|Por turno)$/);
  const shift = report.locator('[data-testid=tip-report-row]', { hasText: bea.full_name }).first();
  await expect(shift).toBeVisible();
  await expect(shift).toContainText('–');
  await expect(report.locator('[data-testid=tip-report-row]', { hasText: /Outside a clocked working day|Fuera de una jornada fichada/ }).first()).toBeVisible();
  await capturedAtEachSize(page, 'tip-report-shift', 'tip-report-row');

  const download = page.waitForEvent('download');
  await report.locator('[data-testid=tip-report-export]').click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/^tips-by-shift-\d{4}-\d{2}-\d{2}\.csv$/);
  const csv = readFileSync(await file.path(), 'utf8');
  expect(csv).toContain(bea.full_name);
  expect(csv).toMatch(/3\.00,1\.50,0\.00,4\.50/);
});

test('TIP-F14: the employee sees only her own tips of today and of the week, with nothing of managing them', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  try {
    await login(page, A, '/tip/mine', EMPLOYEE);
    const mine = shown(page);
    await expect(mine.locator('[data-testid=tip-mine-day-total]')).toContainText(/4[.,]50/);
    await expect(mine.locator('[data-testid=tip-mine-week-total]')).toContainText(/4[.,]50/);
    for (const managing of ['tip-list-add', 'tip-report-export', 'tab-tips', 'tab-report', 'tab-settings']) {
      await expect(page.locator(`[data-testid=${managing}]`), managing).toHaveCount(0);
    }
    expect((await api(context, A, 'GET', '/tip/report')).status).toBe(403);
    await capturedAtEachSize(page, 'tip-mine', 'tip-mine-day-total');
  } finally {
    await context.close();
  }
});
