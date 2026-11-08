// flow: BASE-F05 and one create form per app of hub#1020's first stage. The installed app's Back is simulated at the
// edge; every screen, form and confirmation is real. Nothing is saved: each dirty form asks, keeps what was typed on a
// second Back, closes only on «Discard changes», opens blank again and closes cleanly when untouched.
import { expect, type Page, test } from '@playwright/test';

import { A, capture, login, shown } from './helpers';
import { insideTheApp, pressBack } from './system-back-helpers';

const VIEWPORTS = [
  { label: '1440x900', width: 1440, height: 900 },
  { label: '820x1180', width: 820, height: 1180 },
  { label: '375x667', width: 375, height: 667 },
];

const CASES = [
  { app: 'sale', flow: 'SALE-F36', route: '/sale/quick-notes', add: 'sale-quick-notes-add', form: 'sale-quick-note-form', field: 'sale-quick-note-form-text' },
  { app: 'table', flow: 'TABLE-F01', route: '/table/zones', add: 'table-zones-add', form: 'table-zone-form', field: 'table-zone-form-name' },
  { app: 'kitchen', flow: 'KITCHEN-F01', route: '/kitchen/stations', add: 'kitchen-stations-primary-action', form: 'kitchen-station-form', field: 'kitchen-station-form-name' },
  { app: 'customer', flow: 'CUSTOMER-F01', route: '/customer/customers', add: 'customer-list-add', form: 'customer-create', field: 'customer-form-name' },
  { app: 'reservation', flow: 'RESERVATION-F06', route: '/reservation/reservations', add: 'reservation-list-add', form: 'reservation-form', field: 'reservation-form-guest_name' },
  { app: 'appointment', flow: 'APPOINTMENT-F01', route: '/appointment/agenda', add: 'appointment-list-add', form: 'appointment-form', field: 'appointment-form-time' },
  { app: 'staff', flow: 'STAFF-F04', route: '/staff/roles', add: 'staff-roles-add', form: 'staff-role-form', field: 'staff-role-form-name' },
  { app: 'service', flow: 'SERVICE-F07', route: '/service/categories', add: 'service-categories-add', form: 'service-category-form', field: 'service-category-form-name' },
];

const question = (page: Page) => page.locator('ion-modal.ep-confirm-dialog').last();

for (const item of CASES) {
  test(`${item.flow} ${item.app}: Android Back asks before discarding a dirty form and closes a clean one`, async ({ page }) => {
    await login(page, A);
    await insideTheApp(page);
    await page.goto(item.route);
    const add = shown(page).locator(`[data-testid=${item.add}]`);
    await expect(add).toBeVisible();
    const form = page.locator(`ion-modal[data-testid=${item.form}]`);
    const field = form.locator(`[data-testid=${item.field}] input`);
    const value = item.field.endsWith('time') ? '10:15' : 'E2E unsaved';

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await add.click();
      await expect(form).toBeVisible();
      await field.fill(value);
      await pressBack(page);
      const asked = question(page);
      await expect(asked).toBeVisible();
      await expect(asked).toContainText(/Discard changes\?|¿Descartar los cambios\?/);
      await expect(form).toBeVisible();
      await capture(page, `HUB-1020-${item.app}-${viewport.label}`);

      await pressBack(page);
      await expect(asked).toBeHidden();
      await expect(form).toBeVisible();
      await expect(field).toHaveValue(value);

      await pressBack(page);
      await asked.locator('.ep-form-modal__submit').click();
      await expect(form).toBeHidden();

      await add.click();
      await expect(form).toBeVisible();
      await expect(field).toHaveValue('');
      await pressBack(page);
      await expect(form).toBeHidden();
      await expect(page.locator('ion-modal.ep-confirm-dialog:visible')).toHaveCount(0);
    }
  });
}
