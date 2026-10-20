// The rules of the menu sheet of the till (SALE-F12; Menus' COMBO-F07, «Contrato con Ventas»), kept pure. A
// course of a menu is a group of the options sheet (`modifierChoice`): a course of one swaps its dish, one with a
// ceiling refuses the tap past it naming the course, a dish that may be repeated has a counter. What differs:
// no dish is picked by default, the button names the course still short and how many it needs, and the line
// sends each dish once with how many times it was picked. The money shown is a preview: Menus prices the line on
// the server and the browser only sends the choices.
import type { SaleComboOut, SaleGroupOut } from '../../../combo/frontend/operations';
import type { ComboChoiceIn } from '../operations';
import { addedCents, type Choice } from './modifierChoice';

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

/** A dish as the cart, the bill and the ticket name it: «2× Café» when it is more than one. */
export function dishLabel(dish: { product_name: string; quantity: number }): string {
  return dish.quantity > 1 ? `${dish.quantity}× ${dish.product_name}` : dish.product_name;
}
