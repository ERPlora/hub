// APPOINTMENT-F01, F04, F14, F22: the booking panel. «New appointment» asks for the Customer (Customers'
// own search, which also creates a card), one or more Services, the Professional (only who does them all),
// the Day and the Time (with the free times), the Min. (the services' sum unless typed) and the notes;
// «Add appointment» books it. An overlap asks first («Book anyway» / «Pick another time»); a refusal goes on
// top, a bad field under it, and what was typed stays. «Edit appointment» sends only what changed, asks
// «This appointment only» / «This and all following» for a series and shows the history below.
// CUSTOMER-F25: a customer who is not there yet is created from the same search («+ New customer «…»»,
// walk-in) and stays chosen, and what was already chosen for the appointment is kept, also when it fails.
import { Combo, ConfirmDialog } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import type { AppointmentOut } from '../operations';
import { click, ionValue, mountAppointment, page, settle } from '../__tests__/mount-appointment';
import AppointmentFormModal from './AppointmentFormModal.vue';
import AppointmentHistory from './AppointmentHistory.vue';
import FreeSlots from './FreeSlots.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

const BOOKED: AppointmentOut = {
  id: 'a1',
  number: 'APT-20261019-0001',
  customer_id: 'c9',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-10-19T10:00:00+02:00',
  end: '2026-10-19T10:30:00+02:00',
  duration_minutes: 30,
  status: 'confirmed',
  source: 'counter',
  services: [{ service_id: 'cut', name: 'Haircut', price: 2000, duration_minutes: 30 }],
  service_names: 'Haircut',
  total: 2000,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  customer_phone: '+34600111222',
  customer_email: '',
  notes: '',
  internal_notes: '',
  cancelled_at: null,
  cancellation_reason: '',
  cancelled_by_customer: false,
  charged_at: null,
  created_at: '2026-10-14T10:00:00+02:00',
  updated_at: '2026-10-14T10:00:00+02:00',
  start_date_label: 'Monday, October 19, 2026',
  start_time_label: '10:00',
};

const SERVICES = page([
  { id: 'cut', name: 'Haircut', price: 2000, duration_minutes: 30, is_bookable: true },
  { id: 'colour', name: 'Colour', price: 4500, duration_minutes: 60, is_bookable: true },
]);

/** What the panel reads when it opens: the services for sale, the professionals and who does what. */
const READS: Record<string, [number, unknown]> = {
  '/api/service/services/for_sale': [200, SERVICES],
  '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }])],
  '/api/service/assignments/eligible': [200, page([])],
};

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(AppointmentFormModal, {
    props: { open: false, appointment: null, businessNow: '2026-10-14T12:00', ...props },
    locale,
  });
  m.answerBy(READS);
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`appointment-form-${name}`) as Control;
  const submit = () => m.inDoc('appointment-form-submit') as Control;
  const combos = () => m.wrapper.findAllComponents(Combo);
  const servicePicker = () => combos().find((c) => c.props('testid') === 'appointment-form-service-add')!;
  const staffPicker = () => combos().find((c) => c.props('testid') === 'appointment-form-staff')!;
  async function addService(id: string, label: string) {
    await (servicePicker().props('search') as (q: string) => Promise<unknown>)('');
    servicePicker().vm.$emit('update:modelValue', { id, label });
    await settle();
  }
  async function pickStaff(id: string, label: string) {
    staffPicker().vm.$emit('update:modelValue', { id, label });
    await settle();
  }
  async function pickCustomer() {
    m.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', {
      customer_id: 'c1',
      customer_name: 'Lucía Pérez',
      customer_tax_id: '',
      customer_address: '',
      customer_country: '',
    });
    await settle();
  }
  return { ...m, field, submit, servicePicker, staffPicker, addService, pickStaff, pickCustomer };
}

async function fillNew(s: Awaited<ReturnType<typeof setup>>) {
  await s.pickCustomer();
  await s.addService('cut', 'Haircut');
  await s.addService('colour', 'Colour');
  await s.pickStaff('s1', 'Ana López');
  await ionValue(s.field('day'), '2026-10-19', 'ionInput');
  await ionValue(s.field('time'), '10:00', 'ionInput');
}

