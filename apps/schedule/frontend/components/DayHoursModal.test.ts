// SCHEDULE-F02 «Fijar el horario de un día»: «Edit» on a day (or its row) opens «Edit hours — {day}»
// with Day, Closed, Open 24 hours and the interval editor, and «Save day» sends
// `schedule.week.set_day`, which replaces the day's intervals. A line half filled is said in the form
// and nothing is sent; the server's refusal (overlaps…) goes under the intervals; what was typed stays.
import { describe, expect, it, vi } from 'vitest';

import type { WeekDayOut } from '../operations';
import { click, ionValue, mountSchedule, settle } from '../__tests__/mount-schedule';
import DayHoursModal from './DayHoursModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

/** Ticks or unticks an `ion-checkbox` as Ionic does (`ionChange` with `checked`). */
async function toggle(el: Element | null, checked: boolean): Promise<void> {
  if (!el) throw new Error('no checkbox');
  (el as HTMLElement & { checked?: boolean }).checked = checked;
  el.dispatchEvent(new CustomEvent('ionChange', { detail: { checked, value: 'on' }, bubbles: true }));
  await settle();
}

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; disabled?: boolean; errorText?: string };

const MONDAY: WeekDayOut = {
  weekday: 0,
  name: 'Monday',
  id: 'd0',
  is_set: true,
  is_closed: false,
  intervals: [
    { open_time: '10:00:00', close_time: '14:00:00' },
    { open_time: '17:00:00', close_time: '20:00:00' },
  ],
};
const SUNDAY: WeekDayOut = { weekday: 6, name: 'Sunday', id: 'd6', is_set: true, is_closed: true, intervals: [] };
const UNSET: WeekDayOut = { weekday: 2, name: 'Wednesday', id: null, is_set: false, is_closed: false, intervals: [] };

async function setup(day: WeekDayOut = MONDAY, locale: 'en' | 'es' = 'en') {
  const m = await mountSchedule(DayHoursModal, { props: { open: true, day }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await settle();
  const control = (name: string) => m.inDoc(`schedule-day-form-${name}`) as Control;
  const submit = () => m.inDoc('schedule-day-form-submit') as Control;
  return { ...m, control, submit };
}

describe('DayHoursModal (SCHEDULE-F02)', () => {
  it('opens «Edit hours — {day}» with the day’s intervals and «Save day»', async () => {
    const s = await setup();
    expect(s.inDoc('schedule-day-form')?.getAttribute('aria-label')).toBe('Edit hours — Monday');
    expect(s.control('weekday').value).toBe(0);
    expect([s.control('closed').checked, s.control('open24h').checked]).toEqual([false, false]);
    expect([(s.inDoc('schedule-day-form-intervals-open-0') as Control).value, (s.inDoc('schedule-day-form-intervals-close-1') as Control).value]).toEqual([
      '10:00',
      '20:00',
    ]);
    expect(s.submit().textContent?.trim()).toBe('Save day');
  });

  it('a closed day shows no interval; a day not set starts from 09:00–18:00', async () => {
    const closed = await setup(SUNDAY);
    expect(closed.control('closed').checked).toBe(true);
    expect(closed.inDoc('schedule-day-form-intervals-open-0')).toBeNull();
    const unset = await setup(UNSET);
    expect((unset.inDoc('schedule-day-form-intervals-open-0') as Control).value).toBe('09:00');
  });

  it('«Save day» sends the day and its intervals, then closes', async () => {
    const s = await setup();
    s.answer(200, { week_starts_on: 1, confirmed: true, timezone: 'Europe/Madrid', days: [] });
    await click(s.submit());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/schedule/week/set_day',
        query: {},
        body: {
          weekday: 0,
          is_closed: false,
          intervals: [
            { open_time: '10:00', close_time: '14:00' },
            { open_time: '17:00', close_time: '20:00' },
          ],
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('another day in the selector re-titles the dialog and saves there', async () => {
    const s = await setup();
    s.answer(200, { week_starts_on: 1, confirmed: true, timezone: 'Europe/Madrid', days: [] });
    await ionValue(s.control('weekday'), 1);
    expect(s.inDoc('schedule-day-form')?.getAttribute('aria-label')).toBe('Edit hours — Tuesday');
    await click(s.submit());
    expect((s.sent()[0].body as { weekday: number }).weekday).toBe(1);
  });

  it('Closed sends no interval; Open 24 hours sends 00:00–00:00', async () => {
    const s = await setup();
    s.answer(200, { week_starts_on: 1, confirmed: true, timezone: 'Europe/Madrid', days: [] });
    await toggle(s.control('open24h'), true);
    expect(s.inDoc('schedule-day-form-intervals-open-0')).toBeNull();
    await click(s.submit());
    expect(s.sent().at(-1)?.body).toEqual({ weekday: 0, is_closed: false, intervals: [{ open_time: '00:00', close_time: '00:00' }] });
    await s.wrapper.setProps({ open: true });
    await settle();
    await toggle(s.control('closed'), true);
    await click(s.submit());
    expect(s.sent().at(-1)?.body).toEqual({ weekday: 0, is_closed: true, intervals: [] });
  });

  it('a line half filled is said in the form and nothing is sent', async () => {
    const s = await setup(UNSET);
    await ionValue(s.inDoc('schedule-day-form-intervals-close-0'), '', 'ionInput');
    await click(s.submit());
    expect(s.sent()).toEqual([]);
    expect(s.inDoc('schedule-day-form-incomplete')?.textContent?.trim()).toBe('Enter opening and closing times, or mark it as closed');
  });

  it('the server’s refusal goes under the intervals, the dialog stays open with what was typed', async () => {
    const s = await setup();
    const overlap = 'Two intervals overlap (or one runs past midnight into another); adjust the times so they do not clash.';
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { intervals: overlap } } });
    await ionValue(s.inDoc('schedule-day-form-intervals-open-1'), '13:00', 'ionInput');
    await click(s.submit());
    expect(s.inDoc('schedule-day-form-intervals-error')?.textContent?.trim()).toBe(overlap);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect((s.inDoc('schedule-day-form-intervals-open-1') as Control).value).toBe('13:00');
  });

  it('speaks Spanish', async () => {
    const s = await setup(MONDAY, 'es');
    expect(s.inDoc('schedule-day-form')?.getAttribute('aria-label')).toBe('Editar horario — Lunes');
    expect([s.control('weekday').label, s.submit().textContent?.trim()]).toEqual(['Día', 'Guardar día']);
  });
});
