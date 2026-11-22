// CUSTOMER-F25: a customer who is not there yet is created from the same search («+ New customer «…»»,
// walk-in) and stays chosen, and what was already chosen for the appointment is kept, also when it fails.
import { describe, expect, it } from 'vitest';

import { BOOKED, fillChoices, READS, setup, type Control } from '../__tests__/appointment-form';
import { click, ionValue, settle } from '../__tests__/mount-appointment';

describe('AppointmentFormModal: a new customer without leaving the agenda (CUSTOMER-F25)', () => {
  // The card the server gives back for «Marta Ruiz»: walk-in, no tax details.
  const MARTA = {
    id: 'c9',
    name: 'Marta Ruiz',
    phone: '+34600999888',
    source: 'walk_in',
    company_name: '',
    tax_id: '',
    address: '',
    postal_code: '',
    city: '',
    country: '',
  };

  /** «New appointment» with the services, the professional, the day and the time chosen, and the
   *  customer search open on «+ New customer «Marta Ruiz»» with a phone typed; `create` answers it. */
  async function quickAddReady(create: [number, unknown]) {
    const s = await setup();
    s.answerBy({
      ...READS,
      '/api/customer/customers/by_phone': [200, { rows: [] }],
      '/api/customer/customers': create,
      '/api/appointment/appointments': [201, BOOKED],
    });
    await fillChoices(s);
    await click(s.inDoc('customer-search-trigger'));
    await ionValue(s.inDoc('customer-picker-search'), 'Marta Ruiz', 'ionInput');
    await click(s.inDoc('customer-search-quick-add'));
    await ionValue(s.inDoc('customer-search-quick-phone'), '600 999 888', 'ionInput');
    return s;
  }

  /** The services, the professional, the day, the time and the minutes chosen before are still there. */
  function expectChoicesKept(s: Awaited<ReturnType<typeof setup>>) {
    expect([s.inDoc('appointment-form-service-cut'), s.inDoc('appointment-form-service-colour')].every(Boolean)).toBe(true);
    expect(s.staffPicker().props('modelValue')).toEqual({ id: 's1', label: 'Ana López' });
    expect([s.kept('day'), s.kept('time'), s.field('minutes').value]).toEqual(['2026-10-19', '10:00', '90']);
  }

  /** «Create and assign»: its submit button sends the quick form (an `ion-button` only does that once
   *  attached to a document, which this mount is not; the e2e taps the real one). */
  async function createAndAssign(s: Awaited<ReturnType<typeof setup>>) {
    expect((s.inDoc('customer-search-quick-submit') as Control).disabled).toBe(false);
    (s.inDoc('customer-search-quick-form') as HTMLFormElement).requestSubmit();
    await settle();
  }

  const customerCalls = (s: Awaited<ReturnType<typeof setup>>) => s.sent().filter((call) => call.path.startsWith('/api/customer/'));

  it('creates the card (walk-in) from the search, leaves it chosen and books the appointment with it', async () => {
    const s = await quickAddReady([201, MARTA]);
    await createAndAssign(s);
    expect(customerCalls(s)).toEqual([
      { method: 'GET', path: '/api/customer/customers/by_phone', query: { phone: '600 999 888' }, body: undefined },
      { method: 'POST', path: '/api/customer/customers', query: {}, body: { name: 'Marta Ruiz', phone: '600 999 888', source: 'walk_in' } },
    ]);
    // The search closes and the appointment's «Customer» is the new card.
    expect(s.inDoc('customer-search-quick-form')).toBeNull();
    expect(s.inDoc('customer-search-trigger')?.textContent?.trim()).toBe('Marta Ruiz');
    expectChoicesKept(s);
    expect(s.submit().disabled).toBe(false);
    await click(s.submit());
    const booked = s.sent().find((call) => call.path === '/api/appointment/appointments');
    expect(booked?.body).toMatchObject({
      customer_id: 'c9',
      services: [{ service_id: 'cut' }, { service_id: 'colour' }],
      staff_id: 's1',
      start: '2026-10-19T10:00',
    });
  });

  it('a card that cannot be created says why inside the search; what was chosen and typed stays, and a retry assigns her', async () => {
    const s = await quickAddReady([500, { error: { code: 'internal_error', message: 'Internal error' } }]);
    await createAndAssign(s);
    expect(s.inDoc('customer-search-quick-error')?.textContent?.trim()).toBe('Internal error');
    expect(s.inDoc('customer-search-trigger')?.textContent?.trim()).toBe('Assign customer');
    const typed = (id: string) => (s.inDoc(id) as Control).value;
    expect([typed('customer-search-quick-name'), typed('customer-search-quick-phone')]).toEqual(['Marta Ruiz', '600 999 888']);
    expectChoicesKept(s);
    expect(s.submit().disabled).toBe(true);

    s.answerBy({
      ...READS,
      '/api/customer/customers/by_phone': [200, { rows: [] }],
      '/api/customer/customers': [201, MARTA],
    });
    await createAndAssign(s);
    expect(s.inDoc('customer-search-trigger')?.textContent?.trim()).toBe('Marta Ruiz');
    expectChoicesKept(s);
    expect(s.submit().disabled).toBe(false);
  });
});
