// BASE-F118: an employee who opens by its address a screen its role does not open (Taxes' «Rules», an entry its menu
// does not show) gets «No access» in that same address, with the names of who can give it, in the three widths; the
// owner, the positive control, opens the same screen. A screen of the employee's own work still opens.
import { expect, test } from '@playwright/test';

import { A, api, EMPLOYEE, hostPage, shot, shown, testid, THREE_SIZES } from './helpers';

type People = { people: { name: string; role: string; me: boolean }[] };

test('BASE-F118: an employee opening by its address a screen its role does not open sees «No access» and whom to ask @smoke', async ({ browser }) => {
  const owner = await hostPage(browser, A, { next: '/tax/rules' });
  const employee = await hostPage(browser, A, { next: '/tax/rules', credentials: EMPLOYEE });
  try {
    await expect(shown(owner.page).locator('[data-testid=tax-rules-add]')).toBeVisible();
    await expect(testid(owner.page, 'no-access')).toHaveCount(0);
    const people = (await api<People>(owner.context, A, 'GET', '/people')).data.people;
    const ownerName = people.find((person) => person.role === 'hub_owner')?.name ?? '';
    const employeeName = people.find((person) => person.role === 'hub_employee')?.name ?? '';
    expect(ownerName).not.toBe('');

    const { page } = employee;
    for (const size of THREE_SIZES) {
      await page.setViewportSize(size);
      await page.goto(`${A}/tax/rules`);
      await expect(testid(page, 'no-access')).toContainText(/You do not have access to this screen|No tienes acceso a esta pantalla/);
      expect(new URL(page.url()).pathname).toBe('/tax/rules');
      const grantors = testid(page, 'no-access-grantor');
      await expect(grantors.filter({ hasText: ownerName })).toBeVisible();
      if (employeeName) await expect(grantors.filter({ hasText: employeeName })).toHaveCount(0);
      await expect(shown(page).locator('[data-testid=tax-rules-add]')).toHaveCount(0);
      await page.screenshot({ path: shot(`base-no-access-${size.label}`) });
    }

    await testid(page, 'no-access-home').click();
    await expect(page).toHaveURL(`${A}/`);
    await page.goto(`${A}/sale/sales`);
    await expect(shown(page).locator('ion-content').first()).toBeVisible();
    await expect(testid(page, 'no-access')).toHaveCount(0);
  } finally {
    await owner.context.close();
    await employee.context.close();
  }
});
