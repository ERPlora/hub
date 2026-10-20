// flow: SALE-F11 — the rules of the options sheet (MODIFIER-F06): what a tap does in each kind of group,
// what the line carries and when «Add» waits.
import { describe, expect, it } from 'vitest';

import type { TargetGroupOut } from '../../../modifier/frontend/operations';
import {
  addedCents,
  choose,
  chosenIds,
  countOf,
  initialChoice,
  missingGroup,
  ruleOf,
  unchoose,
} from './modifierChoice';

const option = (id: string, price_delta = 0, is_default = false) => ({
  id,
  name: id,
  kitchen_name: '',
  price_delta,
  tax_category_key: null,
  is_default,
});

const group = (id: string, min: number, max: number, ids: string[], more: Partial<TargetGroupOut> = {}): TargetGroupOut => ({
  id,
  name: id,
  kitchen_name: '',
  min_choices: min,
  max_choices: max,
  allow_repeat: false,
  is_required: min > 0,
  options: ids.map((optionId) => option(optionId)),
  ...more,
});

describe('the rule each group says', () => {
  it('says «Choose N» when required, «Up to N» with a ceiling and «Optional» otherwise', () => {
    expect(ruleOf(group('a', 2, 3, ['x']))).toEqual({ key: 'sale.pos.options.choose', n: 2 });
    expect(ruleOf(group('b', 0, 3, ['x']))).toEqual({ key: 'sale.pos.options.upTo', n: 3 });
    expect(ruleOf(group('c', 0, 0, ['x']))).toEqual({ key: 'sale.pos.options.optional', n: 0 });
  });
});

describe('a tap', () => {
  it('starts with the defaults chosen, in the catalogue order', () => {
    const extras = group('extras', 0, 0, [], { options: [option('cheese', 100, true), option('bacon', 150), option('egg', 50, true)] });
    expect(chosenIds(initialChoice([extras]))).toEqual(['cheese', 'egg']);
  });

  it('swaps in a group of one: the new choice takes the old one out', () => {
    const doneness = group('doneness', 1, 1, ['rare', 'done']);
    let choice = choose(initialChoice([doneness]), doneness, 'rare');
    choice = choose(choice, doneness, 'done');
    expect(chosenIds(choice)).toEqual(['done']);
  });

  it('takes it out when the same one is tapped again in a group of one (it never gets stuck)', () => {
    const doneness = group('doneness', 1, 1, ['rare', 'done']);
    const choice = choose(choose(initialChoice([doneness]), doneness, 'rare'), doneness, 'rare');
    expect(chosenIds(choice)).toEqual([]);
  });

  it('adds up to the ceiling and refuses the next one, saying which group is full', () => {
    const sauces = group('sauces', 0, 2, ['ketchup', 'mayo', 'mustard']);
    let choice = choose(initialChoice([sauces]), sauces, 'ketchup');
    choice = choose(choice, sauces, 'mayo');
    const refused = choose(choice, sauces, 'mustard');
    expect(chosenIds(refused)).toEqual(['ketchup', 'mayo']);
    expect(refused.refused).toBe('sauces');
  });

  it('lets one out at the ceiling and another in', () => {
    const sauces = group('sauces', 0, 2, ['ketchup', 'mayo', 'mustard']);
    let choice = choose(choose(initialChoice([sauces]), sauces, 'ketchup'), sauces, 'mayo');
    choice = choose(choose(choice, sauces, 'ketchup'), sauces, 'mustard');
    expect(chosenIds(choice)).toEqual(['mayo', 'mustard']);
  });

  it('never fills a group without a ceiling', () => {
    const extras = group('extras', 0, 0, ['a', 'b', 'c', 'd']);
    let choice = initialChoice([extras]);
    for (const id of ['a', 'b', 'c', 'd']) choice = choose(choice, extras, id);
    expect(chosenIds(choice)).toEqual(['a', 'b', 'c', 'd']);
  });

  it('counts a repeated option up and down, and the line names it as many times, in the order chosen', () => {
    const extras = group('extras', 0, 3, ['cheese', 'bacon'], { allow_repeat: true });
    let choice = choose(initialChoice([extras]), extras, 'cheese');
    choice = choose(choice, extras, 'bacon');
    choice = choose(choice, extras, 'cheese');
    expect(countOf(choice, 'cheese')).toBe(2);
    expect(chosenIds(choice)).toEqual(['cheese', 'bacon', 'cheese']);
    choice = unchoose(choice, 'cheese');
    expect(chosenIds(choice)).toEqual(['cheese', 'bacon']);
  });
});

describe('«Add» waits', () => {
  it('while a required group is short, naming it; never closing on its own at the minimum', () => {
    const doneness = group('doneness', 1, 1, ['rare', 'done']);
    const extras = group('extras', 0, 0, ['cheese']);
    const choice = initialChoice([extras, doneness]);
    expect(missingGroup([extras, doneness], choice)?.id).toBe('doneness');
    expect(missingGroup([extras, doneness], choose(choice, doneness, 'rare'))).toBeNull();
  });
});

describe('the price the sheet shows (a preview: the server values the line)', () => {
  it('adds each choice with its sign, repeats counted', () => {
    const extras = group('extras', 0, 0, [], { allow_repeat: true, options: [option('cheese', 100), option('no-meat', -200)] });
    let choice = choose(initialChoice([extras]), extras, 'cheese');
    choice = choose(choice, extras, 'cheese');
    choice = choose(choice, extras, 'no-meat');
    expect(addedCents([extras], choice)).toBe(0);
  });
});
