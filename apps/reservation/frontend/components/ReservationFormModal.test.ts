// RESERVATION-F06, F08, F23: the booking panel. «New reservation» asks for the Customer (Customers' own
// search, which also creates a card) or the guest's Name and Phone, the Date, the Time, the Party, the
// Duration, the Table (the free ones at that time, the ones that fit first), where it was booked and the
// notes; «Reserve» books it. A full slot asks first («Book anyway»); a refusal goes on top, a bad field
// under it, and what was typed stays. «Edit reservation» sends only what changed (or `no_table`), and a
// finished reservation only changes its notes.
import { Combo, ConfirmDialog } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import { click, ionValue, mountReservation, settle } from '../__tests__/mount-reservation';
import { freeTable, reservationRow } from '../__tests__/rows';
import ReservationFormModal from './ReservationFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

const TABLES = {
  rows: [
    freeTable(),
    freeTable({ id: 't2', number: '2', label: '2 (Bar)', zone_name: 'Bar', capacity: 2, fits: false }),
    freeTable({ id: 't9', number: '9', label: '9 (Terrace)', free: false, taken_from: '20:00:00', taken_until: '22:00:00' }),
  ],
};

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(ReservationFormModal, {
    props: { open: false, reservation: null, day: '2026-10-15', ...props },
    locale,
  });
  m.answerBy({
    '/api/reservation/availability/tables': [200, TABLES],
    '/api/customer/customers/detail': [200, { id: 'c1', name: 'Lucía Pérez', phone: '+34600999888', email: 'lucia@x.es' }],
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`reservation-form-${name}`) as Control;
  const submit = () => m.inDoc('reservation-form-submit') as Control;
  const tablePicker = () => m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === 'reservation-form-table')!;
  const bodies = (path: string) => m.sent().filter((call) => call.path === path).map((call) => call.body);
  return { ...m, field, submit, tablePicker, bodies };
}

async function fillNew(s: Awaited<ReturnType<typeof setup>>) {
  await ionValue(s.field('guest_name'), 'Ana García', 'ionInput');
  await ionValue(s.field('guest_phone'), '600 111 222', 'ionInput');
  await ionValue(s.field('time'), '21:00', 'ionInput');
  await ionValue(s.field('party_size'), '4', 'ionInput');
}

