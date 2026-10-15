// APPOINTMENT-F20 «Ver las citas de una clienta en su ficha»: the «Visit history» block Customers paints at
// the end of a card (CUSTOMER-F24's contract: one prop, `customerId`). Her ten last appointments, the
// newest first, with services, professional, status and the visit's notes (the internal one first).
import { describe, expect, it } from 'vitest';

import { mountAppointment, page, settle, errorFrame } from '../__tests__/mount-appointment';
import VisitHistory from './VisitHistory.vue';

const OP = 'appointment.appointment.list_for_customer';
const visit = (id: string, over = {}) => ({
  id,
  number: `APT-${id}`,
  customer_id: 'c1',
  customer_name: 'Lucía Pérez',
  staff_id: 's1',
  staff_name: 'Ana López',
  start: '2026-10-19T10:00:00+02:00',
  end: '2026-10-19T10:30:00+02:00',
  duration_minutes: 30,
  status: 'completed',
  source: 'counter',
  services: [],
  service_names: 'Colour',
  total: 4500,
  booked_by_customer: false,
  sale_id: null,
  order_id: null,
  recurring_id: null,
  occurrence_date: null,
  notes: 'Bring photo',
  internal_notes: 'Formula 7/1',
  ...over,
});

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(VisitHistory, { props: { customerId: 'c1' }, locale });
  await m.live();
  return m;
}

describe('VisitHistory', () => {
  it('asks her ten last appointments and paints each with its notes, the internal one first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ customer_id: 'c1', limit: 10 }]);
    await s.result(OP, page([visit('a1')], 1, 10));
    expect(s.find('appointment-visits').text()).toContain('Visit history');
    const text = s.find('appointment-visit').text().replace(/\s+/g, ' ');
    for (const part of ['Monday, October 19, 2026 · 10:00 AM', 'Colour · Ana López', 'Completed']) expect(text).toContain(part);
    expect(text.indexOf('Formula 7/1')).toBeLessThan(text.indexOf('Bring photo'));
  });

  it('says when she has none, and when it cannot load', async () => {
    const s = await setup('es');
    await s.result(OP, page([], 0, 10));
    expect(s.find('appointment-visits-empty').text()).toBe('Este cliente aún no tiene citas.');
    s.net.lastStream().push(errorFrame(s.subId(OP), 'appointment.boom'));
    await settle();
    expect(s.find('appointment-visits-error').text()).toContain('No se pudo cargar el historial de visitas.');
  });
});
