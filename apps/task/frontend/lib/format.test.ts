// How the task screens paint days, moments, tones and tags (pages never format by hand). A due date is
// a pure day: painted without moving it across time zones (tasks#23: 00:00 UTC went back a day west of
// Greenwich). «Today» is the business's day, on the clock it is given (hub#779; WORKBOOK «Antes de empezar»).
import { describe, expect, it } from 'vitest';

import {
  businessToday,
  dueTone,
  formatDay,
  formatMoment,
  isClosed,
  parseTags,
  PRIORITY_TONE,
  STATUS_TONE,
  tagsText,
} from './format';

const MADRID = 'Europe/Madrid';
const CANARY = 'Atlantic/Canary';

describe('task format', () => {
  it('reads today on the clock it is given, not in UTC nor in the browser', () => {
    // 23:30 UTC on 14 October is already the 15th in Madrid (UTC+2).
    expect(businessToday(MADRID, new Date('2026-10-14T23:30:00Z'))).toBe('2026-10-15');
    expect(businessToday(MADRID, new Date('2026-10-14T21:30:00Z'))).toBe('2026-10-14');
    // 23:30 UTC on 2 November is still the 2nd in the Canaries (UTC) and the 3rd in Madrid (hub#779).
    expect(businessToday(CANARY, new Date('2026-11-02T23:30:00Z'))).toBe('2026-11-02');
    expect(businessToday(MADRID, new Date('2026-11-02T23:30:00Z'))).toBe('2026-11-03');
  });

  it("is due today until the business's midnight, not the deployment's (hub#779)", () => {
    const night = new Date('2026-11-02T23:30:00Z');
    expect(dueTone('2026-11-02', 'todo', CANARY, night)).toBe('today');
    expect(dueTone('2026-11-02', 'todo', MADRID, night)).toBe('overdue');
  });

  it('says overdue before today and due today on the day, only while the task is open', () => {
    const now = new Date('2026-10-15T10:00:00Z');
    expect(dueTone('2026-10-14', 'todo', MADRID, now)).toBe('overdue');
    expect(dueTone('2026-10-15', 'in_progress', MADRID, now)).toBe('today');
    expect(dueTone('2026-10-16', 'blocked', MADRID, now)).toBe('none');
    expect(dueTone(null, 'todo', MADRID, now)).toBe('none');
    // A closed task is not late: there is nothing left to do with it.
    expect(dueTone('2026-10-01', 'done', MADRID, now)).toBe('none');
    expect(dueTone('2026-10-01', 'cancelled', MADRID, now)).toBe('none');
  });

  it('paints a due day in the order of the language, the same day everywhere, and a dash without one', () => {
    expect(formatDay('2026-09-01', 'es')).toBe('01/09/2026');
    expect(formatDay('2026-09-01', 'en')).toBe('01/09/2026');
    expect(formatDay(null, 'es')).toBe('—');
    expect(formatDay('', 'es')).toBe('—');
  });

  it('paints a moment with its time on the clock it is given', () => {
    expect(formatMoment('2026-10-14T23:30:00Z', 'es', MADRID)).toBe('15/10/2026, 01:30');
    expect(formatMoment('2026-11-02T23:30:00Z', 'es', CANARY)).toBe('02/11/2026, 23:30');
    expect(formatMoment(null, 'es', MADRID)).toBe('—');
  });

  it('until the business answers it is on the device, never a zone written by hand', () => {
    const moment = new Date('2026-11-02T23:30:00Z');
    const device = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' });
    expect(businessToday(undefined, moment)).toBe(device.format(moment));
  });

  it('gives each status and priority a tone, colour never the only carrier (the label goes inside)', () => {
    expect(STATUS_TONE).toEqual({ todo: 'neutral', in_progress: 'info', blocked: 'warning', done: 'success', cancelled: 'danger' });
    expect(PRIORITY_TONE).toEqual({ low: 'neutral', medium: 'info', high: 'warning', urgent: 'danger' });
    expect(['done', 'cancelled', 'todo'].map((s) => isClosed(s as 'todo'))).toEqual([true, true, false]);
  });

  it('reads tags from a comma-separated text, trimmed and once each, and writes them back', () => {
    expect(parseTags(' stock, urgent ,,stock ')).toEqual(['stock', 'urgent']);
    expect(parseTags('')).toEqual([]);
    expect(tagsText(['stock', 'urgent'])).toBe('stock, urgent');
  });
});
