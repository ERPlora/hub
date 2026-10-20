// flow: SALE-F12 — the rules of the menu sheet (COMBO-F07): what the line sends, what the button says while a
// course is short and the total it previews.
import { describe, expect, it } from 'vitest';

import type { SaleComboOut, SaleGroupOut } from '../../../combo/frontend/operations';
import { comboChoices, comboShort, comboTotal, dishLabel } from './comboChoice';
import { choose, initialChoice } from './modifierChoice';

const course = (id: string, min: number, max: number, ids: string[], more: Partial<SaleGroupOut> = {}): SaleGroupOut => ({
  id,
  name: id,
  min_choices: min,
  max_choices: max,
  allow_repeat: false,
  options: ids.map((optionId) => ({ id: optionId, product_id: `p-${optionId}`, product_name: optionId, sku: '', price_delta: optionId === 'steak' ? 200 : 0 })),
  ...more,
});

const menu = (groups: SaleGroupOut[]): SaleComboOut => ({
  id: 'm1',
  name: 'Menu of the day',
  kitchen_name: 'MENU',
  price: 1350,
  supply_kind: 'service',
  sort_order: 0,
  groups,
});

const starters = course('Starters', 1, 1, ['lentils', 'salad']);
const mains = course('Mains', 1, 1, ['hake', 'steak']);
const coffees = course('Coffee', 0, 3, ['espresso', 'latte'], { allow_repeat: true });

describe('the menu sheet', () => {
  it('opens with nothing picked: a menu has no default dish', () => {
    expect(initialChoice(menu([starters, mains]).groups).picks).toEqual([]);
  });

  it('names the first course short of its minimum and how many it still needs', () => {
    const groups = [starters, course('Sides', 2, 2, ['fries', 'rice', 'peas'])];
    let choice = initialChoice(groups);
    expect(comboShort(groups, choice)).toEqual({ group: starters, n: 1 });
    choice = choose(choice, starters, 'salad');
    choice = choose(choice, groups[1], 'rice');
    expect(comboShort(groups, choice)).toEqual({ group: groups[1], n: 1 });
    choice = choose(choice, groups[1], 'peas');
    expect(comboShort(groups, choice)).toBeNull();
  });

  it('a course of one swaps its dish, never adds a second one', () => {
    let choice = choose(initialChoice([starters]), starters, 'lentils');
    choice = choose(choice, starters, 'salad');
    expect(comboChoices(choice)).toEqual([{ option_id: 'salad', quantity: 1 }]);
  });

  it('sends each dish once with how many times it was picked, in the order first picked', () => {
    let choice = initialChoice([starters, coffees]);
    choice = choose(choice, coffees, 'latte');
    choice = choose(choice, starters, 'lentils');
    choice = choose(choice, coffees, 'espresso');
    choice = choose(choice, coffees, 'latte');
    expect(comboChoices(choice)).toEqual([
      { option_id: 'latte', quantity: 2 },
      { option_id: 'lentils', quantity: 1 },
      { option_id: 'espresso', quantity: 1 },
    ]);
  });

  it('previews the closed price plus the supplements picked', () => {
    const offer = menu([starters, mains]);
    let choice = choose(initialChoice(offer.groups), starters, 'lentils');
    expect(comboTotal(offer, choice)).toBe(1350);
    choice = choose(choice, mains, 'steak');
    expect(comboTotal(offer, choice)).toBe(1550);
  });

  it('labels a dish with how many when it is more than one', () => {
    expect(dishLabel({ product_name: 'Café', quantity: 1 })).toBe('Café');
    expect(dishLabel({ product_name: 'Café', quantity: 2 })).toBe('2× Café');
  });
});
