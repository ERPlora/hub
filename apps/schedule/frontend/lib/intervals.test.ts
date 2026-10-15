// The opening intervals as the forms edit them and the tables paint them (SCHEDULE-F01, F02, F04, F05):
// one line per interval, an open day needs every line complete, a closed one sends none; a day reads
// «Closed», «Open 24 hours», «Not set» or its intervals «10:00–14:00 · 17:00–20:00».
import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { ALL_DAY, blankRows, hoursSummary, isAllDay, payloadOf, rowsOf, statusOf } from './intervals';

function translator(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return (key: string) => i18n.global.t(key);
}

describe('the lines of the editor', () => {
  it('come from the stored intervals as HH:MM, or one blank line', () => {
    expect(rowsOf([{ open_time: '10:00:00', close_time: '14:00:00' }])).toEqual([{ open_time: '10:00', close_time: '14:00' }]);
    expect(blankRows()).toEqual([{ open_time: '', close_time: '' }]);
    expect(rowsOf([])).toEqual(blankRows());
  });

  it('00:00–00:00 alone is open 24 hours', () => {
    expect(isAllDay([ALL_DAY])).toBe(true);
    expect(isAllDay([ALL_DAY, { open_time: '10:00', close_time: '11:00' }])).toBe(false);
    expect(isAllDay([{ open_time: '09:00', close_time: '18:00' }])).toBe(false);
  });
});

describe('payloadOf', () => {
  it('sends every complete line of an open day', () => {
    expect(
      payloadOf(false, [
        { open_time: '10:00', close_time: '14:00' },
        { open_time: '17:00', close_time: '20:00' },
      ]),
    ).toEqual([
      { open_time: '10:00', close_time: '14:00' },
      { open_time: '17:00', close_time: '20:00' },
    ]);
  });

  it('a closed day sends none', () => {
    expect(payloadOf(true, [{ open_time: '10:00', close_time: '' }])).toEqual([]);
  });

  it('a line half filled, or no line, is a mistake (null), never «open all day»', () => {
    expect(payloadOf(false, [{ open_time: '10:00', close_time: '' }])).toBeNull();
    expect(payloadOf(false, [])).toBeNull();
  });
});

describe('hoursSummary and statusOf', () => {
  const t = translator('en');

  it('a day reads its intervals in the clock of the language', () => {
    const day = { is_set: true, is_closed: false, intervals: [
      { open_time: '10:00:00', close_time: '14:00:00' },
      { open_time: '17:00:00', close_time: '20:00:00' },
    ] };
    expect(hoursSummary(day, translator('es'), 'es')).toBe('10:00–14:00 · 17:00–20:00');
    expect(statusOf(day, t)).toBe('Open');
  });

  it('closed, open 24 hours and not set', () => {
    expect(hoursSummary({ is_set: true, is_closed: true, intervals: [] }, t, 'en')).toBe('Closed');
    expect(statusOf({ is_set: true, is_closed: true, intervals: [] }, t)).toBe('Closed');
    expect(hoursSummary({ is_set: true, is_closed: false, intervals: [{ open_time: '00:00:00', close_time: '00:00:00' }] }, t, 'en')).toBe(
      'Open 24 hours',
    );
    expect(hoursSummary({ is_set: false, is_closed: false, intervals: [] }, t, 'en')).toBe('Not set');
    expect(statusOf({ is_set: false, is_closed: false, intervals: [] }, t)).toBe('—');
  });

  it('an exception (no is_set) open with hours reads them; closed reads «Closed»', () => {
    expect(hoursSummary({ is_closed: false, intervals: [{ open_time: '09:00:00', close_time: '13:00:00' }] }, t, 'en')).toBe(
      '09:00 AM–01:00 PM',
    );
    expect(hoursSummary({ is_closed: true, intervals: [] }, translator('es'), 'es')).toBe('Cerrado');
  });
});
