// Where «By professional · Day» opens, as the agendas of Google Calendar or Fresha: today, half an hour before the
// business's time now; another day, at the hour the business opens (Schedules); with neither, at the start of the
// calendar. It scrolls there when the day, the business's zone or its hours change, never as the clock ticks.
import { describe, expect, it } from 'vitest';
import { nextTick, ref, shallowRef } from 'vue';

import { mountComposable } from '../__tests__/mount-appointment';
import { type GridStart, startMinute, useGridStart } from './useGridStart';

const ZONE = 'Europe/Madrid';
const TODAY = '2026-10-19';
/** 16:10 in Madrid on TODAY. */
const NOW = new Date('2026-10-19T16:10:00+02:00');
const OPEN_9_TO_20: Array<[number, number]> = [
  [0, 540],
  [1200, 1440],
];
const at = (over: Partial<GridStart> = {}): GridStart => ({ day: TODAY, zone: ZONE, now: NOW, closed: OPEN_9_TO_20, windowStart: 480, ...over });

describe('startMinute', () => {
  it('today, half an hour before the business’s time now', () => {
    expect(startMinute(at())).toBe(16 * 60 + 10 - 30);
    expect(startMinute(at({ zone: 'America/New_York' })), 'the business’s clock, not the device’s').toBe(10 * 60 + 10 - 30);
  });

  it('today before the calendar starts, at its start', () => {
    expect(startMinute(at({ now: new Date('2026-10-19T07:50:00+02:00') }))).toBe(480);
  });

  it('another day, at the hour the business opens; with no hours or closed all day, at the start of the calendar', () => {
    expect(startMinute(at({ day: '2026-10-20' }))).toBe(540);
    expect(startMinute(at({ day: '2026-10-20', closed: [] }))).toBe(480);
    expect(startMinute(at({ day: '2026-10-20', closed: [[0, 1440]] }))).toBe(480);
  });
});

describe('useGridStart', () => {
  it('scrolls the grid there once it is on screen and when the day changes, not as the clock ticks', async () => {
    const scroller = ref<{ scrollLeft: number } | null>(null);
    const state = shallowRef(at());
    await mountComposable(() => useGridStart(scroller as never, () => state.value, 4));
    scroller.value = { scrollLeft: 0 };
    await nextTick();
    expect(scroller.value.scrollLeft).toBe((16 * 60 + 10 - 30 - 480) * 4);

    scroller.value.scrollLeft = 12;
    state.value = at({ now: new Date('2026-10-19T16:11:00+02:00') });
    await nextTick();
    expect(scroller.value.scrollLeft, 'the person’s own scroll stays').toBe(12);

    state.value = at({ day: '2026-10-20' });
    await nextTick();
    expect(scroller.value.scrollLeft).toBe((540 - 480) * 4);
  });
});
