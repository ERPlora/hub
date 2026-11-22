// flow: SALE-F12, SALE-F42 — the rules of the menu sheet (COMBO-F07): what the line sends, what the button says while a
// course or a dish's group of options is short and the total it previews.
import { describe, expect, it } from 'vitest';

import type { SaleComboOut, SaleGroupOut } from '../../../combo/frontend/operations';
import { comboChoices, comboShort, comboTotal, dishesCents, dishLabel, dishShort, pickedDishes, withDishOptions } from './comboChoice';
import { type ChoiceGroup, choose, initialChoice } from './modifierChoice';

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

  it('labels a dish with the options chosen for it, in brackets', () => {
    expect(dishLabel({ product_name: 'Entrecot', quantity: 1, modifiers: ['Poco hecho', 'Queso'] })).toBe('Entrecot (Poco hecho, Queso)');
    expect(dishLabel({ product_name: 'Café', quantity: 2, modifiers: [] })).toBe('2× Café');
  });
});

describe('the options of a dish picked in a menu (SALE-F42)', () => {
  const doneness: ChoiceGroup & { name: string } = {
    id: 'doneness',
    name: 'Punto de la carne',
    min_choices: 1,
    max_choices: 1,
    allow_repeat: false,
    options: [
      { id: 'rare', price_delta: 0 },
      { id: 'done', price_delta: 0 },
    ],
  };
  const extras: ChoiceGroup & { name: string } = {
    id: 'extras',
    name: 'Extras',
    min_choices: 0,
    max_choices: 2,
    allow_repeat: false,
    options: [{ id: 'cheese', price_delta: 100, is_default: true }],
  };
  const groupsOf = (productId: string) => (productId === 'p-steak' ? [doneness, extras] : productId === 'p-latte' ? [extras] : []);

  it('lists the dishes picked, course by course, each once with how many times', () => {
    let choice = choose(initialChoice([mains, coffees]), coffees, 'latte');
    choice = choose(choose(choice, mains, 'steak'), coffees, 'latte');
    expect(pickedDishes([mains, coffees], choice)).toEqual([
      { id: 'steak', product_id: 'p-steak', name: 'steak', course: 'Mains', count: 1 },
      { id: 'latte', product_id: 'p-latte', name: 'latte', course: 'Coffee', count: 2 },
    ]);
  });

  it('names the first dish whose group is short and how many it needs; a dish not chosen yet opens with its defaults', () => {
    const dishes = pickedDishes([mains], choose(initialChoice([mains]), mains, 'steak'));
    expect(dishShort(dishes, { groupsOf, choices: {} })).toEqual({ dish: dishes[0], group: doneness, n: 1 });
    const rare = choose(initialChoice([doneness, extras]), doneness, 'rare');
    expect(dishShort(dishes, { groupsOf, choices: { steak: rare } })).toBeNull();
  });

  it('a dish whose groups are not read yet waits for nothing', () => {
    const dishes = pickedDishes([mains], choose(initialChoice([mains]), mains, 'steak'));
    expect(dishShort(dishes, { groupsOf: () => null, choices: {} })).toBeNull();
  });

  it('adds what each dish’s options cost, once per pick of the dish', () => {
    let choice = choose(choose(initialChoice([mains, coffees]), mains, 'steak'), coffees, 'latte');
    choice = choose(choice, coffees, 'latte');
    const dishes = pickedDishes([mains, coffees], choice);
    // The steak's cheese (a default, 1,00 €) once and the cheese of each of the two lattes.
    expect(dishesCents(dishes, { groupsOf, choices: {} })).toBe(300);
    expect(dishesCents(dishes, { groupsOf, choices: { steak: initialChoice([]), latte: initialChoice([]) } })).toBe(0);
  });

  it('hands each dish up with the options chosen for it, and a dish without any as before', () => {
    const choice = choose(choose(initialChoice([starters, mains]), starters, 'lentils'), mains, 'steak');
    const steak = choose(initialChoice([doneness, extras]), doneness, 'rare');
    const dishes = pickedDishes([starters, mains], choice);
    expect(withDishOptions(comboChoices(choice), dishes, { groupsOf, choices: { steak } })).toEqual([
      { option_id: 'lentils', quantity: 1 },
      { option_id: 'steak', quantity: 1, option_ids: ['cheese', 'rare'] },
    ]);
  });
});
