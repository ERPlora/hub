// flow: BASE-F131
// The bell's notice of the roles of the business left to review, as the owner of hub `a` meets it in Spanish at 375, 820
// and 1440: a role that lacks a permission comes as a card without reloading, the bell says how many, «Revisar los
// roles» opens Empleados › Roles, an employee never sees it, and once the role is saved with what it lacked it goes
// without reloading. The role is the run's own, deleted after it.
import { type BrowserContext, expect, type Page, test } from '@playwright/test';

import {
  arrivalCard,
  bellSays,
  bellTotal,
  expectTheServersWords,
  featureNotice,
  noticeButton,
  serverCounter,
} from './action-center';
import { A, api, capture, EMPLOYEE, horizontalOverflow, psql, shown, uniqueName } from './helpers';
import { spanishPerson } from './home-helpers';

const KEY = 'base.roles_to_review';
const TITLE = '1 rol por revisar';
/** A permission of an app that is on, which the role loses behind the Hub's back as one an app adds later. */
const PERMISSION = 'sale.void_sale';
const SIZES = [
  { width: 375, height: 667 },
  { width: 820, height: 1180 },
  { width: 1440, height: 900 },
] as const;

async function snap(page: Page, name: string, width: number): Promise<void> {
  expect(await horizontalOverflow(page), `${name} at ${width}: no sideways scroll`).toBeLessThanOrEqual(0);
  await capture(page, `BASE-F131-${name}-${width}`);
}

/** A role the owner makes from the employee's, which then lacks `PERMISSION`; saving another one tells the bell. */
async function roleToReview(context: BrowserContext): Promise<string> {
  const made = await api<{ key: string }>(context, A, 'POST', '/roles', { based_on: 'hub_employee', name: uniqueName('Caja') });
  expect(made.status).toBe(200);
  psql(`update base_businessrole set states = states - '${PERMISSION}' where id = '${made.data.key}'`);
  expect((await api(context, A, 'POST', '/roles/update', { role: made.data.key, description: 'e2e' })).status).toBe(200);
  return made.data.key;
}

for (const size of SIZES) {
  test(`the bell counts the roles to review and leads to them at ${size.width}`, async ({ browser }) => {
    const { context, page } = await spanishPerson(browser, size);
    // The bell's first result is in: what comes after it arrives as a card.
    await bellSays(page, await bellTotal(context));
    const role = await roleToReview(context);
    try {
      await expect(arrivalCard(page)).toContainText(TITLE);
      await expect(arrivalCard(page)).toHaveCount(0, { timeout: 15_000 });
      const counter = await serverCounter(context, KEY);
      expect(counter?.severity).toBe('info');
      const featured = await featureNotice(page, TITLE);
      await expectTheServersWords(featured, counter!);
      await snap(page, 'panel', size.width);
      await noticeButton(featured, 'Revisar los roles').click();
      await expect(page).toHaveURL(/\/employees#roles$/);
      await expect(shown(page).locator('[data-testid="roles-row"], [data-testid="roles-card"]')).toHaveCount(6);
      await snap(page, 'roles', size.width);

      const employee = await spanishPerson(browser, size, EMPLOYEE);
      expect(await serverCounter(employee.context, KEY)).toBeUndefined();
      await employee.context.close();

      const pending = await bellTotal(context);
      await bellSays(page, pending);
      expect((await api(context, A, 'POST', '/roles/update', { role, states: { [PERMISSION]: 'off' } })).status).toBe(200);
      await bellSays(page, pending - 1);
      expect(await serverCounter(context, KEY)).toBeUndefined();
    } finally {
      expect((await api(context, A, 'POST', '/roles/delete', { role })).status).toBe(200);
      await context.close();
    }
  });
}
