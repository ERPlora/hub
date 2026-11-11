// flow: BASE-F05 and one create form per app of hub#1020's first stage (the walks are `expectBackAsksOnDirtyForm` and, for its own ways out, `expectWaysOutAskOnDirtyForm`, hub#1156).
import { test } from '@playwright/test';

import { expectBackAsksOnDirtyForm, expectWaysOutAskOnDirtyForm, type UnsavedFormCase } from './unsaved-back-helpers';

const CASES: UnsavedFormCase[] = [
  { app: 'sale', flow: 'SALE-F36', route: '/sale/quick-notes', add: 'sale-quick-notes-add', form: 'sale-quick-note-form', field: 'sale-quick-note-form-text' },
  { app: 'table', flow: 'TABLE-F01', route: '/table/zones', add: 'table-zones-add', form: 'table-zone-form', field: 'table-zone-form-name' },
  { app: 'kitchen', flow: 'KITCHEN-F01', route: '/kitchen/stations', add: 'kitchen-stations-primary-action', form: 'kitchen-station-form', field: 'kitchen-station-form-name' },
  { app: 'customer', flow: 'CUSTOMER-F01', route: '/customer/customers', add: 'customer-list-add', form: 'customer-create', field: 'customer-form-name' },
  { app: 'reservation', flow: 'RESERVATION-F06', route: '/reservation/reservations', add: 'reservation-list-add', form: 'reservation-form', field: 'reservation-form-guest_name' },
  { app: 'appointment', flow: 'APPOINTMENT-F01', route: '/appointment/agenda', add: 'appointment-list-add', form: 'appointment-form', field: 'appointment-form-time', value: '10:15' },
  { app: 'staff', flow: 'STAFF-F04', route: '/staff/roles', add: 'staff-roles-add', form: 'staff-role-form', field: 'staff-role-form-name' },
  { app: 'service', flow: 'SERVICE-F07', route: '/service/categories', add: 'service-categories-add', form: 'service-category-form', field: 'service-category-form-name' },
];

for (const item of CASES) {
  test(`${item.flow} ${item.app}: Android Back asks before discarding a dirty form and closes a clean one`, async ({ page }) => {
    await expectBackAsksOnDirtyForm(page, item, 'HUB-1020');
  });

  test(`${item.flow} ${item.app}: Cancel, ×, Escape and a tap outside ask before discarding a dirty form and close a clean one (hub#1156)`, async ({ page }) => {
    await expectWaysOutAskOnDirtyForm(page, item, 'HUB-1156');
  });
}
