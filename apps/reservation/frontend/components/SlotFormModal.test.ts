// RESERVATION-F01: «Add slot» — the Day of the week, From, To, Max reservations and, optionally, Max
// guests; «Create slot». An overlap with another slot of the day goes on top and under «From».
import { describe, expect, it } from 'vitest';

import { pick } from '../../../../base/frontend/__tests__/date-time-fields';
import { itTellsTheCorrectedFieldApart } from '../../../../base/frontend/__tests__/same-words-refusal';
import { click, type Control, ionValue, mountOpenForm, settle } from '../__tests__/mount-reservation';
import { slotRow } from '../__tests__/rows';
import SlotFormModal from './SlotFormModal.vue';

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountOpenForm(SlotFormModal, { props: { weekday: 3 }, locale });
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
    await pick(s.field('start_time'), '20:00');
    await pick(s.field('end_time'), '23:30');
    await ionValue(s.field('max_covers'), '40', 'ionInput');
    s.answer(201, slotRow());
    await click(s.submit());
    expect(s.sent().map((call) => call.body)).toEqual([
      { day_of_week: 5, start_time: '20:00', end_time: '23:30', max_reservations: 10, max_covers: 40 },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it.each([
    ['en', 'Max guests', 'Optional'],
    ['es', 'Máx comensales', 'Opcional'],
  ] as const)('in %s, the maximum of guests says under its field that it is optional, not in its label', async (locale, label, help) => {
    const s = await setup(locale);
    const covers = s.field('max_covers') as Control & { helperText?: string };
    expect([covers.label, covers.helperText]).toEqual([label, help]);
  });

  // From and To are the app's own time wheel, never the device's; a slot needs both, so neither offers «Clear».
  it('From and To are the app’s time pickers, shown as read', async () => {
    const s = await setup();
    await pick(s.field('start_time'), '20:00');
    await pick(s.field('end_time'), '23:30');
    expect([s.field('start_time'), s.field('end_time')].map((field) => [field.readonly, field.required])).toEqual([[true, true], [true, true]]);
    expect([s.field('start_time').value, s.field('end_time').value]).toEqual([expect.stringMatching(/^08:00\sPM$/), expect.stringMatching(/^11:30\sPM$/)]);
  });

  it('puts an overlap once, under «From», and speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.submit().textContent).toContain('Crear franja');
    await pick(s.field('start_time'), '15:00');
    await pick(s.field('end_time'), '17:00');
    const message = 'Esa franja se pisa con otra del mismo día (13:00–16:00).';
    s.answer(409, { error: { code: 'reservation.slot_overlaps', message, fields: { start_time: message } } });
    await click(s.submit());
    expect(s.field('start_time').errorText).toBe(message);
    expect(s.inDoc('reservation-slot-form-error')).toBeNull();
  });
});

describe('SlotFormModal: fields refused with the same words (hub#888)', () => {
  // From, To and both maximums paint a refusal, each under its own key.
  itTellsTheCorrectedFieldApart(['start_time', 'end_time', 'max_reservations', 'max_covers'], async (locale, refusal) => {
    const s = await setup(locale);
    await pick(s.field('start_time'), '20:00');
    await pick(s.field('end_time'), '23:30');
    await ionValue(s.field('max_covers'), '40', 'ionInput');
    s.answer(422, refusal);
    return { field: s.field, send: () => click(s.submit()), settle };
  }, 'max_covers');
});

describe('SlotFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('reservation-slot-form'),
      change: () => pick(s.field('start_time'), '20:00'),
      restore: () => pick(s.field('start_time'), ''),
    });
  });
});
