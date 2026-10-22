// The week of a schedule (STAFF-F13, F14): one row per weekday (Monday = 0) with «works» and its
// start, end and optional break; a new schedule proposes Monday to Friday with the business's default
// working day (Staff › Settings, STAFF-F22), its break in the middle of the day. Only the
// working days travel, in weekday order (a weekday not sent is a day off); a break is sent with both
// ends or not at all. The server's 422 names a day by its position in what was sent
// (`days.<i>.<field>`): it is turned back into the weekday it belongs to, so the message sits under
// that day's row.
import { describe, expect, it } from 'vitest';

import type { ScheduleOut } from '../operations';
import {
  blankScheduleForm,
  dayErrors,
  daysPayload,
  DEFAULT_WORKDAY,
  defaultWeek,
  proposedBreak,
  scheduleFormFromRecord,
  type Workday,
  workdayFromSettings,
} from './scheduleForm';

const NO_BREAK: Workday = { start: '09:00', end: '18:00', breakMinutes: 0 };
const EARLY: Workday = { start: '08:00', end: '16:00', breakMinutes: 30 };
const row = (d: { weekday: number; working: boolean; start: string; end: string; breakStart: string; breakEnd: string }) => [
  d.weekday,
  d.working,
  d.start,
  d.end,
  d.breakStart,
  d.breakEnd,
];

describe('defaultWeek', () => {
  it('proposes Monday to Friday with the settings’ own defaults until the saved ones arrive: 09:00 to 18:00, break 13:00 to 14:00', () => {
    expect(DEFAULT_WORKDAY).toEqual({ start: '09:00', end: '18:00', breakMinutes: 60 });
    expect(defaultWeek().map(row)).toEqual([
      [0, true, '09:00', '18:00', '13:00', '14:00'],
      [1, true, '09:00', '18:00', '13:00', '14:00'],
      [2, true, '09:00', '18:00', '13:00', '14:00'],
      [3, true, '09:00', '18:00', '13:00', '14:00'],
      [4, true, '09:00', '18:00', '13:00', '14:00'],
      [5, false, '09:00', '18:00', '13:00', '14:00'],
      [6, false, '09:00', '18:00', '13:00', '14:00'],
    ]);
  });

  it('proposes the business’s working day on every weekday, worked or not (switching a day on proposes it too)', () => {
    expect(defaultWeek(EARLY).map(row)).toEqual([
      [0, true, '08:00', '16:00', '11:45', '12:15'],
      [1, true, '08:00', '16:00', '11:45', '12:15'],
      [2, true, '08:00', '16:00', '11:45', '12:15'],
      [3, true, '08:00', '16:00', '11:45', '12:15'],
      [4, true, '08:00', '16:00', '11:45', '12:15'],
      [5, false, '08:00', '16:00', '11:45', '12:15'],
      [6, false, '08:00', '16:00', '11:45', '12:15'],
    ]);
    expect(defaultWeek(NO_BREAK)[0]).toMatchObject({ breakStart: '', breakEnd: '' });
  });
});

describe('proposedBreak', () => {
  it('sits in the middle of the day, its start rounded down to the quarter hour', () => {
    expect(proposedBreak(DEFAULT_WORKDAY)).toEqual({ breakStart: '13:00', breakEnd: '14:00' });
    expect(proposedBreak(EARLY)).toEqual({ breakStart: '11:45', breakEnd: '12:15' });
    expect(proposedBreak({ start: '09:00', end: '18:00', breakMinutes: 45 })).toEqual({ breakStart: '13:00', breakEnd: '13:45' });
    expect(proposedBreak({ start: '07:30', end: '15:00', breakMinutes: 20 })).toEqual({ breakStart: '11:00', breakEnd: '11:20' });
    expect(proposedBreak({ start: '08:00', end: '08:50', breakMinutes: 40 })).toEqual({ breakStart: '08:00', breakEnd: '08:40' });
  });

  it('none for 0 minutes, nor in a day that cannot hold it (the server says why if it is sent)', () => {
    expect(proposedBreak(NO_BREAK)).toEqual({ breakStart: '', breakEnd: '' });
    expect(proposedBreak({ start: '09:00', end: '10:00', breakMinutes: 60 })).toEqual({ breakStart: '', breakEnd: '' });
    expect(proposedBreak({ start: '22:00', end: '06:00', breakMinutes: 30 })).toEqual({ breakStart: '', breakEnd: '' });
  });
});

