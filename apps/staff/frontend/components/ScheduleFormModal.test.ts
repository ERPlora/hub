// STAFF-F13 «Crear el horario semanal» and STAFF-F14 «Editar un horario»: the old panel as a dialog —
// Schedule (name; empty, the server calls it «Regular schedule»), Effective from, Effective until,
// Default, and one row per weekday with «works» and Start «to» End «break» Start «to» End, or «Off».
// A new one proposes Monday to Friday with the business's default working day (Staff › Settings,
// STAFF-F22: followed live; until it arrives, its own defaults, 09:00–18:00 with a break 13:00–14:00)
// and says «Create schedule»; editing replaces the
// whole week and says «Save». The server judges: a day's problem goes under that day's row, a week
// without working days on top of the week, a date under its field.
import { describe, expect, it, vi } from 'vitest';

import type { ScheduleOut, SettingsOut } from '../operations';
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

const EARLY: SettingsOut = { default_work_start: '08:00', default_work_end: '16:00', default_break_duration: 30 };

async function setup(schedule: ScheduleOut | null = null, locale: 'en' | 'es' = 'en', proposeDefault = true, settings?: SettingsOut) {
  const m = await mountStaff(ScheduleFormModal, { props: { open: false, memberId: 'm1', schedule, proposeDefault }, locale, path: '/staff/schedules' });
  if (settings) {
    await m.live();
    await m.result('staff.settings.get', settings);
  }
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`staff-schedule-form-${name}`) as Control;
  const day = (weekday: number, part: string) => m.inDoc(`staff-schedule-form-day-${weekday}-${part}`) as Control;
  const save = () => m.inDoc('staff-schedule-form-submit') as Control;
  return { ...m, field, day, save };
}

