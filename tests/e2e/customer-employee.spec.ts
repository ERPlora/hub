// What an employee can do with customers (apps.py `role_permissions`: `customer.view` and
// `customer.manage`), in Ioan's Chrome: sees the list and adds a customer, imports, edits and notes
// on the card; gets «Merge with…», which a manager approves with their PIN (BASE-F84: customer-approval.spec.ts);
// does not get «Export CSV», «Delete» nor «Erase personal data», and the server refuses the export to them too
// (403), whatever the screen shows.
import { expect, test } from '@playwright/test';

import { cleanUp, customersReady, e2eName, idFromUrl, inputOf, rowNamed, searchList } from './customer-helpers';
import { A, api, EMPLOYEE, hostPage, shot, shown } from './helpers';

test.afterAll(() => cleanUp());

test('the employee sees and creates customers but neither exports nor deletes', async ({ browser }) => {
  const { context, page } = await hostPage(browser, A, { next: '/customer/customers', credentials: EMPLOYEE });
  try {
    await customersReady(page);
    await expect(shown(page).locator('[data-testid=customer-list-add]')).toBeVisible();
    await expect(shown(page).locator('[data-testid=customer-import]')).toBeVisible();
    await expect(shown(page).locator('[data-testid=customer-export]')).toHaveCount(0);

    // Creates one.
    const name = e2eName('By employee');
    await shown(page).locator('[data-testid=customer-list-add]').click();
    const dialog = page.locator('ion-modal[data-testid=customer-create]');
    await inputOf(dialog, 'customer-form-name').fill(name);
    await dialog.locator('[data-testid=customer-create-submit]').click();
    await expect(dialog).toBeHidden();
    await searchList(page, 'customer-list', name);
    const row = rowNamed(page, 'customer-list', name);
    await expect(row).toBeVisible();
    await expect(row.locator('[data-testid$=-delete]')).toHaveCount(0);
    await page.screenshot({ path: shot('customer-employee-list') });

    // On the card: Edit and Merge with… (with a manager's approval); the note form is there.
    await row.click();
    await page.waitForURL(/\/customer\/customers\/[0-9a-f-]+$/);
    idFromUrl(page);
    const actions = shown(page).locator('[data-testid=customer-detail-actions] ion-button');
    await expect(actions).toHaveCount(2);
    await expect(actions.nth(0)).toHaveAttribute('data-testid', 'customer-detail-edit');
    await expect(actions.nth(1)).toHaveAttribute('data-testid', 'customer-detail-merge');
    await expect(shown(page).locator('[data-testid=customer-note-form]')).toBeVisible();
    await page.screenshot({ path: shot('customer-employee-card') });

    // The server refuses the export to them, whatever the screen shows.
    const res = await api<{ error: { code: string } }>(context, A, 'GET', '/customer/customers/export');
    expect(res.status).toBe(403);
    expect(res.data.error.code).toBe('permission_denied');
  } finally {
    await context.close();
  }
});
