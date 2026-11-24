// flow: CASH_REGISTER-F18 — the tips another app records in the drawer show in their own lines. A 5.00 € tip in cash,
// recorded by the API as Tips will (by an installed app's name, the demo app standing in for Tips), shows apart in the
// session's detail, says that app as its movement's type and goes, just above the expected cash it raises, into the
// «Close session» window, which closes square at that expected. Screenshots of the window at three widths. What this
// file opens is deleted after it.
import { expect, test } from '@playwright/test';

import { A, api, capture, login, saveSessionForTheSweep, shown } from './helpers';
import { forgetSessions, freshSession } from './cash-session-helpers';
import { dialog, fill } from './inventory-helpers';
import { rowAction } from './service-helpers';
import { stamp } from './sale-helpers';

const CONCEPT = `e2e tip ${stamp()}`;
/** The app that records the tip: any installed app other than the cash register, as the server's tests use. */
const APP = 'demo';
const TIP_LINE = /Demo (in cash|en efectivo)/;
const WIDTHS = [
  { label: '1440', width: 1440, height: 900 },
  { label: '820', width: 820, height: 1180 },
  { label: '375', width: 375, height: 667 },
];
const opened = new Set<string>();

interface Detail {
  status: string;
  expected_balance: number | null;
  closing_balance: number | null;
  difference: number | null;
  summary: { total_cash_in: number | null; expected_cash: number | null; app_lines: { app: string; amount: number }[] | null };
}

test.afterAll(() => forgetSessions(opened));

test('CASH_REGISTER-F18: a tip in cash shows in its own line in the detail and the close window, and the close squares', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, A, '/cash_register/sessions');
  await saveSessionForTheSweep(page.context());
  const id = await freshSession(page.context(), opened);
  const tip = await api(page.context(), A, 'POST', '/cash_register/movements', {
    session_id: id,
    type: 'in',
    amount: 500,
    method_type: 'cash',
    description: CONCEPT,
    app: APP,
  });
  expect(tip.status, JSON.stringify(tip.data)).toBe(201);

  await page.goto(`${A}/cash_register/sessions/${id}`);
  const detail = shown(page);
  const line = detail.locator(`[data-testid=cash-register-summary-${APP}-0]`);
  await expect(line).toContainText(TIP_LINE);
  await expect(line).toContainText(/5[.,]00/);
  await expect(detail.locator('[data-testid=cash-register-summary-cashIn]')).toContainText(/0[.,]00/);
  await expect(detail.locator('[data-testid=cash-register-summary-expected]')).toContainText(/15[.,]00/);
  const row = detail.locator('[data-testid=cash-register-session-movements-row]').filter({ hasText: CONCEPT });
  await expect(row).toContainText('Demo');
  await expect(row).not.toContainText(/Cash in|Entrada/);

  await page.goto(`${A}/cash_register/sessions`);
  await rowAction(page, 'cash-register-sessions', id, 'close');
  const close = dialog(page, 'cash-register-close');
  const tips = close.locator('[data-testid=cash-register-close-app-lines]');
  await expect(tips).toContainText(TIP_LINE);
  await expect(tips).toContainText(/5[.,]00/);
  await expect(close.locator('[data-testid=cash-register-close-expected]')).toContainText(/15[.,]00/);
  for (const width of WIDTHS) {
    await page.setViewportSize({ width: width.width, height: width.height });
    await capture(page, `cash-register-tips-close-${width.label}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await fill(close, 'cash-register-close-counted', '15,00');
  await expect(close.locator('[data-testid=cash-register-close-expected]')).toContainText(/\+?\s?0[.,]00/);
  const submit = close.locator('[data-testid=cash-register-close-submit]');
  await submit.click();
  // Another session's open checks may be on the hub: then the first press warns and the second closes.
  if ((await close.isVisible()) && (await close.locator('[data-testid=cash-register-review-confirm]').count())) await submit.click();
  await expect(close).toBeHidden();

  const closed = (await api<Detail>(page.context(), A, 'GET', `/cash_register/sessions/detail?session_id=${id}`)).data;
  expect([closed.status, closed.expected_balance, closed.closing_balance, closed.difference]).toEqual(['closed', 1500, 1500, 0]);
  expect(closed.summary.total_cash_in).toBe(0);
  expect(closed.summary.app_lines?.map((tipLine) => [tipLine.app, tipLine.amount])).toEqual([
    [APP, 500],
    [APP, 0],
    [APP, 0],
  ]);
});
