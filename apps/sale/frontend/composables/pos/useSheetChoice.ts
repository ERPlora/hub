// What a tap does in a choosing sheet of the till (the options sheet of a product, SALE-F11; the menu sheet, SALE-F12):
// the sheet's choice, under the rules of `modifierChoice`, and the group it points at — the one whose ceiling refused
// the last tap, or the one the button asks for.
import { shallowRef } from 'vue';

import { type Choice, type ChoiceGroup, choose, initialChoice, unchoose } from '../../lib/modifierChoice';

export function useSheetChoice() {
  const choice = shallowRef<Choice>(initialChoice([]));
  const attention = shallowRef<string | null>(null);

  /** The sheet as it opens: the defaults of `groups` chosen, nothing pointed at. */
  function start(groups: readonly ChoiceGroup[]): void {
    choice.value = initialChoice(groups);
    attention.value = null;
  }

  function tap(group: ChoiceGroup, optionId: string): void {
    choice.value = choose(choice.value, group, optionId);
    attention.value = choice.value.refused;
  }

  function less(optionId: string): void {
    choice.value = unchoose(choice.value, optionId);
    attention.value = null;
  }

  return { choice, attention, start, tap, less };
}
