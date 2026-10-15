// Appointments for an employee (WORKBOOK «Quién puede qué»: the employee sees and manages her own agenda).
// Her account is linked to a record of Staff; the owner books one appointment with her and one with a
// colleague. She sees only hers, books for herself from «Add appointment» (the professional comes fixed
// to her own record) and the API refuses her a booking for the colleague (403). The owner is the positive
// control: he sees both. Everything is named «E2E Apt …» and removed before and after.
import { type Browser, expect, test } from '@playwright/test';

import { A, api, type Credentials, EMPLOYEE, login, psql, shot, shown } from './helpers';
import { pick, post } from './service-helpers';

const TAG = 'E2E Apt';
const RUN = Date.now().toString(36);
const named = (label: string): string => `${TAG} ${label} ${RUN}`;

function aTuesday(): string {
  const day = new Date();
  day.setUTCDate(day.getUTCDate() + 35 + ((9 - day.getUTCDay()) % 7));
  return day.toISOString().slice(0, 10);
}
const DAY = aTuesday();

function cleanUp(): void {
  const customers = `select id from customer_customer where name like '${TAG}%'`;
  const appointments = `select id from appointment_appointment where customer_id in (${customers})`;
  const services = `select id from service_service where name like '${TAG}%'`;
  const members = `select id from staff_member where first_name like '${TAG}%'`;
  psql(
    [
      `delete from appointment_history where appointment_id in (${appointments})`,
      `delete from appointment_appointmentservice where appointment_id in (${appointments})`,
      `delete from appointment_appointment where id in (${appointments})`,
      `delete from schedule_specialdayinterval where special_day_id in (select id from schedule_specialday where name like '${TAG}%')`,
      `delete from schedule_specialday where name like '${TAG}%'`,
      `delete from service_assignment where service_id in (${services}) or member_id in (${members})`,
      `delete from service_service where name like '${TAG}%'`,
      `delete from staff_member where first_name like '${TAG}%'`,
      `delete from customer_activity where customer_id in (${customers})`,
      `delete from customer_consent where customer_id in (${customers})`,
      `delete from customer_customer where name like '${TAG}%'`,
    ].join('; '),
  );
}

test.beforeAll(cleanUp);
test.afterAll(cleanUp);

async function signedIn(browser: Browser, credentials?: Credentials) {
  const context = await browser.newContext({ baseURL: A, viewport: { width: 1280, height: 860 }, locale: 'en-US' });
  const page = await context.newPage();
  await login(page, A, '/appointment/agenda', credentials);
  return { context, page };
}

async function goToDay(page: import('@playwright/test').Page): Promise<void> {
  const calendar = shown(page).locator('[data-testid=appointment-toolbar-calendar] input');
  await calendar.fill(DAY);
  await calendar.press('Tab');
}

test('an employee sees and books her own agenda only, and the API agrees', async ({ browser }) => {
  const employee = await signedIn(browser, EMPLOYEE);
  const owner = await signedIn(browser);
  try {
    // Her account (the hub user the SaaS login made) linked to a record of Staff; a colleague beside her.
    const accounts = await api<{ rows: Array<{ user_id: number; name: string }> }>(owner.context, A, 'GET', '/staff/accounts?search=employee');
    const account = accounts.data.rows.find((row) => row.name.toLowerCase().includes('employee'));
    expect(account, JSON.stringify(accounts.data)).toBeDefined();
    const linked = await api<{ rows: Array<{ id: string; full_name: string }> }>(owner.context, A, 'GET', `/staff/members?user_id=${account!.user_id}`);
    const bea =
      linked.data.rows[0] ??
      (await post<{ id: string; full_name: string }>(owner.context, '/staff/members', {
        first_name: named('Bea'),
        last_name: 'Employee',
        user_id: account!.user_id,
      }));
    const ana = await post<{ id: string; full_name: string }>(owner.context, '/staff/members', { first_name: named('Ana'), last_name: 'Colleague' });
    const customer = await post<{ id: string; name: string }>(owner.context, '/customer/customers', {
      name: named('Marta'),
      phone: `6${String(Date.now()).slice(-8)}`,
    });
    const service = await post<{ id: string; name: string }>(owner.context, '/service/services', {
      name: named('Blow-dry'),
      price: 1500,
      duration_minutes: 30,
      tax_category_key: 'service.generic',
    });
    await post(owner.context, '/schedule/special_days', {
      date: DAY,
      name: named('Open'),
      is_closed: false,
      intervals: [{ open_time: '09:00', close_time: '18:00' }],
    });
    const booking = (staffId: string, start: string) => ({
      customer_id: customer.id,
      services: [{ service_id: service.id }],
      staff_id: staffId,
      start: `${DAY}T${start}`,
    });
    const hers = await post<{ id: string; number: string }>(owner.context, '/appointment/appointments', booking(bea.id, '10:00'));
    const theirs = await post<{ id: string; number: string }>(owner.context, '/appointment/appointments', booking(ana.id, '10:00'));

    // Positive control: the owner sees both.
    await goToDay(owner.page);
    const ownerView = shown(owner.page);
    await expect(ownerView.locator(`[data-testid=appointment-list-row][data-id="${theirs.id}"]`)).toBeVisible();
    await expect(ownerView.locator(`[data-testid=appointment-list-row][data-id="${hers.id}"]`)).toBeVisible();

    // The employee: only hers.
    await employee.page.reload();
    await goToDay(employee.page);
    const view = shown(employee.page);
    await expect(view.locator(`[data-testid=appointment-list-row][data-id="${hers.id}"]`)).toBeVisible();
    await expect(view.locator(`[data-testid=appointment-list-row][data-id="${theirs.id}"]`)).toHaveCount(0);
    await employee.page.screenshot({ path: shot('appointment-employee-list') });

    // She books for herself: the professional is fixed to her own record.
    await view.locator('[data-testid=appointment-list-add]').click();
    const form = employee.page.locator('ion-modal[data-testid=appointment-form]');
    await expect(form.locator('[data-testid=appointment-form-own]')).toHaveText('You book your own appointments.');
    await form.locator('[data-testid=customer-search-trigger]').click();
    const search = employee.page.locator('ion-modal[data-testid=customer-search-modal]');
    await search.locator('[data-testid=customer-picker-search] input').fill(customer.name);
    await search.locator(`[data-testid=customer-picker-result-${customer.id}]`).click();
    await pick(employee.page, 'appointment-form-service-add', service.name.split(' ')[2], service.name);
    const day = form.locator('[data-testid=appointment-form-day] input');
    await day.fill(DAY);
    await day.press('Tab');
    await employee.page.locator('[data-testid=appointment-slots-time]', { hasText: /^11:00\s?AM$/ }).click();
    await employee.page.locator('[data-testid=appointment-form-submit]').click();
    await expect(view.locator('[data-testid=appointment-list-row]', { hasText: customer.name })).toHaveCount(2);
    expect(psql(`select count(*) from appointment_appointment where customer_id = '${customer.id}' and staff_id = '${bea.id}'`)).toBe('2');
    await employee.page.screenshot({ path: shot('appointment-employee-booked') });

    // The API refuses her a booking for the colleague.
    const refused = await api<{ error: { code: string } }>(employee.context, A, 'POST', '/appointment/appointments', booking(ana.id, '12:00'));
    expect([refused.status, refused.data.error.code]).toEqual([403, 'permission_denied']);
  } finally {
    await employee.context.close();
    await owner.context.close();
  }
});