describe('AppointmentFormModal: New appointment', () => {
  it('asks for customer, services, professional, day, time and minutes, as the old panel', async () => {
    const s = await setup();
    expect(s.inDoc('appointment-form')?.getAttribute('aria-label')).toBe('New appointment');
    expect([s.field('day').label, s.field('time').label, s.field('minutes').label]).toEqual(['Day', 'Time', 'Min.']);
    expect(s.staffPicker().props('label')).toBe('Professional');
    expect(s.submit().textContent).toContain('Add appointment');
    expect(s.submit().disabled).toBe(true);
  });

  it('books with the services in order, the professional and the wall-clock time; the minutes are their sum', async () => {
    const s = await setup();
    await fillNew(s);
    expect(s.field('minutes').value).toBe('90');
    expect(s.wrapper.findComponent(FreeSlots).props()).toMatchObject({ date: '2026-10-19', serviceIds: ['cut', 'colour'], staffId: 's1' });
    s.answer(201, BOOKED);
    await click(s.submit());
    const sent = s.sent().filter((call) => call.path === '/api/appointment/appointments');
    expect(sent).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/appointments',
        query: {},
        body: {
          customer_id: 'c1',
          services: [{ service_id: 'cut' }, { service_id: 'colour' }],
          staff_id: 's1',
          start: '2026-10-19T10:00',
          notes: '',
          internal_notes: '',
          confirm_overlap: false,
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    expect(s.wrapper.emitted('saved')?.[0]).toEqual([BOOKED]);
  });

  it('the minutes and the total are the professional’s own for each service (Services · «Who does it»)', async () => {
    const s = await setup();
    const eligible = (memberId: string, fullName: string, duration: number, price: number, own: boolean) => ({
      member_id: memberId,
      full_name: fullName,
      color: '',
      booking_buffer: 0,
      custom_duration: own ? duration : null,
      custom_price: own ? price : null,
      is_primary: own,
      duration,
      price,
    });
    s.net.onApi(({ url }) => {
      const asked = new URL(url, 'http://a.localhost');
      if (asked.pathname === '/api/service/services/for_sale') return Response.json(SERVICES);
      if (asked.pathname === '/api/staff/members') return Response.json(page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }]));
      if (asked.pathname === '/api/service/assignments/eligible' && asked.searchParams.get('service_id') === 'cut') {
        return Response.json(page([eligible('s1', 'Ana López', 45, 2500, true), eligible('s2', 'Bea Ruiz', 30, 2000, false)]));
      }
      return Response.json(page([]));
    });
    await fillNew(s);
    // Ana does a haircut in 45 minutes for €25.00; the colour, nobody's own: the catalog's.
    expect(s.field('minutes').value).toBe('105');
    expect(s.inDoc('appointment-form-total')?.textContent).toContain('€70.00');
    await s.pickStaff('s2', 'Bea Ruiz');
    expect(s.field('minutes').value).toBe('90');
    expect(s.inDoc('appointment-form-total')?.textContent).toContain('€65.00');
    // Minutes typed by hand stay.
    await ionValue(s.field('minutes'), '50', 'ionInput');
    await s.pickStaff('s1', 'Ana López');
    expect(s.field('minutes').value).toBe('50');
  });

  it('sends the minutes only when typed, and a free time fills the time', async () => {
    const s = await setup();
    await fillNew(s);
    await ionValue(s.field('minutes'), '75', 'ionInput');
    s.wrapper.findComponent(FreeSlots).vm.$emit('pick', '11:15');
    await settle();
    expect(s.field('time').value).toBe('11:15');
    s.answer(201, BOOKED);
    await click(s.submit());
    const body = s.sent().find((call) => call.path === '/api/appointment/appointments')?.body as Record<string, unknown>;
    expect([body.start, body.duration_minutes]).toEqual(['2026-10-19T11:15', 75]);
  });

  it('asks before booking on top of another appointment, and «Book anyway» books', async () => {
    const s = await setup();
    await fillNew(s);
    const message = 'This time overlaps with APT-1 Pepa (10:00–10:30). Book it anyway?';
    s.answer(409, { error: { code: 'appointment.overlap_needs_confirmation', message } });
    await click(s.submit());
    const dialog = s.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === 'appointment-overlap')!;
    expect([dialog.props('open'), dialog.props('title'), dialog.props('message')]).toEqual([true, 'Overlapping appointment', message]);
    expect([dialog.props('confirmLabel'), dialog.props('cancelLabel')]).toEqual(['Book anyway', 'Pick another time']);
    s.answer(201, BOOKED);
    dialog.vm.$emit('confirm');
    await settle();
    const bodies = s.sent().filter((call) => call.path === '/api/appointment/appointments').map((call) => (call.body as Record<string, unknown>).confirm_overlap);
    expect(bodies).toEqual([false, true]);
  });

  it('a refusal goes on top and a bad field under it, and what was typed stays', async () => {
    const s = await setup();
    await fillNew(s);
    s.answer(409, { error: { code: 'appointment.outside_schedule', message: 'That time is outside the business’s opening hours.' } });
    await click(s.submit());
    expect(s.inDoc('appointment-form-error')?.textContent).toContain('outside the business’s opening hours');
    s.answer(422, { error: { code: 'appointment.invalid_local_time', message: 'x', fields: { start: 'That time does not exist.' } } });
    await click(s.submit());
    expect(s.field('time').errorText).toBe('That time does not exist.');
    expect(s.field('time').value).toBe('10:00');
  });

  it('warns that the time is in the past', async () => {
    const s = await setup();
    await fillNew(s);
    expect(s.inDoc('appointment-form-past')).toBeNull();
    await ionValue(s.field('day'), '2026-10-13', 'ionInput');
    expect(s.inDoc('appointment-form-past')?.textContent).toContain('starts in the past');
  });

  it('comes with the professional and the time of the tapped slot', async () => {
    const s = await setup({ preset: { day: '2026-10-19', time: '16:30', staffId: 's2', staffName: 'Bea Ruiz' } });
    expect(s.staffPicker().props('modelValue')).toEqual({ id: 's2', label: 'Bea Ruiz' });
    expect([s.field('day').value, s.field('time').value]).toEqual(['2026-10-19', '16:30']);
  });

  it('an employee books for herself only', async () => {
    const s = await setup({ ownStaff: { id: 's2', name: 'Bea Ruiz' } });
    expect(s.staffPicker().props('modelValue')).toEqual({ id: 's2', label: 'Bea Ruiz' });
    expect(s.staffPicker().props('disabled')).toBe(true);
    expect(s.inDoc('appointment-form-own')?.textContent).toBe('You book your own appointments.');
  });

  it('a professional who does not do the services is taken away with a warning', async () => {
    const s = await setup();
    await s.pickStaff('s1', 'Ana López');
    s.answerBy({
      '/api/service/services/for_sale': [200, SERVICES],
      '/api/staff/members': [200, page([{ id: 's1', full_name: 'Ana López' }, { id: 's2', full_name: 'Bea Ruiz' }])],
      '/api/service/assignments/eligible': [200, page([{ member_id: 's2', full_name: 'Bea Ruiz' }])],
    });
    await s.addService('colour', 'Colour');
    await settle();
    expect(s.staffPicker().props('modelValue')).toBeNull();
    expect(s.inDoc('appointment-form-staff-warning')?.textContent).toContain('does not perform these services');
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.inDoc('appointment-form')?.getAttribute('aria-label')).toBe('Nueva cita');
    expect([s.field('day').label, s.field('time').label]).toEqual(['Día', 'Hora']);
    expect(s.submit().textContent).toContain('Añadir cita');
  });
});

