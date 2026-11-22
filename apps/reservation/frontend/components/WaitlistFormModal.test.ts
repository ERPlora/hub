// RESERVATION-F14: «Add guest» puts somebody on the waitlist — the Customer (Customers' search) or the
// guest's Name and, if given, Phone, the Date, the preferred Time, the Party and notes. A refusal goes on
// top, a bad field under it.
import { describe, expect, it } from 'vitest';

import CustomerSearch from '../../../customer/frontend/components/CustomerSearch.vue';
import { pick, picked } from '../../../../base/frontend/__tests__/date-time-fields';
import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, ionValue, mountReservation, settle } from '../__tests__/mount-reservation';
import { entryRow } from '../__tests__/rows';
import WaitlistFormModal from './WaitlistFormModal.vue';

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string; disabled?: boolean; readonly?: boolean; required?: boolean };

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
    expect(picked(s.field('date'))).toBe('2026-10-15');
    expect(s.wrapper.findComponent(CustomerSearch).exists()).toBe(true);
    expect(s.submit().textContent).toContain('Add to waitlist');
    expect(s.submit().disabled).toBe(true);
  });

  it('writes somebody down without a phone, and with one', async () => {
    const s = await setup();
    await ionValue(s.field('guest_name'), 'Luis', 'ionInput');
    await pick(s.field('preferred_time'), '21:00');
    s.answer(201, entryRow());
    await click(s.submit());
    expect(s.sent().map((call) => call.body)).toEqual([
      { guest_name: 'Luis', guest_phone: '', date: '2026-10-15', preferred_time: '21:00', party_size: 2, notes: '' },
    ]);
    expect(s.wrapper.emitted('saved')).toHaveLength(1);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  // The date and the preferred time are the app's own calendar and time wheel, never the device's; both are needed,
  // so neither offers «Clear».
  it('the date and the preferred time are the app’s pickers, shown as read', async () => {
    const s = await setup();
    await pick(s.field('date'), '2026-10-16');
    await pick(s.field('preferred_time'), '21:00');
    expect([s.field('date'), s.field('preferred_time')].map((field) => [field.readonly, field.required])).toEqual([[true, true], [true, true]]);
    expect([s.field('date').value, s.field('preferred_time').value]).toEqual(['10/16/2026', expect.stringMatching(/^09:00\sPM$/)]);
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
    await pick(s.field('preferred_time'), '21:00');
    s.answer(201, entryRow());
    await click(s.submit());
    expect(s.sent().at(-1)?.body).toMatchObject({ customer_id: 'c1', guest_name: 'Lucía Pérez' });
  });

  it('puts a bad phone under its field, and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.submit().textContent).toContain('Añadir a la lista de espera');
    await ionValue(s.field('guest_name'), 'Luis', 'ionInput');
    await ionValue(s.field('guest_phone'), '12', 'ionInput');
    await pick(s.field('preferred_time'), '21:00');
    s.answer(422, { error: { code: 'invalid_payload', message: 'Teléfono no válido', fields: { guest_phone: 'Teléfono no válido' } } });
    await click(s.submit());
    expect(s.field('guest_phone').errorText).toBe('Teléfono no válido');
  });
});

describe('WaitlistFormModal: fields refused with the same words (hub#888)', () => {
  // The guest, the phone, the day, the time and the party paint a refusal, each under its own key.
  itTellsTheCorrectedFieldApart(['guest_name', 'guest_phone', 'date', 'preferred_time', 'party_size'], async (locale, refusal) => {
    const s = await setup(locale);
    await ionValue(s.field('guest_name'), 'Luis', 'ionInput');
    await ionValue(s.field('guest_phone'), '600123123', 'ionInput');
    await pick(s.field('preferred_time'), '21:00');
    s.answer(422, refusal);
    return { field: s.field, send: () => click(s.submit()), settle };
  }, 'guest_phone');
});

describe('WaitlistFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('reservation-waitlist-form'),
      change: () => ionValue(s.field('guest_name'), 'Luis', 'ionInput'),
      restore: () => ionValue(s.field('guest_name'), '', 'ionInput'),
    });
  });
});
