// Taxes for an employee (`hub_employee`: `tax.view` only, which the till needs; the WORKBOOK's who may do what): its
// screens set the business up, so its menu does not show them and by their address they say «No access» (BASE-F118);
// the API refuses every write with 403 `permission_denied` and still answers its reads. The owner's Rules is the
// positive control: the same screen opens, with «+» and the row actions, for who may manage.
import { expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, hostPage, shot, shown, testid } from './helpers';

type Envelope = { error?: { code: string } };

test('an employee gets «No access» on Categories, Rules and Aliases, and the API refuses its writes', async ({ browser }) => {
  const owner = await hostPage(browser, A, { next: '/tax/rules' });
  const employee = await hostPage(browser, A, { next: '/tax/categories', credentials: EMPLOYEE });
  const { page } = employee;
  try {
    // Positive control: the owner gets «+» and the row actions.
    await shown(owner.page).locator('[data-testid=tax-rules-row]').first().waitFor({ state: 'visible' });
    await expect(shown(owner.page).locator('[data-testid=tax-rules-add]')).toBeVisible();
    await expect(shown(owner.page).locator('[data-testid$=-deactivate]').first()).toBeAttached();
    await expect(testid(owner.page, 'no-access')).toHaveCount(0);

    for (const section of ['categories', 'rules', 'aliases'] as const) {
      await page.goto(`${A}/tax/${section}`);
      await expect(testid(page, 'no-access'), section).toBeVisible();
      await expect(shown(page).locator(`[data-testid=tax-${section}-add]`), section).toHaveCount(0);
      await page.screenshot({ path: shot(`tax-employee-${section}`) });
    }

    // By the API: every write refused with 403 permission_denied.
    const writes: ReadonlyArray<readonly [string, unknown]> = [
      ['/tax/categories', { key: 'e2e.by_employee', name: 'By the employee' }],
      ['/tax/rules', { country_code: 'ES', tax_category_key: 'product.generic', rate_pct: 21 }],
      ['/tax/rules/deactivate', { country_code: 'ES', tax_category_key: 'product.generic' }],
      ['/tax/aliases', { alias: 'by employee', tax_category_key: 'product.generic' }],
    ];
    for (const [path, body] of writes) {
      const res = await api<Envelope>(employee.context, A, 'POST', path, body);
      expect(res.status, path).toBe(403);
      expect(res.data.error?.code, path).toBe('permission_denied');
    }
    // What it may do, it does: read.
    expect((await api(employee.context, A, 'GET', '/tax/categories?limit=1')).status).toBe(200);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});
