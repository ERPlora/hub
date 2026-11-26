// How many of a group of choices the customer picks, said above its options: a dish's modifier group (0 = no ceiling)
// or a set menu's course.
import { describe, expect, it } from 'vitest';

import { choiceRule } from './choice-rule';

describe('choiceRule', () => {
  it.each([
    [0, 0, ['online_order.menu.rule.optional', {}]],
    [0, 2, ['online_order.menu.rule.optionalUpTo', { max: 2 }]],
    [1, 1, ['online_order.menu.rule.exactly', { min: 1 }]],
    [2, 2, ['online_order.menu.rule.exactly', { min: 2 }]],
    [1, 3, ['online_order.menu.rule.between', { min: 1, max: 3 }]],
    [1, 0, ['online_order.menu.rule.atLeast', { min: 1 }]],
  ])('reads %i to %i as its text', (min, max, said) => {
    expect(choiceRule(min, max)).toEqual(said);
  });
});
