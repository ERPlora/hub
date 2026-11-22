// «What it allows» of a basic role: opened from Employees › Roles, read only, app by app.
// flow: BASE-F82
import { type Browser, expect, type Page, test } from '@playwright/test';

import { A, collectProblems, EMPLOYEE, horizontalOverflow, hostPage, shot, shown, untilStill } from './helpers';

const VIEWPORTS = {
  375: { width: 375, height: 667 },
  820: { width: 820, height: 1180 },
  1440: { width: 1440, height: 900 },
} as const;

const testid = (page: Page, id: string) => shown(page).locator(`[data-testid="${id}"]`);

async function signedIn(browser: Browser, viewport: { width: number; height: number }, next: string, employee = false) {
  return hostPage(browser, A, { viewport, next, credentials: employee ? EMPLOYEE : undefined });
}

/** The capture once the page settled, without sideways scroll. */
async function snap(page: Page, key: string, width: number): Promise<void> {
  await page.mouse.move(0, 0);
  await expect(shown(page).locator('[data-testid$="-loading"]:visible')).toHaveCount(0);
  await untilStill(page);
  expect(await horizontalOverflow(page), `${key} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await page.screenshot({ path: shot(`BASE-F82-${key}-${width}`), fullPage: true });
}

/** What the role does with ``permission``: its phrase and its pill's tone. */
async function expectLine(page: Page, permission: string, phrase: string, tone: string): Promise<void> {
  const line = testid(page, `role-permission-${permission}`);
  await expect(line).toContainText(phrase);
  await expect(line.locator('[data-testid="role-state"]')).toHaveAttribute('data-tone', tone);
}

for (const [label, viewport] of Object.entries(VIEWPORTS)) {
  const width = Number(label);

  test(`the owner opens what the employee role allows from Roles at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/employees#roles');
    const problems = await collectProblems(page);
    const rows = shown(page).locator('[data-testid="roles-row"], [data-testid="roles-card"]');
    await expect(rows).toHaveCount(5);
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

  test(`an employee reads it too, and a role that does not exist says so, at ${width}`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, viewport, '/employees/roles/hub_manager', true);
    await expectLine(page, 'sale.void_sale', 'Void a sale', 'success');
    await snap(page, 'manager-by-employee', width);
    await page.goto(page.url().replace('hub_manager', 'hub_cashier'));
    await expect(testid(page, 'role-not-found')).toContainText('This role does not exist in this business.');
    await snap(page, 'not-found', width);
    await context.close();
  });
}