describe('ReservationFormModal: New reservation', () => {
  it('asks for the guest, the date and time, the party, the table and the notes, as the old panel and more', async () => {
    const s = await setup();
    expect(s.inDoc('reservation-form')?.getAttribute('aria-label')).toBe('New reservation');
    expect([s.field('guest_name').label, s.field('guest_phone').label, s.field('date').label, s.field('time').label, s.field('party_size').label]).toEqual([
      'Guest',
      'Phone',
      'Date',
      'Time',
      'Party',
    ]);
    expect(s.field('date').value).toBe('2026-10-15');
    expect(s.field('party_size').value).toBe('2');
    expect(s.wrapper.findComponent(CustomerSearch).exists()).toBe(true);
    expect(s.tablePicker().props('label')).toBe('Table');
    expect(s.submit().textContent).toContain('Reserve');
    expect(s.submit().disabled).toBe(true);
  });

  it('offers the free tables at that time, the ones that fit first, saying their seats and zone', async () => {
    const s = await setup();
    await fillNew(s);
    const options = await (s.tablePicker().props('search') as (q: string) => Promise<unknown>)('ter');
    expect(s.sent().find((call) => call.path === '/api/reservation/availability/tables')?.query).toEqual({
      date: '2026-10-15',
      time: '21:00',
      party_size: '4',
      search: 'ter',
    });
    expect(options).toEqual([
      { id: 't5', label: '5 (Terrace)', hint: '4 seats · Terrace' },
      { id: 't2', label: '2 (Bar)', hint: '2 seats · Bar · too small for the party' },
    ]);
  });

  it('books the guest with the table and the wall-clock time', async () => {
    const s = await setup();
    await fillNew(s);
    s.tablePicker().vm.$emit('update:modelValue', { id: 't5', label: '5 (Terrace)' });
    await ionValue(s.field('notes'), 'Birthday', 'ionInput');
    const booked = reservationRow();
    s.answer(201, booked);
    await click(s.submit());
    expect(s.bodies('/api/reservation/reservations')).toEqual([
      {
        guest_name: 'Ana García',
        guest_phone: '600 111 222',
        guest_email: '',
        date: '2026-10-15',
        time: '21:00',
        party_size: 4,
        table_id: 't5',
        source: 'phone',
        notes: 'Birthday',
        internal_notes: '',
        overbook: false,
      },
    ]);
    expect(s.wrapper.emitted('saved')?.[0]).toEqual([booked]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a customer picked from Customers fills the guest and books with her card', async () => {
    const s = await setup();
    s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', {
      customer_id: 'c1',
      customer_name: 'Lucía Pérez',
      customer_tax_id: '',
      customer_address: '',
      customer_country: '',
    });
    await settle();
    expect([s.field('guest_name').value, s.field('guest_phone').value, s.field('guest_email').value]).toEqual([
      'Lucía Pérez',
      '+34600999888',
      'lucia@x.es',
    ]);
    await ionValue(s.field('time'), '21:00', 'ionInput');
    s.answer(201, reservationRow());
    await click(s.submit());
    expect(s.bodies('/api/reservation/reservations')[0]).toMatchObject({ customer_id: 'c1', guest_name: 'Lucía Pérez' });
  });

  it('warns that the chosen table is small for the party, and still books it', async () => {
    const s = await setup();
    await fillNew(s);
    await (s.tablePicker().props('search') as (q: string) => Promise<unknown>)('');
    s.tablePicker().vm.$emit('update:modelValue', { id: 't2', label: '2 (Bar)' });
    await settle();
    expect(s.inDoc('reservation-form-small')?.textContent).toContain('Table 2 (Bar) has 2 seats for 4 guests.');
  });

  it('asks before filling a full slot, and «Book anyway» books it', async () => {
    const s = await setup();
    await fillNew(s);
    const message = 'That time slot is fully booked for that date.';
    const hint = 'Send overbook as true to book this full slot anyway.';
    s.answer(409, { error: { code: 'reservation.no_capacity', message, fields: { time: message, overbook: hint } } });
    await click(s.submit());
    const confirm = s.wrapper.findAllComponents(ConfirmDialog).find((c) => c.props('testid') === 'reservation-overbook')!;
    expect([confirm.props('open'), confirm.props('message')]).toEqual([true, `${message} Book it anyway?`]);
    s.answer(201, reservationRow());
    confirm.vm.$emit('confirm');
    await settle();
    expect(s.bodies('/api/reservation/reservations').map((body) => (body as { overbook: boolean }).overbook)).toEqual([false, true]);
    expect(s.wrapper.emitted('saved')).toHaveLength(1);
  });

  it('a full slot the server does not let overbook is a plain refusal, on top', async () => {
    const s = await setup();
    await fillNew(s);
    const message = 'That time slot is fully booked for that date.';
    s.answer(409, { error: { code: 'reservation.no_capacity', message, fields: { time: message } } });
    await click(s.submit());
    const confirm = s.wrapper.findAllComponents(ConfirmDialog).find((c) => c.props('testid') === 'reservation-overbook')!;
    expect(confirm.props('open')).toBe(false);
    expect(s.inDoc('reservation-form-error')?.textContent).toContain(message);
  });

  it('puts a refusal on top and a bad field under it, keeping what was typed', async () => {
    const s = await setup();
    await fillNew(s);
    const message = 'This business requires a phone number for every reservation.';
    s.answer(409, { error: { code: 'reservation.phone_required', message, fields: { guest_phone: message } } });
    await click(s.submit());
    expect(s.inDoc('reservation-form-error')?.textContent).toContain(message);
    expect(s.field('guest_phone').errorText).toBe(message);
    expect(s.field('guest_name').value).toBe('Ana García');
  });
});

describe('ReservationFormModal: Edit reservation', () => {
  it('sends only what changed, and can leave it without a table', async () => {
    const s = await setup({ reservation: reservationRow({ status: 'confirmed' }) });
    expect(s.inDoc('reservation-form')?.getAttribute('aria-label')).toBe('Edit reservation');
    expect([s.field('time').value, s.field('party_size').value, s.tablePicker().props('modelValue')]).toEqual([
      '21:00',
      '4',
      { id: 't5', label: '5 (Terrace)' },
    ]);
    expect(s.wrapper.findComponent(CustomerSearch).exists()).toBe(false);
    await ionValue(s.field('time'), '21:30', 'ionInput');
    s.tablePicker().vm.$emit('update:modelValue', null);
    s.answer(200, reservationRow({ time: '21:30:00', table_id: null }));
    await click(s.submit());
    expect(s.bodies('/api/reservation/reservations/update')).toEqual([{ id: 'r1', time: '21:30', no_table: true, overbook: false }]);
  });

  it('a seated reservation only changes its notes', async () => {
    const s = await setup({ reservation: reservationRow({ status: 'seated' }) });
    expect(s.inDoc('reservation-form-notes-only')?.textContent).toContain('This reservation is seated: only its notes can change.');
    expect([s.field('time').disabled, s.field('party_size').disabled, s.tablePicker().props('disabled')]).toEqual([true, true, true]);
    await ionValue(s.field('internal_notes'), 'VIP', 'ionInput');
    s.answer(200, reservationRow({ status: 'seated', internal_notes: 'VIP' }));
    await click(s.submit());
    expect(s.bodies('/api/reservation/reservations/update')).toEqual([{ id: 'r1', internal_notes: 'VIP', overbook: false }]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect([s.field('guest_name').label, s.field('party_size').label, s.submit().textContent?.trim()]).toEqual(['Cliente', 'Pax', 'Reservar']);
  });
});
