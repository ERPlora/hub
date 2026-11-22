// flow: APPOINTMENT-F22, APPOINTMENT-F27 — the customer's phone and email on an appointment reach only whoever sees the
// customers' contact details (BASE-F119). The employee holds that permission (base/apps.py), so her own appointment
// answers them, and editing its notes keeps them, at every width. A role that opens the agenda without the permission
// does not exist yet in a browser: what it gets is held by the server's tests
// (apps/appointment/tests/test_customer_contact.py).
import { expect, test } from '@playwright/test';

import { aMonday, employeesRecord, salonCleanUp } from './appointment-helpers';
import { cardDeletes, FLOW_VIEWPORTS, spanishMobile } from './customer-helpers';
import { pickDay } from './date-time-fields';
import { signedIn } from './flow-helpers';
import { A, api, capture, EMPLOYEE, psql, shown } from './helpers';
import { post } from './service-helpers';

const TAG = 'E2E AptContact';
const DAY = aMonday(2);

type Contact = { customer_name: string; customer_phone: string | null; customer_email: string | null; notes: string };

function cleanUp(): void {
  psql([...salonCleanUp(TAG), ...cardDeletes(`select id from customer_customer where name like '${TAG}%'`)].join('; '));
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

for (const [index, viewport] of FLOW_VIEWPORTS.entries()) {
  test(`the employee's own appointment keeps the customer's phone and email at ${viewport.label}px`, async ({ browser }) => {
    const owner = await signedIn(browser, '/appointment/agenda', viewport);
    const employee = await signedIn(browser, '/appointment/agenda', viewport, EMPLOYEE);
    if (process.env.E2E_SAVE_STORAGE_STATE) await employee.context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    try {
      const bea = await employeesRecord(owner.context, `${TAG} Bea`);
      const run = `${viewport.label}${Date.now().toString(36)}`;
      const phone = `+34${spanishMobile()}`;
      const email = `apt.contact.${run}@example.com`;
      const customer = await post<{ id: string; name: string }>(owner.context, '/customer/customers', { name: `${TAG} Marta ${run}`, phone, email });
      const service = await post<{ id: string }>(owner.context, '/service/services', {
        name: `${TAG} Corte ${run}`,
        price: 2000,
        duration_minutes: 30,
        tax_category_key: 'service.generic',
      });
      if (index === 0) {
        await post(owner.context, '/schedule/special_days', { date: DAY, name: `${TAG} Abierto`, is_closed: false, intervals: [{ open_time: '09:00', close_time: '18:00' }] });
      }
      const booked = await post<{ id: string }>(owner.context, '/appointment/appointments', {
        customer_id: customer.id,
        services: [{ service_id: service.id }],
        staff_id: bea.id,
        start: `${DAY}T${10 + index}:00`,
      });

      const detail = async () => (await api<Contact>(employee.context, A, 'GET', `/appointment/appointments/detail?id=${booked.id}`)).data;
      expect(await detail()).toMatchObject({ customer_name: customer.name, customer_phone: phone, customer_email: email });
      const edited = await api<Contact>(employee.context, A, 'POST', '/appointment/appointments/update', { id: booked.id, notes: 'Bring the photo' });
      expect([edited.status, edited.data.customer_phone, edited.data.customer_email]).toEqual([200, phone, email]);
      expect(psql(`select customer_phone || ' ' || customer_email from appointment_appointment where id = '${booked.id}'`)).toBe(`${phone} ${email}`);

      await pickDay(employee.page, shown(employee.page).locator('[data-testid=appointment-toolbar-calendar]'), DAY);
      const row = shown(employee.page).locator(`[data-testid=appointment-list-row][data-id="${booked.id}"]`);
      await expect(row).toContainText(customer.name);
      await capture(employee.page, `appointment-contact-agenda-${viewport.label}`);
    } finally {
      await employee.context.close();
      await owner.context.close();
    }
  });
}
