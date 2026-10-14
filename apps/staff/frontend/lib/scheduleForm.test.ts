// The week of a schedule (STAFF-F13, F14): one row per weekday (Monday = 0) with «works» and its
// start, end and optional break; a new schedule proposes Monday to Friday, 09:00 to 18:00. Only the
// working days travel, in weekday order (a weekday not sent is a day off); a break is sent with both
// ends or not at all. The server's 422 names a day by its position in what was sent
// (`days.<i>.<field>`): it is turned back into the weekday it belongs to, so the message sits under
// that day's row.
import { describe, expect, it } from 'vitest';

import type { ScheduleOut } from '../operations';
import { blankScheduleForm, dayErrors, daysPayload, defaultWeek, scheduleFormFromRecord } from './scheduleForm';

describe('defaultWeek', () => {
  it('proposes Monday to Friday from 09:00 to 18:00, no break, the weekend off', () => {
    const week = defaultWeek();
    expect(week.map((d) => [d.weekday, d.working, d.start, d.end, d.breakStart, d.breakEnd])).toEqual([
      [0, true, '09:00', '18:00', '', ''],
      [1, true, '09:00', '18:00', '', ''],
      [2, true, '09:00', '18:00', '', ''],
      [3, true, '09:00', '18:00', '', ''],
      [4, true, '09:00', '18:00', '', ''],
      [5, false, '09:00', '18:00', '', ''],
      [6, false, '09:00', '18:00', '', ''],
    ]);
  });
});

describe('blankScheduleForm', () => {
  it('is «Default» only for the member’s first one: a second (a summer one) must not take it over', () => {
    expect(blankScheduleForm({ isDefault: true })).toMatchObject({ name: '', effective_from: '', effective_until: '', is_default: true });
    expect(blankScheduleForm({ isDefault: false }).is_default).toBe(false);
  });
});

describe('daysPayload', () => {
  it('sends the working days only, with their break when it has both ends', () => {
    const week = defaultWeek().map((d) => (d.weekday === 0 ? { ...d, breakStart: '13:00', breakEnd: '14:00' } : d));
    week[1] = { ...week[1], working: false };
    expect(daysPayload(week)).toEqual([
      { weekday: 0, start_time: '09:00', end_time: '18:00', break_start: '13:00', break_end: '14:00' },
      { weekday: 2, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
      { weekday: 3, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
      { weekday: 4, start_time: '09:00', end_time: '18:00', break_start: null, break_end: null },
    ]);
  });

  it('a break with one end goes as it is, for the server to say «the break needs a start and an end»', () => {
    const week = defaultWeek();
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
