// «What it allows» of a role, basic or the business's own: opened from Employees › Roles, app by app, and read only for
// whoever does not manage the roles; it follows live what the business changes in its own.
// flow: BASE-F82
import { type Browser, type BrowserContext, expect, type Page, test, type ViewportSize } from '@playwright/test';

import { A, api, capture, collectProblems, EMPLOYEE, horizontalOverflow, hostPage, shown, uniqueName, untilStill } from './helpers';

const VIEWPORTS = {
  375: { width: 375, height: 667 },
  820: { width: 820, height: 1180 },
  1440: { width: 1440, height: 900 },
} as const;

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

/** The capture once the page settled, without sideways scroll. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await page.mouse.move(0, 0);
  await expect(shown(page).locator('[data-testid$="-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `BASE-F82-${key}-${width}`, { fullPage: true });
}

/** What the role does with ``permission``: its phrase and its pill's tone. */
async function expectLine(page: Page, permission: string, phrase: string, tone: string): Promise<void> {
  const line = testid(page, `role-permission-${permission}`);
  await expect(line).toContainText(phrase);
  await expect(line.locator('[data-testid="role-state"]')).toHaveAttribute('data-tone', tone);
}

/** Employees › Roles as the owner opens it, with the five basic roles. */
async function openRoles(browser: Browser, viewport: ViewportSize) {
  const { context, page } = await hostPage(browser, A, { viewport, next: '/employees#roles' });
  const problems = await collectProblems(page);
  const rows = shown(page).locator('[data-testid="roles-row"], [data-testid="roles-card"]');
  await expect(rows).toHaveCount(5);
  return { context, page, problems, rows };
}

/** A role the business makes from the employee's, deleted with its context's session after ``use``. */
async function withRole(context: BrowserContext, use: (role: { key: string; label: string }) => Promise<void>): Promise<void> {
  const made = await api<{ key: string; label: string }>(context, A, 'POST', '/roles', {
    based_on: 'hub_employee',
    name: uniqueName('Cashier'),
  });
  expect(made.status).toBe(200);
  try {
    await use(made.data);
  } finally {
    expect((await api(context, A, 'POST', '/roles/delete', { role: made.data.key })).status).toBe(200);
  }
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`the owner opens what the employee role allows from Roles at ${width}`, async ({ browser }) => {
    const { context, page, problems, rows } = await openRoles(browser, viewport);
    await rows.nth(3).click();
    await expect(page).toHaveURL(/\/employees\/roles\/hub_employee$/);
    await expect(testid(page, 'role-members')).toBeVisible();
    await expect(testid(page, 'role-app-base')).toContainText('The business');
    await expect(testid(page, 'role-app-sensitive')).toContainText('Sensitive data');
    await expectLine(page, 'sale.void_sale', 'Void a sale', 'warning');
    await expectLine(page, 'sale.take_payment', 'Take payments', 'success');
    await expectLine(page, 'base.view_costs', 'View costs', 'neutral');
    await expect(shown(page).locator('ion-toggle, ion-checkbox')).toHaveCount(0);
    await snap(page, 'employee', width);
    const seen = await problems();
    expect(seen.console).toEqual([]);
    expect(seen.page).toEqual([]);
    if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    await context.close();
  });

  test(`a role the business made goes by its name, and what it allows follows live what changes in it, at ${width}`, async ({ browser }) => {
    const { context, page, problems, rows } = await openRoles(browser, viewport);
    await withRole(context, async ({ key, label: name }) => {
      await expect(rows).toHaveCount(6);
      await expect(rows.nth(5)).toContainText(name);
      await expect(rows.nth(5)).toContainText('Custom');
      await snap(page, 'list-own', width);
      await rows.nth(5).click();
      await expect(page).toHaveURL(new RegExp(`/employees/roles/${key}$`));
      await expect(testid(page, 'role-members')).toContainText('0');
      await expect(testid(page, 'role-permission-base.own_business')).toHaveCount(0);

      const reader = await hostPage(browser, A, { viewport, next: `/employees/roles/${key}`, credentials: EMPLOYEE });
      await expectLine(reader.page, 'sale.take_payment', 'Take payments', 'success');
      const changed = { role: key, states: { 'sale.take_payment': 'off' } };
      expect((await api(context, A, 'POST', '/roles/update', changed)).status).toBe(200);
      await expectLine(reader.page, 'sale.take_payment', 'Take payments', 'neutral');
      await expect(shown(reader.page).locator('ion-toggle')).toHaveCount(0);
      await snap(reader.page, 'own', width);
      await reader.context.close();
    });
    const seen = await problems();
    expect(seen.console).toEqual([]);
    expect(seen.page).toEqual([]);
    await context.close();
  });

  test(`an employee reads it too, and a role that does not exist says so, at ${width}`, async ({ browser }) => {
    const { context, page } = await hostPage(browser, A, { viewport, next: '/employees/roles/hub_manager', credentials: EMPLOYEE });
    await expectLine(page, 'sale.void_sale', 'Void a sale', 'success');
    await snap(page, 'manager-by-employee', width);
    await page.goto(page.url().replace('hub_manager', 'hub_cashier'));
    await expect(testid(page, 'role-not-found')).toContainText('This role does not exist in this business.');
    await snap(page, 'not-found', width);
    await context.close();
  });
}
