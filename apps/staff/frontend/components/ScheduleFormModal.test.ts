// STAFF-F13 «Crear el horario semanal» and STAFF-F14 «Editar un horario»: the old panel as a dialog —
// Schedule (name; empty, the server calls it «Regular schedule»), Effective from, Effective until,
// Default, and one row per weekday with «works» and Start «to» End «break» Start «to» End, or «Off».
// A new one proposes Monday to Friday 09:00–18:00 and says «Create schedule»; editing replaces the
// whole week and says «Save». The server judges: a day's problem goes under that day's row, a week
// without working days on top of the week, a date under its field.
import { describe, expect, it, vi } from 'vitest';

import type { ScheduleOut } from '../operations';
import { click, ionChecked, ionValue, mountStaff, settle } from '../__tests__/mount-staff';
import ScheduleFormModal from './ScheduleFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; type?: string; placeholder?: string; errorText?: string };

const SUMMER: ScheduleOut = {
  id: 's1',
  member_id: 'm1',
  name: 'Summer',
  is_default: false,
  effective_from: '2026-06-01',
  effective_until: '2026-09-15',
  is_active: true,
  days: [{ weekday: 1, start_time: '08:00:00', end_time: '15:00:00', break_start: null, break_end: null }],
};

async function setup(schedule: ScheduleOut | null = null, locale: 'en' | 'es' = 'en', proposeDefault = true) {
  const m = await mountStaff(ScheduleFormModal, { props: { open: false, memberId: 'm1', schedule, proposeDefault }, locale, path: '/staff/schedules' });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`staff-schedule-form-${name}`) as Control;
  const day = (weekday: number, part: string) => m.inDoc(`staff-schedule-form-day-${weekday}-${part}`) as Control;
  const save = () => m.inDoc('staff-schedule-form-submit') as Control;
  return { ...m, field, day, save };
}

describe('ScheduleFormModal: New (STAFF-F13)', () => {
  it('proposes Monday to Friday from 09:00 to 18:00, default, and says «Create schedule»', async () => {
    const s = await setup();
    expect(s.inDoc('staff-schedule-form')?.getAttribute('aria-label')).toBe('New');
    expect([s.field('name').label, s.field('name').placeholder, s.field('effective_from').type, s.field('effective_until').label, s.field('is_default').checked]).toEqual([
      'Schedule',
      'Schedule name',
      'date',
      'Effective until',
      true,
    ]);
    const week = [0, 1, 2, 3, 4, 5, 6].map((d) => [s.day(d, 'working').textContent?.trim(), s.day(d, 'working').checked, s.day(d, 'start')?.value ?? null, s.day(d, 'end')?.value ?? null]);
    expect(week).toEqual([
      ['Monday', true, '09:00', '18:00'],
      ['Tuesday', true, '09:00', '18:00'],
      ['Wednesday', true, '09:00', '18:00'],
      ['Thursday', true, '09:00', '18:00'],
      ['Friday', true, '09:00', '18:00'],
      ['Saturday', false, null, null],
      ['Sunday', false, null, null],
    ]);
    expect(s.day(5, 'off').textContent?.trim()).toBe('Off');
    expect([s.day(0, 'start').type, s.day(0, 'break_start').label]).toEqual(['time', 'Break start']);
    expect(s.save().textContent?.trim()).toBe('Create schedule');
  });

  it('for a member who has a default schedule already, a new one starts without «Default»', async () => {
    const s = await setup(null, 'en', false);
    expect(s.field('is_default').checked).toBe(false);
  });

  it('sends staff.schedule.create with the member and the working days, then closes', async () => {
    const s = await setup();
    s.answer(201, SUMMER);
    await ionValue(s.field('name'), 'Winter', 'ionInput');
    await ionChecked(s.day(1, 'working'), false);
    await ionValue(s.day(0, 'break_start'), '13:00', 'ionInput');
    await ionValue(s.day(0, 'break_end'), '14:00', 'ionInput');
    await ionChecked(s.day(5, 'working'), true);
    await ionValue(s.day(5, 'end'), '14:00', 'ionInput');
    await click(s.save());
    const day = (weekday: number, end = '18:00', pause: [string | null, string | null] = [null, null]) => ({
      weekday,
      start_time: '09:00',
      end_time: end,
      break_start: pause[0],
      break_end: pause[1],
    });
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/staff/schedules',
        query: {},
        body: {
          member_id: 'm1',
          name: 'Winter',
          is_default: true,
          effective_from: null,
          effective_until: null,
          days: [day(0, '18:00', ['13:00', '14:00']), day(2), day(3), day(4), day(5, '14:00')],
        },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a day’s problem goes under that day; a week without working days on top of the week', async () => {
    const s = await setup();
    s.answer(422, {
      error: {
        code: 'invalid_payload',
        message: 'Check the fields.',
        fields: { 'days.1.end_time': 'The start time must be before the end time.', days: 'A schedule needs at least one working day with hours.' },
      },
    });
    await click(s.save());
    // The second day sent is Tuesday.
    expect(s.inDoc('staff-schedule-form-day-1-error')?.textContent).toContain('The start time must be before the end time.');
    expect(s.inDoc('staff-schedule-form-day-0-error')).toBeNull();
    expect(s.inDoc('staff-schedule-form-week-error')?.textContent).toContain('A schedule needs at least one working day with hours.');
  });
});

describe('ScheduleFormModal: Edit · {name} (STAFF-F14)', () => {
  it('fills the schedule and its week, and replaces the week with staff.schedule.update', async () => {
    const s = await setup(SUMMER);
    expect(s.inDoc('staff-schedule-form')?.getAttribute('aria-label')).toBe('Edit · Summer');
    expect([s.field('name').value, s.field('effective_from').value, s.field('is_default').checked, s.day(1, 'start').value, s.day(0, 'working').checked]).toEqual([
      'Summer',
      '2026-06-01',
      false,
      '08:00',
      false,
    ]);
    expect(s.save().textContent?.trim()).toBe('Save');
    s.answer(200, SUMMER);
    await ionValue(s.field('effective_until'), '', 'ionInput');
    await click(s.save());
    expect(s.sent()[0]).toEqual({
      method: 'POST',
      path: '/api/staff/schedules/update',
      query: {},
      body: {
        id: 's1',
        name: 'Summer',
        is_default: false,
        effective_from: '2026-06-01',
        effective_until: null,
        days: [{ weekday: 1, start_time: '08:00', end_time: '15:00', break_start: null, break_end: null }],
      },
    });
  });

  it('speaks Spanish', async () => {
    const s = await setup(SUMMER, 'es');
    expect(s.inDoc('staff-schedule-form')?.getAttribute('aria-label')).toBe('Editar · Summer');
    expect([s.field('effective_from').label, s.day(0, 'working').textContent?.trim(), s.day(0, 'off').textContent?.trim()]).toEqual([
      'Vigente desde',
      'Lunes',
      'No trabaja',
    ]);
  });
});
