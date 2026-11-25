// Which tip the charge has chosen (TIP-F02): «No tip», one of the payment method's suggestions or another amount. It
// opens on the suggestion the settings mark (none: «No tip»), and another payment method changes the suggestions but
// keeps an amount chosen; a percentage goes back to how the charge opens with that method.
import type { SuggestionOut } from '../operations';

export type Choice = { kind: 'none' } | { kind: 'suggestion'; index: number } | { kind: 'custom' };

/** What the charge chooses after another method: and, when an amount turns into another amount, that amount. */
export interface Rechosen {
  choice: Choice;
  custom?: number;
}

/** How the charge opens: the suggestion the settings mark, or «No tip». */
export function opening(read: SuggestionOut): Choice {
  const index = read.preselected - 1;
  return index >= 0 && index < read.suggestions.length ? { kind: 'suggestion', index } : { kind: 'none' };
}

/** `choice`, made on `before`'s suggestions, with the suggestions of another payment method. */
export function afterMethod(choice: Choice, before: SuggestionOut, after: SuggestionOut): Rechosen {
  if (choice.kind !== 'suggestion') return { choice };
  const chosen = before.suggestions[choice.index];
  if (!chosen || chosen.percent !== null) return { choice: opening(after) };
  const index = after.suggestions.findIndex((s) => s.percent === null && s.amount === chosen.amount);
  if (index >= 0) return { choice: { kind: 'suggestion', index } };
  return after.allow_custom ? { choice: { kind: 'custom' }, custom: chosen.amount } : { choice: opening(after) };
}
