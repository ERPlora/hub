// The booking panel and the guest's phone and email (RESERVATION-F06, F08, BASE-F119): what reaches the panel without
// them (null, to whoever does not see the customers' contact details) is neither shown nor sent, so saving never
// empties them; the server keeps them, or copies the picked card's.
import { describe, expect, it } from 'vitest';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import { click, ionValue, mountReservation, settle, WITHOUT_CONTACT } from '../__tests__/mount-reservation';
import { reservationRow } from '../__tests__/rows';
import ReservationFormModal from './ReservationFormModal.vue';

const LUCIA = { customer_id: 'c1', customer_name: 'Lucía Pérez', customer_tax_id: '', customer_address: '', customer_country: '' };

async function setup(props: Record<string, unknown>) {
  const m = await mountReservation(ReservationFormModal, {
    props: { open: false, reservation: null, day: '2026-10-15', ...props },
    session: WITHOUT_CONTACT,
  });
  m.answerBy({
    '/api/reservation/availability/tables': [200, { rows: [] }],
    '/api/customer/customers/detail': [200, { id: 'c1', name: 'Lucía Pérez', phone: null, email: null }],
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const shown = () => ['guest_phone', 'guest_email'].filter((name) => m.inDoc(`reservation-form-${name}`) !== null);
  const field = (name: string) => m.inDoc(`reservation-form-${name}`) as HTMLElement;
  const bodies = (path: string) => m.sent().filter((call) => call.path === path).map((call) => call.body);
  return { ...m, shown, field, bodies };
}

describe('ReservationFormModal: the guest’s contact details it was not given', () => {
  it('editing shows the phone and email that came, and sends them only when they change', async () => {
    const s = await setup({ reservation: reservationRow({ status: 'confirmed', guest_email: 'ana@x.es' }) });
    expect(s.shown()).toEqual(['guest_phone', 'guest_email']);
    await ionValue(s.field('guest_phone'), '600 999 000', 'ionInput');
    s.answer(200, reservationRow());
    await click(s.inDoc('reservation-form-submit')!);
    expect(s.bodies('/api/reservation/reservations/update')).toEqual([{ id: 'r1', guest_phone: '600 999 000', overbook: false }]);
  });

  it('editing one that came without them shows neither and never sends them, so saving keeps them', async () => {
    const s = await setup({ reservation: reservationRow({ status: 'confirmed', guest_phone: null, guest_email: null }) });
    expect(s.shown()).toEqual([]);
    await ionValue(s.field('party_size'), '6', 'ionInput');
    s.answer(200, reservationRow());
    await click(s.inDoc('reservation-form-submit')!);
    expect(s.bodies('/api/reservation/reservations/update')).toEqual([{ id: 'r1', party_size: 6, overbook: false }]);
  });

  it('the same panel, after a new booking with a card, edits one that came without them the same way', async () => {
    const s = await setup({});
    s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', LUCIA);
    await settle();
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ reservation: reservationRow({ status: 'confirmed', guest_phone: null, guest_email: null }), open: true });
    await settle();
    expect(s.shown()).toEqual([]);
    await ionValue(s.field('party_size'), '6', 'ionInput');
    s.answer(200, reservationRow());
    await click(s.inDoc('reservation-form-submit')!);
    expect(s.bodies('/api/reservation/reservations/update')).toEqual([{ id: 'r1', party_size: 6, overbook: false }]);
  });

  it('a card picked without them books with the card’s, and leaving the card asks for them again', async () => {
    const s = await setup({});
    const pick = async (card: typeof LUCIA | null) => {
      s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', card);
      await settle();
      return s.shown();
    };
    expect(s.shown()).toEqual(['guest_phone', 'guest_email']);
    expect(await pick(LUCIA)).toEqual([]);
    expect(await pick(null)).toEqual(['guest_phone', 'guest_email']);
    expect(await pick(LUCIA)).toEqual([]);
    await ionValue(s.field('time'), '21:00', 'ionInput');
    s.answer(201, reservationRow());
    await click(s.inDoc('reservation-form-submit')!);
    const [booked] = s.bodies('/api/reservation/reservations') as Record<string, unknown>[];
    expect([booked.customer_id, 'guest_phone' in booked, 'guest_email' in booked]).toEqual(['c1', false, false]);
  });
});
