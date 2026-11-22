// The rules of the menu sheet of the till (SALE-F12; Menus' COMBO-F07, «Contrato con Ventas»), kept pure. A
// course of a menu is a group of the options sheet (`modifierChoice`): a course of one swaps its dish, one with a
// ceiling refuses the tap past it naming the course, a dish that may be repeated has a counter. What differs:
// no dish is picked by default, the button names the course still short and how many it needs, and the line
// sends each dish once with how many times it was picked. The money shown is a preview: Menus prices the line on
// the server and the browser only sends the choices. A dish picked whose product has groups of Modifiers asks them
// right there (SALE-F42), with the options sheet's rules: each dish keeps its own choice of options, a dish picked twice
// carries the same ones each time, and a dish whose choice has not been touched yet opens with its defaults.
import type { SaleComboOut, SaleGroupOut } from '../../../combo/frontend/operations';
import type { ComboChoiceIn } from '../operations';
import { addedCents, type Choice, type ChoiceGroup, chosenIds, initialChoice, missingGroup } from './modifierChoice';

/** The dishes picked, each once with how many times, in the order each was first picked. */
export function comboChoices(choice: Choice): ComboChoiceIn[] {
  const counts = new Map<string, number>();
  for (const id of choice.picks) counts.set(id, (counts.get(id) ?? 0) + 1);
  return [...counts].map(([option_id, quantity]) => ({ option_id, quantity }));
}

/** The first course short of its minimum, with how many it still needs: «Choose {n} in {course}». */
export function comboShort(groups: readonly SaleGroupOut[], choice: Choice): { group: SaleGroupOut; n: number } | null {
  for (const group of groups) {
    const ids = new Set(group.options.map((option) => option.id));
    const count = choice.picks.filter((id) => ids.has(id)).length;
    if (count < group.min_choices) return { group, n: group.min_choices - count };
  }
  return null;
}

/** The menu's closed price plus the supplements picked, in cents (a preview). */
export function comboTotal(combo: Pick<SaleComboOut, 'price' | 'groups'>, choice: Choice): number {
  return combo.price + addedCents(combo.groups, choice);
}

/** A dish as the cart, the bill and the ticket name it: «2× Café» when it is more than one, with the options chosen
 *  for it in brackets («Entrecot (Poco hecho)»). */
export function dishLabel(dish: { product_name: string; quantity: number; modifiers?: readonly string[] }): string {
  const name = dish.quantity > 1 ? `${dish.quantity}× ${dish.product_name}` : dish.product_name;
  return dish.modifiers?.length ? `${name} (${dish.modifiers.join(', ')})` : name;
}

/** A dish picked in the sheet: its choice of the menu, its product, its name, its course and how many times. */
export interface PickedDish {
  readonly id: string;
  readonly product_id: string;
  readonly name: string;
  readonly course: string;
  readonly count: number;
}

/** A group of Modifiers of a dish, with the name the sheet says. */
export type NamedGroup = ChoiceGroup & { readonly name: string };
/** The groups of Modifiers of a product once read; `null` while they are not. */
export type GroupsOf = (productId: string) => readonly NamedGroup[] | null;
/** The choice of options of each dish touched, by its choice of the menu. */
export type DishChoices = Readonly<Record<string, Choice>>;
/** What the sheet knows of the dishes' options: the groups read and the choices touched. */
export interface DishOptions {
  readonly groupsOf: GroupsOf;
  readonly choices: DishChoices;
}

/** The dishes picked, course by course and in the course's order, each once with how many times. */
export function pickedDishes(groups: readonly SaleGroupOut[], choice: Choice): PickedDish[] {
  return groups.flatMap((group) =>
    group.options
      .map((option) => ({ option, count: choice.picks.filter((id) => id === option.id).length }))
      .filter(({ count }) => count > 0)
      .map(({ option, count }) => ({ id: option.id, product_id: option.product_id, name: option.product_name, course: group.id, count })),
  );
}

/** The options a dish has chosen: what was tapped, else its groups' defaults. */
export function dishChoice(dish: PickedDish, { groupsOf, choices }: DishOptions): Choice {
  return choices[dish.id] ?? initialChoice(groupsOf(dish.product_id) ?? []);
}

/** The first dish whose group of options is short of its minimum, with how many it still needs. */
export function dishShort(dishes: readonly PickedDish[], options: DishOptions): { dish: PickedDish; group: NamedGroup; n: number } | null {
  for (const dish of dishes) {
    const choice = dishChoice(dish, options);
    const groups = options.groupsOf(dish.product_id) ?? [];
    const group = groups.find((one) => one === missingGroup(groups, choice));
    if (!group) continue;
    const ids = new Set(group.options.map((option) => option.id));
    return { dish, group, n: Math.max(1, group.min_choices - choice.picks.filter((id) => ids.has(id)).length) };
  }
  return null;
}

/** What the dishes' options add to the menu, in cents: each dish's, once per pick of it (a preview). */
export function dishesCents(dishes: readonly PickedDish[], options: DishOptions): number {
  return dishes.reduce((sum, dish) => sum + dish.count * addedCents(options.groupsOf(dish.product_id) ?? [], dishChoice(dish, options)), 0);
}

/** The dishes as the line sends them, each with the ids of the options chosen for it when it has any. */
export function withDishOptions(sent: readonly ComboChoiceIn[], dishes: readonly PickedDish[], options: DishOptions): ComboChoiceIn[] {
  return sent.map((choice) => {
    const dish = dishes.find((one) => one.id === choice.option_id);
    const ids = dish ? chosenIds(dishChoice(dish, options)) : [];
    return ids.length ? { ...choice, option_ids: ids } : choice;
  });
}