describe('ScheduleFormModal: New (STAFF-F13)', () => {
  it('until the working day arrives, proposes Monday to Friday 09:00–18:00 with a break 13:00–14:00, default, and says «Create schedule»', async () => {
    const s = await setup();
    expect(s.params('staff.settings.get')).toEqual([{}]);
    expect(s.inDoc('staff-schedule-form')?.getAttribute('aria-label')).toBe('New');
    expect([s.field('name').label, s.field('name').placeholder, s.field('effective_from').type, s.field('effective_until').label, s.field('is_default').checked]).toEqual([
      'Schedule',
      'Schedule name',
      'date',
      'Effective until',
      true,
    ]);
    const week = [0, 1, 2, 3, 4, 5, 6].map((d) => [
      s.day(d, 'working').textContent?.trim(),
      s.day(d, 'working').checked,
      s.day(d, 'start')?.value ?? null,
      s.day(d, 'end')?.value ?? null,
      s.day(d, 'break_start')?.value ?? null,
      s.day(d, 'break_end')?.value ?? null,
    ]);
    expect(week).toEqual([
      ['Monday', true, '09:00', '18:00', '13:00', '14:00'],
      ['Tuesday', true, '09:00', '18:00', '13:00', '14:00'],
      ['Wednesday', true, '09:00', '18:00', '13:00', '14:00'],
      ['Thursday', true, '09:00', '18:00', '13:00', '14:00'],
      ['Friday', true, '09:00', '18:00', '13:00', '14:00'],
      ['Saturday', false, null, null, null, null],
      ['Sunday', false, null, null, null, null],
    ]);
    expect(s.day(5, 'off').textContent?.trim()).toBe('Off');
    expect([s.day(0, 'start').type, s.day(0, 'break_start').label]).toEqual(['time', 'Break start']);
    expect(s.save().textContent?.trim()).toBe('Create schedule');
  });

  it('proposes the business’s working day from Staff › Settings, its break in the middle of the day, and sends it', async () => {
    const s = await setup(null, 'en', true, EARLY);
    const monday = ['start', 'end', 'break_start', 'break_end'].map((part) => s.day(0, part).value);
    expect(monday).toEqual(['08:00', '16:00', '11:45', '12:15']);
    expect([1, 2, 3, 4].map((d) => s.day(d, 'start').value)).toEqual(['08:00', '08:00', '08:00', '08:00']);
    s.answer(201, SUMMER);
    await click(s.save());
    const sent = (s.sent()[0].body as { days: unknown[] }).days;
    expect(sent).toEqual(
      [0, 1, 2, 3, 4].map((weekday) => ({ weekday, start_time: '08:00', end_time: '16:00', break_start: '11:45', break_end: '12:15' })),
    );
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
          days: [0, 2, 3, 4].map((weekday) => day(weekday, '18:00', ['13:00', '14:00'])).concat(day(5, '14:00', ['13:00', '14:00'])),
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

  // The week's refusal is a line of its own on top of the week, under no single field: any change the person makes to
  // the week takes it away at once, and only it (hub#1448).
  describe('a week without working days: a change to the week takes it away before saving again', () => {
    const NO_DAYS = 'A schedule needs at least one working day with hours.';
    const NAME = 'Use another name: this member already has a schedule with it.';

    async function refusedWeek(fields: Record<string, string> = { days: NO_DAYS }) {
      const s = await setup();
      s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields } });
      await click(s.save());
      return s;
    }

    it.each([
      ['ticking a day', (s: Awaited<ReturnType<typeof refusedWeek>>) => ionChecked(s.day(6, 'working'), true)],
      ['typing a working day’s start', (s: Awaited<ReturnType<typeof refusedWeek>>) => ionValue(s.day(1, 'start'), '08:30', 'ionInput')],
    ])('%s', async (_, change) => {
      const s = await refusedWeek();
      expect(s.inDoc('staff-schedule-form-week-error')?.textContent).toContain(NO_DAYS);
      await change(s);
      expect(s.inDoc('staff-schedule-form-week-error')).toBeNull();
      expect(s.sent()).toHaveLength(1);
    });

    it('another field’s refusal stays under it', async () => {
      const s = await refusedWeek({ name: NAME, days: NO_DAYS });
      await ionChecked(s.day(6, 'working'), true);
      expect(s.field('name').errorText).toBe(NAME);
      expect(s.inDoc('staff-schedule-form-week-error')).toBeNull();
    });
  });

  // A day's refusal is a line under that day: the server names it by the day's position among those sent
  // (`days.<i>.<field>`), and any change the person makes to that day takes its line away at once (hub#1460).
  describe('a refused day: a change to that day takes its reason away before saving again, and only its own', () => {
    const ORDER = 'The start time must be before the end time.';
    const PAIR = 'A break needs both a start and an end (or neither).';
    const INSIDE = 'The break must fall within the working hours.';

    /** Monday is left out, so Wednesday is the second day sent (`days.1`) and Thursday the third (`days.2`). */
    async function refusedDays(fields: Record<string, string> = { 'days.1.end_time': ORDER, 'days.2.break_end': PAIR }) {
      const s = await setup();
      await ionChecked(s.day(0, 'working'), false);
      s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields } });
      await click(s.save());
      return s;
    }
    const reason = (s: Awaited<ReturnType<typeof refusedDays>>, weekday: number) =>
      s.inDoc(`staff-schedule-form-day-${weekday}-error`)?.textContent?.trim() ?? null;
    /** Typing in a field as a browser does: the native `input` bubbles up from the field, then Ionic says the value. */
    async function typeIn(field: Element | null, value: string): Promise<void> {
      field?.dispatchEvent(new Event('input', { bubbles: true }));
      await ionValue(field, value, 'ionInput');
    }

    it.each([
      ['typing the refused hour', (s: Awaited<ReturnType<typeof refusedDays>>) => typeIn(s.day(2, 'end'), '19:00')],
      ['typing another of its hours', (s: Awaited<ReturnType<typeof refusedDays>>) => typeIn(s.day(2, 'start'), '08:00')],
      ['typing its break', (s: Awaited<ReturnType<typeof refusedDays>>) => typeIn(s.day(2, 'break_end'), '14:30')],
      ['unticking it', (s: Awaited<ReturnType<typeof refusedDays>>) => ionChecked(s.day(2, 'working'), false)],
    ])('%s', async (_, change) => {
      const s = await refusedDays();
      expect([reason(s, 2), reason(s, 3)]).toEqual([ORDER, PAIR]);
      await change(s);
      expect([reason(s, 2), reason(s, 3)]).toEqual([null, PAIR]);
      expect(s.sent()).toHaveLength(1);
    });

    it('a change to another day, or to a field off the week, leaves it', async () => {
      const s = await refusedDays();
      await ionChecked(s.day(0, 'working'), true);
      await typeIn(s.day(4, 'end'), '17:00');
      await typeIn(s.field('name'), 'Winter');
      expect([reason(s, 0), reason(s, 2), reason(s, 3), reason(s, 4)]).toEqual([null, ORDER, PAIR, null]);
    });

    it('a day refused for two things says the first, and a change to it takes the day’s line away whole', async () => {
      const s = await refusedDays({ 'days.1.break_end': INSIDE, 'days.1.end_time': ORDER });
      expect(reason(s, 2)).toBe(INSIDE);
      await typeIn(s.day(2, 'break_start'), '13:30');
      expect(reason(s, 2)).toBeNull();
    });

    it('a new try says every reason again', async () => {
      const s = await refusedDays();
      await typeIn(s.day(2, 'end'), '19:00');
      s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { 'days.1.end_time': ORDER } } });
      await click(s.save());
      expect([reason(s, 2), reason(s, 3)]).toEqual([ORDER, null]);
    });
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

  it('a refused day’s reason goes as soon as that day is changed, as when creating one', async () => {
    const s = await setup(SUMMER);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the fields.', fields: { 'days.0.end_time': 'The start time must be before the end time.' } } });
    await click(s.save());
    expect(s.inDoc('staff-schedule-form-day-1-error')?.textContent).toContain('The start time must be before the end time.');
    await ionChecked(s.day(1, 'working'), false);
    expect(s.inDoc('staff-schedule-form-day-1-error')).toBeNull();
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

describe('ScheduleFormModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('staff-schedule-form'),
      change: () => ionValue(s.field('name'), 'Winter', 'ionInput'),
      restore: () => ionValue(s.field('name'), '', 'ionInput'),
    });
  });
});
