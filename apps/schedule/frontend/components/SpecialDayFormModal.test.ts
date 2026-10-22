// SCHEDULE-F04 «Añadir un día especial» and F13 «Corregir»: «New special day» — Date, Name, Status
// («Closed» or «Open (with hours)», closed to begin with), the interval editor when open, «Repeats every
// year» and Notes — and «Add day» (the old words); a row opens «Edit · {name}» with «Save». «Add day»
// waits for a date and a name. The server's refusal goes under its field (the 409 of a taken date under
// Date) and what was typed stays.
import { describe, expect, it, vi } from 'vitest';

import type { SpecialDayOut } from '../operations';
import { click, ionValue, mountSchedule, settle } from '../__tests__/mount-schedule';
import SpecialDayFormModal from './SpecialDayFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; disabled?: boolean; errorText?: string; type?: string; placeholder?: string };

async function toggle(el: Element | null, checked: boolean): Promise<void> {
  if (!el) throw new Error('no checkbox');
  (el as HTMLElement & { checked?: boolean }).checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked, value: 'on' }, bubbles: true }));
  await settle();
}

const EVE: SpecialDayOut = {
  id: 'sd1',
  date: '2026-12-24',
  name: 'Christmas Eve',
  is_closed: false,
  recurring_yearly: true,
  notes: 'half day',
  intervals: [{ open_time: '10:00:00', close_time: '14:00:00' }],
};
const SAVED = { ...EVE, id: 'sd9' };

async function setup(specialDay: SpecialDayOut | null = null, locale: 'en' | 'es' = 'en') {
  const m = await mountSchedule(SpecialDayFormModal, { props: { open: true, specialDay }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const field = (name: string) => m.inDoc(`schedule-special-day-form-${name}`) as Control;
  const submit = () => m.inDoc('schedule-special-day-form-submit') as Control;
  return { ...m, field, submit };
}

describe('SpecialDayFormModal (SCHEDULE-F04, F13)', () => {
  it('«New special day»: Date, Name, Status closed, Repeats every year, Notes and «Add day»', async () => {
    const s = await setup();
    expect(s.inDoc('schedule-special-day-form')?.getAttribute('aria-label')).toBe('New special day');
    expect([s.field('date').type, s.field('date').label]).toEqual(['date', 'Date']);
    expect([s.field('name').label, s.field('name').placeholder]).toEqual(['Name', 'Name (e.g. Christmas)']);
    expect([s.field('status').label, s.field('status').value]).toEqual(['Status', 'closed']);
    expect(s.inDoc('schedule-special-day-form-intervals-open-0')).toBeNull();
    expect(s.field('recurring').textContent?.trim()).toBe('Repeats every year');
    expect(s.field('notes').label).toBe('Notes');
    expect(s.submit().textContent?.trim()).toBe('Add day');
  });

  it('«Add day» waits for a date and a name', async () => {
    const s = await setup();
    expect(s.submit().disabled).toBe(true);
    await ionValue(s.field('date'), '2026-12-25', 'ionInput');
    expect(s.submit().disabled).toBe(true);
    await ionValue(s.field('name'), '   ', 'ionInput');
    expect(s.submit().disabled).toBe(true);
    await ionValue(s.field('name'), 'Christmas', 'ionInput');
    expect(s.submit().disabled).toBe(false);
  });

  it('a closed day sends schedule.special_day.create, then closes', async () => {
    const s = await setup();
    s.answer(201, SAVED);
    await ionValue(s.field('date'), '2026-12-25', 'ionInput');
    await ionValue(s.field('name'), ' Christmas ', 'ionInput');
    await toggle(s.field('recurring'), true);
    await click(s.submit());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/schedule/special_days',
        query: {},
        body: { date: '2026-12-25', name: 'Christmas', is_closed: true, intervals: [], recurring_yearly: true, notes: '' },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('«Open (with hours)» shows the intervals and sends them', async () => {
    const s = await setup();
    s.answer(201, SAVED);
    await ionValue(s.field('date'), '2026-12-24', 'ionInput');
    await ionValue(s.field('name'), 'Eve', 'ionInput');
    await ionValue(s.field('status'), 'open');
    await ionValue(s.inDoc('schedule-special-day-form-intervals-open-0'), '10:00', 'ionInput');
    await ionValue(s.inDoc('schedule-special-day-form-intervals-close-0'), '13:00', 'ionInput');
    await click(s.submit());
    expect(s.sent()[0].body).toMatchObject({ is_closed: false, intervals: [{ open_time: '10:00', close_time: '13:00' }] });
  });

  it('an open day with a line half filled is said in the form and nothing is sent', async () => {
    const s = await setup();
    await ionValue(s.field('date'), '2026-12-24', 'ionInput');
    await ionValue(s.field('name'), 'Eve', 'ionInput');
    await ionValue(s.field('status'), 'open');
    await click(s.submit());
    expect(s.sent()).toEqual([]);
    expect(s.inDoc('schedule-special-day-form-incomplete')?.textContent?.trim()).toBe('Enter opening and closing times, or mark it as closed');
  });

  it('a taken date (409) is said under Date, the dialog stays open', async () => {
    const s = await setup();
    const taken = 'There is already a special day on that date.';
    s.answer(409, { error: { code: 'schedule.special_day_exists', message: taken, fields: { date: taken } } });
    await ionValue(s.field('date'), '2026-12-25', 'ionInput');
    await ionValue(s.field('name'), 'Again', 'ionInput');
    await click(s.submit());
    expect(s.field('date').errorText).toBe(taken);
    expect(s.field('date').classList.contains('ion-invalid')).toBe(true);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(s.field('name').value).toBe('Again');
  });

  it('a row opens «Edit · {name}» with what it has, and «Save» sends schedule.special_day.update', async () => {
    const s = await setup(EVE);
    expect(s.inDoc('schedule-special-day-form')?.getAttribute('aria-label')).toBe('Edit · Christmas Eve');
    expect([s.field('date').value, s.field('name').value, s.field('status').value, s.field('recurring').checked, s.field('notes').value]).toEqual([
      '2026-12-24',
      'Christmas Eve',
      'open',
      true,
      'half day',
    ]);
    expect((s.inDoc('schedule-special-day-form-intervals-close-0') as Control).value).toBe('14:00');
    expect(s.submit().textContent?.trim()).toBe('Save');
    s.answer(200, EVE);
    await ionValue(s.field('notes'), 'Family', 'ionInput');
    await click(s.submit());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/schedule/special_days/update',
        query: {},
        body: {
          id: 'sd1',
          date: '2026-12-24',
          name: 'Christmas Eve',
          is_closed: false,
          intervals: [{ open_time: '10:00', close_time: '14:00' }],
          recurring_yearly: true,
          notes: 'Family',
        },
      },
    ]);
  });

  it('speaks Spanish with the old words', async () => {
    const s = await setup(null, 'es');
    expect(s.inDoc('schedule-special-day-form')?.getAttribute('aria-label')).toBe('Nuevo día especial');
    expect([s.field('date').label, s.field('name').placeholder, s.submit().textContent?.trim()]).toEqual(['Fecha', 'Nombre (p. ej. Navidad)', 'Añadir día']);
  });
});
