// How the task screens paint days, moments, tones and tags (pages never format by hand). A due date is
// a pure day: painted without moving it across time zones (tasks#23: 00:00 UTC went back a day west of
// Greenwich). «Today» is the business's day, Europe/Madrid in phase 1 (WORKBOOK «Antes de empezar»).
import { describe, expect, it } from 'vitest';

import {
  BUSINESS_TIME_ZONE,
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

describe('task format', () => {
  it('reads today in Madrid, not in UTC nor in the browser', () => {
    expect(BUSINESS_TIME_ZONE).toBe('Europe/Madrid');
    // 23:30 UTC on 14 October is already the 15th in Madrid (UTC+2).
    expect(businessToday(new Date('2026-10-14T23:30:00Z'))).toBe('2026-10-15');
    expect(businessToday(new Date('2026-10-14T21:30:00Z'))).toBe('2026-10-14');
  });

  it('says overdue before today and due today on the day, only while the task is open', () => {
    const now = new Date('2026-10-15T10:00:00Z');
    expect(dueTone('2026-10-14', 'todo', now)).toBe('overdue');
    expect(dueTone('2026-10-15', 'in_progress', now)).toBe('today');
    expect(dueTone('2026-10-16', 'blocked', now)).toBe('none');
    expect(dueTone(null, 'todo', now)).toBe('none');
    // A closed task is not late: there is nothing left to do with it.
    expect(dueTone('2026-10-01', 'done', now)).toBe('none');
    expect(dueTone('2026-10-01', 'cancelled', now)).toBe('none');
  });

  it('paints a due day in the order of the language, the same day everywhere, and a dash without one', () => {
    expect(formatDay('2026-09-01', 'es')).toBe('01/09/2026');
    expect(formatDay('2026-09-01', 'en')).toBe('01/09/2026');
    expect(formatDay(null, 'es')).toBe('—');
    expect(formatDay('', 'es')).toBe('—');
  });

  it('paints a moment with its time in Madrid', () => {
    expect(formatMoment('2026-10-14T23:30:00Z', 'es')).toBe('15/10/2026, 01:30');
    expect(formatMoment(null, 'es')).toBe('—');
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
