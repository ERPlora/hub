// flow: ONLINE_BOOKING-F08 — the customer's phone and email on an online booking reach only whoever sees the customers'
// contact details (BASE-F119). The employee holds that permission (base/apps.py): in her inbox, at every width, the
// search box offers the phone, finds her own booking by part of it and shows the customer with it, and the booking
// answers both. A role that opens the inbox without the permission does not exist yet in a browser: what it gets is
// held by the server's tests (apps/online_booking/tests/test_queries_contact.py) and the page's (Vitest).
import { expect, test } from '@playwright/test';

import { aMonday } from './appointment-helpers';
import { spanishMobile } from './customer-helpers';
import { A, api, capture, EMPLOYEE, saveSessionForTheSweep, shown } from './helpers';
import { cast, keepTheBusiness } from './online-booking-helpers';
import { FLOW_VIEWPORTS, ownerPage, post } from './service-helpers';
import { recordOf } from './staff-helpers';
import { signedIn } from './task-helpers';

const TAG = 'E2E OBContact';

type Contact = { customer_name: string; customer_phone: string | null; customer_email: string | null };

keepTheBusiness(TAG);

FLOW_VIEWPORTS.forEach((vp, index) => {
  test(`the employee's inbox finds and shows her customer by phone at ${vp.label}px`, async ({ browser }) => {
    const owner = await ownerPage(browser, '/online_booking/bookings', vp);
    const employee = await signedIn(browser, '/online_booking/bookings', EMPLOYEE, vp);
    try {
      await saveSessionForTheSweep(employee.context);
      const day = aMonday(index + 3);
      const { service } = await cast(owner.context, `${TAG} ${vp.label}`, day);
      const bea = await recordOf(owner.context, EMPLOYEE.email, `${TAG} Bea`);
      await post(owner.context, '/service/assignments/assign', { service_id: service.id, member_id: bea.id }, 200);
      const mobile = spanishMobile();
      const email = `ob.contact.${vp.label}.${Date.now().toString(36)}@example.com`;
      const customer = await post<{ id: string; name: string }>(owner.context, '/customer/customers', { name: `${TAG} Marta ${vp.label}`, phone: mobile, email });
      const booked = await post<{ id: string; number: string }>(owner.context, '/appointment/appointments', {
        customer_id: customer.id,
        services: [{ service_id: service.id }],
        staff_id: bea.id,
        start: `${day}T10:00`,
        source: 'online',
      });

      const detail = await api<Contact>(employee.context, A, 'GET', `/online_booking/bookings/detail?id=${booked.id}`);
      expect([detail.status, detail.data]).toMatchObject([200, { customer_name: customer.name, customer_phone: `+34${mobile}`, customer_email: email }]);

      const search = shown(employee.page).locator('[data-testid=ob-bookings-search] input');
      await expect(search).toHaveAttribute('placeholder', 'Search no., customer, phone, service…');
      await search.fill(mobile.slice(-6));
      const row = shown(employee.page).locator('[data-testid=ob-bookings-row]', { hasText: booked.number });
      await expect(row).toContainText(customer.name);
      await expect(row).toContainText(`+34${mobile}`);
      await capture(employee.page, `online-booking-contact-${vp.label}`);
    } finally {
      await employee.context.close();
      await owner.context.close();
    }
  });
});
