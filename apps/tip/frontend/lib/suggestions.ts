// The three suggestions of each payment method as the Settings screen edits them (TIP-F01): a percentage of the check's
// total before discounts, written as a whole number, or an amount, written as the money field writes it. What is wrong
// with one is said under that field, by a key of the app's catalogue; the server refuses the same anyway.
import { moneyFieldText, parseMoney } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';
import type { MethodSuggestionsOut, Suggestion } from '../operations';

export type SuggestionKind = 'percent' | 'amount';

export interface SuggestionField {
  kind: SuggestionKind;
  text: string;
}

export interface MethodFields {
  method_id: string;
  method_name: string;
  suggestions: SuggestionField[];
}

const WHOLE = /^\d+$/;

export function toFields(methods: readonly MethodSuggestionsOut[], locale: string, money: Money | undefined): MethodFields[] {
  return methods.map((method) => ({
    method_id: method.method_id,
    method_name: method.method_name,
    suggestions: method.suggestions.map((suggestion) =>
      suggestion.percent !== null && suggestion.percent !== undefined
        ? { kind: 'percent', text: String(suggestion.percent) }
        : { kind: 'amount', text: moneyFieldText(suggestion.amount, locale, money) },
    ),
  }));
}

/** The suggestion `field` is, or `null` when it is no percentage from 1 to 100 and no amount above zero. */
function read(field: SuggestionField, money: Money | undefined): Suggestion | null {
  const text = field.text.trim();
  if (field.kind === 'percent') {
    const percent = WHOLE.test(text) ? Number(text) : 0;
    return percent >= 1 && percent <= 100 ? { percent } : null;
  }
  const amount = parseMoney(text, { money });
  return amount.ok && amount.cents !== null && amount.cents > 0 ? { amount: amount.cents } : null;
}

/** What «Save» sends; only called once `suggestionErrors` finds nothing wrong. */
export function toServer(methods: readonly MethodFields[], money: Money | undefined) {
  return methods.map((method) => ({
    method_id: method.method_id,
    suggestions: method.suggestions.map((field) => read(field, money) as Suggestion),
  }));
}

/** What is wrong, by `<method_id>.<position>`: a key of the catalogue. */
export function suggestionErrors(methods: readonly MethodFields[], money: Money | undefined): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const method of methods) {
    const seen = new Set<string>();
    method.suggestions.forEach((field, index) => {
      const suggestion = read(field, money);
      const key = `${method.method_id}.${index}`;
      if (!suggestion) {
        errors[key] = field.kind === 'percent' ? 'tip.settings.errors.percent' : 'tip.settings.errors.amount';
        return;
      }
      const same = JSON.stringify(suggestion);
      if (seen.has(same)) errors[key] = 'tip.settings.errors.same';
      seen.add(same);
    });
  }
  return errors;
}
