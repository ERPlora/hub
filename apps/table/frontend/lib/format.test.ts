// How the table screens paint times, durations and money (pages never format by hand): the business's
// clock (its IANA zone, from `table.settings.get`), the page's language, and an open check's time in
// amber and red after the room settings' minutes.
import { describe, expect, it } from 'vitest';

import { clock, clockTime, durationMinutes, durationTone, formatMoney, minutesSince } from './format';

const NOW = new Date('2026-10-14T19:40:00Z'); // 21:40 in Madrid (summer time)

describe('minutesSince', () => {
  it('counts whole minutes up to now, never below zero, and nothing without a moment', () => {
    expect(minutesSince('2026-10-14T19:05:10Z', NOW)).toBe(34);
    expect(minutesSince('2026-10-14T19:50:00Z', NOW)).toBe(0);
    expect(minutesSince(null, NOW)).toBeNull();
    expect(minutesSince('not a date', NOW)).toBeNull();
  });
});

describe('durationMinutes', () => {
  it('runs until now for an open check and until its close for a finished one', () => {
    expect(durationMinutes('2026-10-14T19:00:00Z', null, NOW)).toBe(40);
    expect(durationMinutes('2026-10-14T18:00:00Z', '2026-10-14T19:15:00Z', NOW)).toBe(75);
  });
});

describe('durationTone', () => {
  const room = { timer_warning_minutes: 60, timer_critical_minutes: 90 };
  it('turns an open check amber and red, never a finished one', () => {
    expect(durationTone('open', 59, room)).toBe('ok');
    expect(durationTone('open', 60, room)).toBe('warning');
    expect(durationTone('open', 90, room)).toBe('critical');
    expect(durationTone('closed', 200, room)).toBe('ok');
  });
});

describe('clock', () => {
  it('is the business wall clock, in the reader’s language', () => {
    expect(clock('2026-10-14T19:00:00Z', 'es', 'Europe/Madrid')).toBe('21:00');
    expect(clock('2026-10-14T19:00:00Z', 'en', 'Europe/Madrid')).toBe('9:00 PM');
    expect(clock(null, 'es', 'Europe/Madrid')).toBe('');
  });
});

describe('clockTime', () => {
  it('says only the time on the business’s today, and the day otherwise (the year if another one)', () => {
    expect(clockTime('2026-10-14T18:30:00Z', NOW, 'es', 'Europe/Madrid')).toBe('20:30');
    expect(clockTime('2026-10-12T18:30:00Z', NOW, 'es', 'Europe/Madrid')).toMatch(/^12 oct.*20:30$/);
    expect(clockTime('2025-10-12T18:30:00Z', NOW, 'es', 'Europe/Madrid')).toMatch(/2025/);
    expect(clockTime(null, NOW, 'es', 'Europe/Madrid')).toBe('—');
  });
});

describe('formatMoney', () => {
  it('paints cents as euros, and nothing charged as a dash, never zero', () => {
    expect(formatMoney(2250, 'es')).toBe('22,50\u00a0€');
    expect(formatMoney(2250, 'en')).toBe('€22.50');
    expect(formatMoney(null, 'es')).toBe('—');
  });
});
