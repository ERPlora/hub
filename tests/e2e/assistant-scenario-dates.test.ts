// @vitest-environment node
// The days of a scenario: `{today}`, `{today±N}` and `{<weekday>}` are written as days of the run, so a booking «on
// Friday» and the checks that look for it name the same day.
import { describe, expect, it } from 'vitest';

import { parseScenario, type Scenario } from './assistant-scenario';
import { datedScenario, nextWeekday } from './assistant-scenario-dates';

const parsed = (changes: Record<string, unknown>): Scenario =>
  parseScenario(
    JSON.stringify({
      id: 's99-dates',
      title: 'Dates',
      vertical: 'restaurant',
      seed: 'restaurant.es',
      language: 'es',
      owner: { persona: 'Ana', goal: 'Reservar', upFront: ['Para el viernes'], ifAsked: [] },
      opening: 'Reserva',
      offered: [],
      writes: [],
      expect: [{ says: 'x', sql: 'select 1', equals: '1' }],
      maxTurns: 2,
      ...changes,
    }),
    'qa/scenarios/x.json',
  );

describe('datedScenario', () => {
  it('writes the days of the run into every text of the scenario', () => {
    const scenario = datedScenario(parsed({ opening: 'Para el {friday}', expect: [{ says: 'x', sql: "select '{today}', '{today+1}'", equals: '{today-1}' }] }), '2026-11-19');
    expect(scenario.opening).toBe('Para el 2026-11-20');
    expect(scenario.expect[0]).toEqual({ says: 'x', sql: "select '2026-11-19', '2026-11-20'", equals: '2026-11-18' });
  });

  it('takes the next weekday strictly after today', () => {
    expect(nextWeekday('2026-11-19', 'friday')).toBe('2026-11-20');
    expect(nextWeekday('2026-11-20', 'friday')).toBe('2026-11-27');
    expect(nextWeekday('2026-11-19', 'monday')).toBe('2026-11-23');
  });
});
