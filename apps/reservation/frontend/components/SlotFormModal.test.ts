// RESERVATION-F01: «Add slot» — the Day of the week, From, To, Max reservations and, optionally, Max
// guests; «Create slot». An overlap with another slot of the day goes on top and under «From».
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountReservation, settle } from '../__tests__/mount-reservation';
import { slotRow } from '../__tests__/rows';
import SlotFormModal from './SlotFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; errorText?: string };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountReservation(SlotFormModal, { props: { open: false, weekday: 3 }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`reservation-slot-form-${name}`) as Control;
  return { ...m, field, submit: () => m.inDoc('reservation-slot-form-submit') as Control };
}

describe('SlotFormModal', () => {
  it('creates a slot of a weekday with its maximum', async () => {
    const s = await setup();
    expect([s.field('day_of_week').label, s.field('start_time').label, s.field('end_time').label, s.field('max_reservations').label]).toEqual([
      'Day',
      'From',
      'To',
      'Max',
    ]);
    expect([s.field('day_of_week').value, s.field('max_reservations').value]).toEqual([3, '10']);
    await ionValue(s.field('day_of_week'), 5);
    await ionValue(s.field('start_time'), '20:00', 'ionInput');
    await ionValue(s.field('end_time'), '23:30', 'ionInput');
    await ionValue(s.field('max_covers'), '40', 'ionInput');
    s.answer(201, slotRow());
    await click(s.submit());
    expect(s.sent().map((call) => call.body)).toEqual([
      { day_of_week: 5, start_time: '20:00', end_time: '23:30', max_reservations: 10, max_covers: 40 },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('puts an overlap under «From», and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.submit().textContent).toContain('Crear franja');
    await ionValue(s.field('start_time'), '15:00', 'ionInput');
    await ionValue(s.field('end_time'), '17:00', 'ionInput');
    const message = 'Esa franja se pisa con otra del mismo día (13:00–16:00).';
    s.answer(409, { error: { code: 'reservation.slot_overlaps', message, fields: { start_time: message } } });
    await click(s.submit());
    expect(s.field('start_time').errorText).toBe(message);
  });
});
