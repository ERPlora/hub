// RESERVATION-F14: «Add guest» puts somebody on the waitlist — the Customer (Customers' search) or the
// guest's Name and, if given, Phone, the Date, the preferred Time, the Party and notes. A refusal goes on
// top, a bad field under it.
import { describe, expect, it, vi } from 'vitest';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import { click, ionValue, mountReservation, settle } from '../__tests__/mount-reservation';
import { entryRow } from '../__tests__/rows';
import WaitlistFormModal from './WaitlistFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(WaitlistFormModal, { props: { open: false, day: '2026-10-15' }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`reservation-waitlist-form-${name}`) as Control;
  const submit = () => m.inDoc('reservation-waitlist-form-submit') as Control;
  return { ...m, field, submit };
}

describe('WaitlistFormModal', () => {
  it('asks for the guest, the day, the preferred time and the party, as the old panel', async () => {
    const s = await setup();
    expect([s.field('guest_name').label, s.field('guest_phone').label, s.field('date').label, s.field('preferred_time').label, s.field('party_size').label]).toEqual([
      'Guest',
      'Phone',
      'Date',
      'Time',
      'Party',
    ]);
    expect(s.wrapper.findComponent(CustomerSearch).exists()).toBe(true);
    expect(s.submit().textContent).toContain('Add to waitlist');
    expect(s.submit().disabled).toBe(true);
  });

  it('writes somebody down without a phone, and with one', async () => {
    const s = await setup();
    await ionValue(s.field('guest_name'), 'Luis', 'ionInput');
    await ionValue(s.field('preferred_time'), '21:00', 'ionInput');
    s.answer(201, entryRow());
    await click(s.submit());
    expect(s.sent().map((call) => call.body)).toEqual([
      { guest_name: 'Luis', guest_phone: '', date: '2026-10-15', preferred_time: '21:00', party_size: 2, notes: '' },
    ]);
    expect(s.wrapper.emitted('saved')).toHaveLength(1);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a customer picked from Customers is the guest', async () => {
    const s = await setup();
    s.wrapper.findComponent(CustomerSearch).vm.$emit('update:modelValue', {
      customer_id: 'c1',
      customer_name: 'Lucía Pérez',
      customer_tax_id: '',
      customer_address: '',
      customer_country: '',
    });
    await settle();
    await ionValue(s.field('preferred_time'), '21:00', 'ionInput');
    s.answer(201, entryRow());
    await click(s.submit());
    expect(s.sent().at(-1)?.body).toMatchObject({ customer_id: 'c1', guest_name: 'Lucía Pérez' });
  });

  it('puts a bad phone under its field, and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.submit().textContent).toContain('Añadir a la lista de espera');
    await ionValue(s.field('guest_name'), 'Luis', 'ionInput');
    await ionValue(s.field('guest_phone'), '12', 'ionInput');
    await ionValue(s.field('preferred_time'), '21:00', 'ionInput');
    s.answer(422, { error: { code: 'invalid_payload', message: 'Teléfono no válido', fields: { guest_phone: 'Teléfono no válido' } } });
    await click(s.submit());
    expect(s.field('guest_phone').errorText).toBe('Teléfono no válido');
  });
});
