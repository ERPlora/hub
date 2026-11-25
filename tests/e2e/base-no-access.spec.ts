// BASE-F118: an employee who opens by its address a screen its role does not open (Taxes' «Rules», an entry its menu
// does not show; System, a platform screen its side menu does not show; and another person's page in Employees, whose
// read the server refuses them) gets «No access» in that same address, with the names of who can give it, in the three
// widths; the owner, the positive control, opens the same screens. A screen of the employee's own work still opens.
import { expect, test } from '@playwright/test';

import { A, api, capture, EMPLOYEE, hostPage, saveSessionForTheSweep, shown, testid, THREE_SIZES } from './helpers';

type People = { people: { id: string; name: string; role: string; me: boolean }[] };

test('BASE-F118: an employee opening by its address a screen its role does not open sees «No access» and whom to ask @smoke', async ({ browser }) => {
  const owner = await hostPage(browser, A, { next: '/tax/rules' });
  const employee = await hostPage(browser, A, { next: '/tax/rules', credentials: EMPLOYEE });
  try {
    await expect(shown(owner.page).locator('[data-testid=tax-rules-add]')).toBeVisible();
    await expect(testid(owner.page, 'no-access')).toHaveCount(0);
    await owner.page.goto(`${A}/system`);
    await expect(testid(owner.page, 'tab-usage')).toBeVisible();
    await expect(testid(owner.page, 'no-access')).toHaveCount(0);
    // Named as on the till's grid: an account erplora.com names by its email shows the part before the «@».
    const people = (await api<People>(owner.context, A, 'GET', '/people')).data.people;
    const nameOf = (role: string) => (people.find((person) => person.role === role)?.name ?? '').split('@')[0];
    const ownerName = nameOf('hub_owner');
    const employeeName = nameOf('hub_employee');
    expect(ownerName).not.toBe('');
    const ownerPerson = `/employees/${people.find((person) => person.role === 'hub_owner')?.id ?? ''}`;
    await owner.page.goto(`${A}${ownerPerson}`);
    await expect(testid(owner.page, 'person-data')).toBeVisible();
    await expect(testid(owner.page, 'no-access')).toHaveCount(0);

    const { page } = employee;
    await saveSessionForTheSweep(employee.context);
    for (const size of THREE_SIZES) {
      await page.setViewportSize(size);
      for (const [path, shot, inside] of [
        ['/tax/rules', 'base-no-access', 'tax-rules-add'],
        ['/system', 'base-no-access-system', 'tab-usage'],
        [ownerPerson, 'base-no-access-person', 'person-data'],
      ]) {
        await page.goto(`${A}${path}`);
        await expect(testid(page, 'no-access')).toContainText(/You do not have access to this screen|No tienes acceso a esta pantalla/);
        expect(decodeURIComponent(new URL(page.url()).pathname)).toBe(path);
        const grantors = testid(page, 'no-access-grantor');
        await expect(grantors.filter({ hasText: ownerName })).toBeVisible();
        if (employeeName) await expect(grantors.filter({ hasText: employeeName })).toHaveCount(0);
        await expect(grantors.filter({ hasText: '@' })).toHaveCount(0);
        await expect(shown(page).locator(`[data-testid=${inside}]`)).toHaveCount(0);
        await capture(page, `${shot}-${size.label}`);
      }
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
