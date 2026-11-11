// @vitest-environment node
// The time budgets of the hub's Vitest run follow the machine's load (hub#765): Vitest's own (5 s a test, 10 s a hook,
// 1 s a `vi.waitFor`) stretched as the machine, with the run's own workers, slows down.
import { describe, expect, it } from 'vitest';

import { loadScale, scaleWaitFor } from './vitest.load';

describe('loadScale', () => {
  it('counts the run\'s own workers in the load it will run under: Vitest\'s one per core but one', () => {
    expect(loadScale([0, 0, 0], 15)).toBeCloseTo(1.87, 2);
    expect(loadScale([0, 0, 0], 15, 14)).toBeCloseTo(1.87, 2);
    expect(loadScale([0, 0, 0], 1)).toBe(2);
  });

  it('is 1 while the machine\'s load and the run\'s workers fit in half its cores', () => {
    expect(loadScale([0, 0, 0], 16, 8)).toBe(1);
    expect(loadScale([2, 1, 0], 15, 5)).toBe(1);
  });

  it('is twice that load per core above: the CPU slowdown measured at load ~80 over 15 cores', () => {
    expect(loadScale([31, 20, 5], 10, 9)).toBe(8);
    expect(loadScale([100, 90, 80], 15, 14)).toBeCloseTo(15.2, 5);
    expect(loadScale([25, 16, 18], 15, 14)).toBeCloseTo(5.2, 5);
  });

  it('follows the busier of the last minute and the last five, never the last fifteen', () => {
    expect(loadScale([30, 60, 10], 15, 15)).toBe(10);
    expect(loadScale([60, 30, 10], 15, 15)).toBe(10);
    expect(loadScale([1, 1, 90], 15, 4)).toBe(1);
  });

  it('is 1 when the machine reports no load (Windows) and has cores to spare, or gives no number', () => {
    expect(loadScale([], 15, 4)).toBe(1);
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
