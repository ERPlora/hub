// Taxes for an employee (`hub_employee`: `tax.view` only; the WORKBOOK's who may do what): the three lists
// are there, with the read-only notice («You can view the tax rules but not change them.»), without «+»
// and without the row actions of Rules; the API refuses every write with 403 `permission_denied`.
// The owner's Rules is the positive control: the same hooks are there for who may manage.
import { expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, hostPage, shot, shown } from './helpers';

type Envelope = { error?: { code: string } };

test('an employee sees Categories, Rules and Aliases read-only, and the API refuses its writes', async ({ browser }) => {
  const owner = await hostPage(browser, A, { next: '/tax/rules' });
  const employee = await hostPage(browser, A, { next: '/tax/categories', credentials: EMPLOYEE });
  const { page } = employee;
  try {
    // Positive control: the owner gets «+» and the row actions.
    await shown(owner.page).locator('[data-testid=tax-rules-row]').first().waitFor({ state: 'visible' });
    await expect(shown(owner.page).locator('[data-testid=tax-rules-add]')).toBeVisible();
    await expect(shown(owner.page).locator('[data-testid$=-deactivate]').first()).toBeAttached();
    await expect(shown(owner.page).locator('[data-testid=tax-rules-readonly]')).toHaveCount(0);

    for (const section of ['categories', 'rules', 'aliases'] as const) {
      await page.goto(`${A}/tax/${section}`);
      const view = shown(page);
      await view.locator(`[data-testid=tax-${section}-row]`).first().waitFor({ state: 'visible' });
      await expect(view.locator(`[data-testid=tax-${section}-readonly]`)).toContainText(
        /You can view the tax rules but not change them\.|Puedes consultar las reglas fiscales pero no modificarlas\./,
      );
      await expect(view.locator(`[data-testid=tax-${section}-add]`), section).toHaveCount(0);
      await page.screenshot({ path: shot(`tax-employee-${section}`) });
    }
    // Rules: no row action at all.
    await expect(shown(page).locator('[data-testid^=tax-rules-row-]')).toHaveCount(0);

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
