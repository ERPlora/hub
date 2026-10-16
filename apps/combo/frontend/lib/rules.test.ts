// The sentence that states the rule the till applies to a course, as the old builder said it:
// «Compulsory · pick 1 · up to 1 · no repeats». The obligation IS the minimum: there is no other switch.
import { describe, expect, it } from 'vitest';

import { courseRule } from './rules';

const words: Record<string, string> = {
  'combo.rule.required': 'Compulsory · pick {min}',
  'combo.rule.requiredRange': 'Compulsory · pick at least {min}',
  'combo.rule.optional': 'Optional',
  'combo.rule.max': 'up to {max}',
  'combo.rule.noCeiling': 'no limit',
  'combo.rule.repeat': 'may repeat',
  'combo.rule.noRepeat': 'no repeats',
};
const t = (key: string, named?: Record<string, unknown>) =>
  (words[key] ?? key).replace(/\{(\w+)\}/g, (_, name: string) => String(named?.[name]));

describe('courseRule', () => {
  it('says a compulsory course of one pick', () => {
    expect(courseRule({ min_choices: 1, max_choices: 1, allow_repeat: false }, t)).toBe('Compulsory · pick 1 · up to 1 · no repeats');
  });

  it('says «at least» when the ceiling is above the floor, and no limit for 0', () => {
    expect(courseRule({ min_choices: 2, max_choices: 0, allow_repeat: true }, t)).toBe('Compulsory · pick at least 2 · no limit · may repeat');
  });

  it('says an optional course', () => {
    expect(courseRule({ min_choices: 0, max_choices: 3, allow_repeat: false }, t)).toBe('Optional · up to 3 · no repeats');
  });
});
