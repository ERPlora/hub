// @vitest-environment node
// The time budgets of the hub's Vitest run follow the machine's load (hub#765): on an idle machine they are Vitest's
// own (5 s a test, 10 s a hook, 1 s a `vi.waitFor`), and on a loaded one they stretch as the machine slows down.
import { describe, expect, it } from 'vitest';

import { loadScale, scaleWaitFor } from './vitest.load';

describe('loadScale', () => {
  it('is 1 on an idle machine and while its load stays at half its cores or less', () => {
    expect(loadScale([0, 0, 0], 15)).toBe(1);
    expect(loadScale([7.5, 5, 3], 15)).toBe(1);
    expect(loadScale([3, 7.5, 9], 15)).toBe(1);
  });

  it('is twice the load per core above that: the CPU slowdown measured at load ~80 over 15 cores', () => {
    expect(loadScale([15, 10, 5], 15)).toBe(2);
    expect(loadScale([100, 90, 80], 15)).toBeCloseTo(13.33, 2);
    expect(loadScale([8, 4, 2], 4)).toBe(4);
  });

  it('follows the busier of the last minute and the last five, never the last fifteen', () => {
    expect(loadScale([30, 60, 10], 15)).toBe(8);
    expect(loadScale([60, 30, 10], 15)).toBe(8);
    expect(loadScale([1, 1, 90], 15)).toBe(1);
  });

  it('is 1 when the machine reports no load (Windows) or a reading that is no number', () => {
    expect(loadScale([], 15)).toBe(1);
    expect(loadScale([Number.NaN, Number.NaN, Number.NaN], 15)).toBe(1);
    expect(loadScale([60, 60, 60], 0)).toBe(1);
  });

  it('reads this machine by default: a number no smaller than 1', () => {
    const scale = loadScale();
    expect(Number.isFinite(scale)).toBe(true);
    expect(scale).toBeGreaterThanOrEqual(1);
  });
});

describe('scaleWaitFor', () => {
  it('gives a vi.waitFor without a budget its default second times the scale', () => {
    expect(scaleWaitFor(undefined, 3)).toEqual({ timeout: 3_000 });
  });

  it('scales the budget a vi.waitFor names, as a number or as an option, and keeps its interval', () => {
    expect(scaleWaitFor(2_000, 2.5)).toBe(5_000);
    expect(scaleWaitFor({ timeout: 400, interval: 20 }, 3)).toEqual({ timeout: 1_200, interval: 20 });
    expect(scaleWaitFor({ interval: 20 }, 2)).toEqual({ timeout: 2_000, interval: 20 });
  });

  it('leaves every budget as it is on an idle machine', () => {
    expect(scaleWaitFor(undefined, 1)).toEqual({ timeout: 1_000 });
    expect(scaleWaitFor(250, 1)).toBe(250);
    expect(scaleWaitFor({ timeout: 400, interval: 20 }, 1)).toEqual({ timeout: 400, interval: 20 });
  });

  it('gives whole milliseconds', () => {
    expect(scaleWaitFor(undefined, 13.333_333)).toEqual({ timeout: 13_333 });
    expect(scaleWaitFor(1_000, 1.000_6)).toBe(1_001);
  });
});