describe('AppointmentFormModal: Edit appointment', () => {
  it('comes filled in, sends only what changed and shows the history below', async () => {
    const s = await setup({ appointment: BOOKED });
    expect(s.inDoc('appointment-form')?.getAttribute('aria-label')).toBe('Edit appointment');
    expect([s.field('day').value, s.field('time').value, s.field('minutes').value]).toEqual(['2026-10-19', '10:00', '30']);
    expect(s.wrapper.findComponent(AppointmentHistory).props('appointmentId')).toBe('a1');
    expect(s.wrapper.findComponent(FreeSlots).props('excludeId')).toBe('a1');
    await ionValue(s.field('time'), '11:00', 'ionInput');
    await ionValue(s.field('notes'), 'Bring photo', 'ionInput');
    s.answer(200, { ...BOOKED, start: '2026-10-19T11:00:00+02:00' });
    await click(s.submit());
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/appointments/update',
        query: {},
        body: { id: 'a1', start: '2026-10-19T11:00', notes: 'Bring photo', confirm_overlap: false },
      },
    ]);
  });

  it('a series occurrence asks the scope; «This and all following» edits the series from its date', async () => {
    const s = await setup({ appointment: { ...BOOKED, recurring_id: 'r1', occurrence_date: '2026-10-19' } });
    await ionValue(s.field('time'), '12:00', 'ionInput');
    await click(s.submit());
    const scope = s.inDoc('appointment-scope');
    expect(scope?.textContent).toContain('This appointment is part of a repeating series.');
    s.answer(200, { recurring: {}, moved: 3, cancelled: 0, locked: 1, skipped: [], booked: 0 });
    await click(s.inDoc('appointment-scope-following'));
    expect(s.sent().filter((call) => call.method === 'POST')).toEqual([
      {
        method: 'POST',
        path: '/api/appointment/recurring/update',
        query: {},
        body: { id: 'r1', from_date: '2026-10-19', time: '12:00' },
      },
    ]);
    // appointments#293: only what happened, never «0 cancelled».
    expect(s.wrapper.emitted('outcome')?.[0]).toEqual(['3 appointments moved · 1 left alone because they are already charged']);
  });
});

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
    await s.addService('cut', 'Haircut');
    await s.addService('colour', 'Colour');
    await s.pickStaff('s1', 'Ana López');
    await ionValue(s.field('day'), '2026-10-19', 'ionInput');
    await ionValue(s.field('time'), '10:00', 'ionInput');
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
    expect([s.field('day').value, s.field('time').value, s.field('minutes').value]).toEqual(['2026-10-19', '10:00', '90']);
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
