// The free times of the booking panel go in one tab per span of the professional's day: every time the server
// gives lands in the span it starts in, and the tab open at first is the one holding the chosen time or, if
// none does, the first with a free time.
import { describe, expect, it } from 'vitest';

import { defaultWindow, groupByWindow } from './free-times';

const at = (time: string) => `2026-10-19T${time}:00+02:00`;
const slot = (time: string) => ({ start: at(time), end: at(time), within_notice: false, staff_ids: ['s1'] });
const MORNING = { start: at('10:00'), end: at('14:00') };
const AFTERNOON = { start: at('16:00'), end: at('20:00') };

describe('groupByWindow', () => {
  it('puts each free time in the span it starts in, in order', () => {
    const groups = groupByWindow([MORNING, AFTERNOON], [slot('10:00'), slot('13:30'), slot('16:00'), slot('19:15')]);
    expect(groups.map((group) => [group.start, group.end, group.slots.map((s) => s.start.slice(11, 16))])).toEqual([
      [MORNING.start, MORNING.end, ['10:00', '13:30']],
      [AFTERNOON.start, AFTERNOON.end, ['16:00', '19:15']],
    ]);
  });

  it('keeps a span with no free time, and never loses a time the server gives', () => {
    expect(groupByWindow([MORNING, AFTERNOON], [slot('09:30')]).map((group) => group.slots.length)).toEqual([1, 0]);
  });

  it('has no tab when the professional does not work that day', () => {
    expect(groupByWindow([], [])).toEqual([]);
  });
});

describe('defaultWindow', () => {
  const groups = groupByWindow([MORNING, AFTERNOON], [slot('10:00'), slot('16:30')]);

  it('opens the span that holds the chosen time', () => {
    expect(defaultWindow(groups, '2026-10-19', '16:45')).toBe(1);
    expect(defaultWindow(groups, '2026-10-19', '10:00')).toBe(0);
  });

  it('without a chosen time inside a span, opens the first span with a free time', () => {
    const full = groupByWindow([MORNING, AFTERNOON], [slot('16:30')]);
    expect(defaultWindow(full, '2026-10-19', '')).toBe(1);
    expect(defaultWindow(full, '2026-10-19', '15:00')).toBe(1);
    expect(defaultWindow(full, '2026-10-19', '14:00')).toBe(1);
  });

  it('opens the first span when none has a free time', () => {
    expect(defaultWindow(groupByWindow([MORNING, AFTERNOON], []), '2026-10-19', '')).toBe(0);
  });
});