describe('workdayFromSettings', () => {
  it('reads the working day of Staff › Settings', () => {
    expect(workdayFromSettings({ default_work_start: '08:00', default_work_end: '16:00', default_break_duration: 30 })).toEqual(EARLY);
  });
});

describe('blankScheduleForm', () => {
  it('is «Default» only for the member’s first one: a second (a summer one) must not take it over', () => {
    expect(blankScheduleForm({ isDefault: true })).toMatchObject({ name: '', effective_from: '', effective_until: '', is_default: true });
    expect(blankScheduleForm({ isDefault: false }).is_default).toBe(false);
  });

  it('proposes the working day it is given', () => {
    expect(blankScheduleForm({ isDefault: true, workday: EARLY }).week.map(row)).toEqual(defaultWeek(EARLY).map(row));
  });
});

describe('daysPayload', () => {
  it('sends the working days only, with their break when it has both ends', () => {
    const week = defaultWeek(NO_BREAK).map((d) => (d.weekday === 0 ? { ...d, breakStart: '13:00', breakEnd: '14:00' } : d));
    week[1] = { ...week[1], working: false };
    expect(daysPayload(week)).toEqual([
      { weekday: 0, start_time: '09:00', end_time: '18:00', break_start: '13:00', break_end: '14:00' },
      { weekday: 2, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
      { weekday: 3, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
      { weekday: 4, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
    ]);
  });

  it('a break with one end goes as it is, for the server to say «the break needs a start and an end»', () => {
    const week = defaultWeek(NO_BREAK);
    week[0] = { ...week[0], breakStart: '13:00' };
    expect(daysPayload(week)[0]).toMatchObject({ break_start: '13:00', break_end: null });
  });
});

describe('scheduleFormFromRecord (Edit · {name})', () => {
  it('fills name, validity, default and the week; a weekday missing is off', () => {
    const schedule: ScheduleOut = {
      id: 's1',
      member_id: 'm1',
      name: 'Summer',
      is_default: false,
      effective_from: '2026-06-01',
      effective_until: null,
      is_active: true,
      days: [{ weekday: 1, start_time: '08:00:00', end_time: '15:00:00', break_start: '11:00:00', break_end: '11:30:00' }],
    };
    const form = scheduleFormFromRecord(schedule);
    expect([form.name, form.effective_from, form.effective_until, form.is_default]).toEqual(['Summer', '2026-06-01', '', false]);
    expect(form.week.filter((d) => d.working).map((d) => [d.weekday, d.start, d.end, d.breakStart, d.breakEnd])).toEqual([
      [1, '08:00', '15:00', '11:00', '11:30'],
    ]);
    expect(form.week).toHaveLength(7);
  });

  it('a weekday it does not have proposes the business’s working day, for when it is switched on', () => {
    const schedule: ScheduleOut = {
      id: 's1',
      member_id: 'm1',
      name: 'Summer',
      is_default: false,
      effective_from: null,
      effective_until: null,
      is_active: true,
      days: [{ weekday: 1, start_time: '10:00:00', end_time: '14:00:00', break_start: null, break_end: null }],
    };
    const week = scheduleFormFromRecord(schedule, EARLY).week;
    expect([row(week[0]), row(week[1])]).toEqual([
      [0, false, '08:00', '16:00', '11:45', '12:15'],
      [1, true, '10:00', '14:00', '', ''],
    ]);
  });
});

describe('dayErrors', () => {
  it('names the weekday of each `days.<i>.<field>` error, by the position in what was sent', () => {
    const sent = [
      { weekday: 0, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
      { weekday: 3, start_time: '18:00', end_time: '09:00', break_start: null, break_end: null },
    ];
    expect(dayErrors({ 'days.1.end_time': 'The start time must be before the end time.', name: 'x' }, sent)).toEqual({
      3: 'The start time must be before the end time.',
    });
  });

  it('a day with two problems keeps the first; nothing sent, nothing named', () => {
    const sent = [{ weekday: 2, start_time: '09:00', end_time: '18:00', break_start: '13:00', break_end: null }];
    expect(dayErrors({ 'days.0.break_end': 'A', 'days.0.end_time': 'B' }, sent)).toEqual({ 2: 'A' });
    expect(dayErrors({ 'days.4.end_time': 'C' }, sent)).toEqual({});
  });
});
