// Services → «Bonos y paquetes» and Settings in Chrome (WORKBOOK SERVICE-F11 to F19, F29, F30), with the
// real Taxes and Customers apps: the owner creates a voucher with a line; two customers buy it (granted
// through the API, as the assistant does) and one spends a session; «Sold vouchers» shows both with
// what is left, a courtesy is given with «Adjust» and the untouched one voided with its reason;
// «Movements» shows the courtesy and the session; the customer's card deleted in Customers sends the
// voucher to «Vouchers with no customer»; deleting the voucher asks first and the Deleted filter still
// finds it. Settings saves the default duration. Each screen is captured in three viewports.
import { expect, test } from '@playwright/test';

import { A, api, shot, shown } from './helpers';
import { cleanUp, named, ownerPage, pick, post, rowAction, VIEWPORTS } from './service-helpers';

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

test('Vouchers: create, sold, adjusted, voided, movements, orphans and delete; settings saved', async ({ browser }) => {
  const bono = named('Bono');
  const { context, page } = await ownerPage(browser, '/service/packages');
  const settings = await api<{ default_duration: number }>(context, A, 'GET', '/service/settings');
  try {
    const cut = await post<{ id: string; name: string }>(context, '/service/services', {
      name: named('Cut'),
      price: 2000,
      tax_category_key: 'service.generic',
    });
    const lucia = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Lucía') });
    const marta = await post<{ id: string; name: string }>(context, '/customer/customers', { name: named('Marta') });

    // «New package»: Uses, Validity and a line with the service.
    const view = shown(page);
    await view.locator('[data-testid=service-packages-empty], [data-testid=service-packages-row]').first().waitFor({ state: 'visible' });
    await view.locator('[data-testid=service-packages-add]').click();
    await page.locator('[data-testid=service-package-form-name] input').fill(bono);
    await page.locator('[data-testid=service-package-form-max_uses] input').fill('5');
    await page.locator('[data-testid=service-package-form-validity_days] input').fill('180');
    await page.locator('[data-testid=service-package-form-fixed_price] input').fill('90');
    await pick(page, 'service-package-form-line-service-0', cut.name.split(' ').pop()!, cut.name);
    await page.screenshot({ path: shot('service-packages-new') });
    await page.locator('[data-testid=service-package-form-submit]').click();
    const row = view.locator('[data-testid=service-packages-row]', { hasText: bono });
    await expect(row).toContainText('€90.00');
    await expect(row).toContainText('Active');

    // Two customers buy it; one spends a session.
    const packageId = (await api<{ id: string }>(context, A, 'GET', `/service/packages/detail?package=${encodeURIComponent(bono)}`)).data.id;
    const sold = await post<{ id: string }>(context, '/service/grants', { package_id: packageId, customer_id: lucia.id, amount: 9000 });
    const untouched = await post<{ id: string }>(context, '/service/grants', { package_id: packageId, customer_id: marta.id, amount: 9000 });
    await post(context, '/service/grants/redeem', { id: sold.id, service_id: cut.id }, 200);

    // «Sold vouchers»: both purchases with what is left; a courtesy and a void.
    await rowAction(page, 'service-packages', packageId, 'grants');
    const sheet = page.locator('ion-modal[data-testid=service-grants]');
    await expect(sheet.locator('[data-testid=service-grants-title]')).toContainText(`Sold vouchers — ${bono}`);
    await expect(sheet.locator(`[data-testid=service-grants-row-${sold.id}]`)).toContainText('1 used · 4 left');
    await expect(sheet.locator(`[data-testid=service-grants-row-${untouched.id}]`)).toContainText('0 used · 5 left');
    await sheet.locator(`[data-testid=service-grants-adjust-${sold.id}]`).click();
    await page.locator('[data-testid=service-grant-adjust-uses] input').fill('1');
    await page.locator('[data-testid=service-grant-adjust-reason] textarea').fill('Courtesy for the delay');
    await expect(page.locator('[data-testid=service-grant-adjust-preview]')).toContainText('After the adjustment: 5 session(s) left');
    await page.locator('[data-testid=service-grant-adjust-submit]').click();
    await expect(sheet.locator(`[data-testid=service-grants-row-${sold.id}]`)).toContainText('Given afterwards: +1 session(s), +0 day(s)');
    await sheet.locator(`[data-testid=service-grants-void-${untouched.id}]`).click();
    await expect(page.locator('ion-modal[data-testid=service-grant-void]')).toContainText(`The voucher of customer ${marta.name} (€90.00)`);
    await page.locator('[data-testid=service-grant-void-reason] textarea').fill('Sold to the wrong customer');
    await page.locator('[data-testid=service-grant-void-submit]').click();
    await expect(sheet.locator(`[data-testid=service-grants-row-${untouched.id}]`)).toContainText('Voided by');
    await expect(sheet.locator(`[data-testid=service-grants-row-${untouched.id}]`)).toContainText('Sold to the wrong customer');
    await page.screenshot({ path: shot('service-grants-desktop') });
    await sheet.locator('[data-testid=service-grants-close]').click();

    // «Movements»: the courtesy and the session, the most recent first.
    await rowAction(page, 'service-packages', packageId, 'movements');
    const movements = page.locator('ion-modal[data-testid=service-movements]');
    await expect(movements.locator('[data-testid^=service-movements-row-]').first()).toContainText('Courtesy');
    await expect(movements.locator('[data-testid^=service-movements-row-]').nth(1)).toContainText('Delivered');
    await expect(movements.locator('[data-testid^=service-movements-row-]').nth(1)).toContainText(cut.name);
    await page.screenshot({ path: shot('service-movements-desktop') });
    await movements.locator('[data-testid=service-movements-close]').click();

    // The card deleted in Customers: the voucher goes to «Vouchers with no customer».
    await post(context, '/customer/customers/delete', { id: lucia.id }, 200);
    await view.locator('[data-testid=service-packages-orphans-open]').click();
    const orphans = page.locator('ion-modal[data-testid=service-orphans]');
    await expect(orphans.locator(`[data-testid=service-orphans-row-${sold.id}]`)).toContainText(`Customer reference: ${lucia.id}`);
    await expect(orphans.locator(`[data-testid=service-orphans-row-${sold.id}]`)).toContainText('5 session(s) left');
    await page.screenshot({ path: shot('service-orphans-desktop') });
    await orphans.locator('[data-testid=service-orphans-close]').click();

    // Delete asks first; the Deleted filter still finds what was sold.
    await rowAction(page, 'service-packages', packageId, 'delete');
    await expect(page.locator('ion-modal[data-testid=service-packages-delete]')).toContainText('the package and its 1 line(s) leave the catalogue');
    await page.locator('[data-testid=service-packages-delete-submit]').click();
    await expect(row).toHaveCount(0);
    await view.locator('[data-testid=service-packages-filter-status]').click();
    await page.locator('ion-popover').getByText('Deleted', { exact: true }).click();
    await expect(row).toContainText('Deleted');
    await page.screenshot({ path: shot('service-packages-desktop') });

    // Settings: the default duration a new service takes.
    await page.goto(`${A}/service/settings`);
    await page.locator('[data-testid=service-settings-default_duration] input').fill('45');
    await page.locator('[data-testid=service-settings-save]').click();
    await expect(page.locator('[data-testid=service-settings-saved]')).toContainText('Settings saved.');
    await page.screenshot({ path: shot('service-settings-desktop') });
    const created = await post<{ duration_minutes: number }>(context, '/service/services', { name: named('Beard'), tax_category_key: 'service.generic' });
    expect(created.duration_minutes).toBe(45);
  } finally {
    await api(context, A, 'POST', '/service/settings', { default_duration: settings.data.default_duration });
    await context.close();
  }

  // The packages screen and its sheet on a tablet and on a phone.
  for (const [name, viewport] of Object.entries(VIEWPORTS).filter(([key]) => key !== 'desktop')) {
    const { context: small, page: phone } = await ownerPage(browser, '/service/packages', viewport);
    try {
      const view = shown(phone);
      await view.locator('[data-testid=service-packages-empty], [data-testid=service-packages-row]').first().waitFor({ state: 'visible' });
      await phone.screenshot({ path: shot(`service-packages-${name}`) });
      await phone.goto(`${A}/service/settings`);
      await expect(phone.locator('[data-testid=service-settings-default_duration]')).toBeVisible();
      await phone.screenshot({ path: shot(`service-settings-${name}`) });
    } finally {
      await small.close();
    }
  }
});
