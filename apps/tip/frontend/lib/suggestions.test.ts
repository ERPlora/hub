// The three suggestions of each payment method on the Settings screen (TIP-F01): each one a percentage («5») or an amount
// in the business's money («2,00»), what is wrong with one said under its own field, and what «Save» sends.
import { describe, expect, it } from 'vitest';

import type { MethodSuggestionsOut } from '../operations';
import { type MethodFields, suggestionErrors, toFields, toServer } from './suggestions';

const EURO = { currency: 'EUR', decimals: 2 };
const CARD: MethodSuggestionsOut = {
  method_id: 'm-card',
  method_name: 'Card',
  method_type: 'card',
  suggestions: [
    { percent: 3, amount: null },
    { percent: 5, amount: null },
    { percent: null, amount: 200 },
  ],
};

const fields = (...suggestions: [kind: 'percent' | 'amount', text: string][]): MethodFields => ({
  method_id: 'm-card',
  method_name: 'Card',
  suggestions: suggestions.map(([kind, text]) => ({ kind, text })),
});

describe('toFields', () => {
  it('writes a percentage as its number and an amount as the money field writes it, in the reader’s language', () => {
    expect(toFields([CARD], 'es', EURO)).toEqual([
      fields(['percent', '3'], ['percent', '5'], ['amount', '2,00']),
    ]);
    expect(toFields([CARD], 'en', EURO)[0].suggestions[2]).toEqual({ kind: 'amount', text: '2.00' });
  });
});

describe('toServer', () => {
  it('sends a percentage as a whole number and an amount in cents, method by method', () => {
    expect(toServer([fields(['percent', ' 4 '], ['amount', '1,50'], ['amount', '3'])], EURO)).toEqual([
      { method_id: 'm-card', suggestions: [{ percent: 4 }, { amount: 150 }, { amount: 300 }] },
    ]);
  });
});

describe('suggestionErrors', () => {
  it('nothing wrong: no errors', () => {
    expect(suggestionErrors([fields(['percent', '3'], ['percent', '100'], ['amount', '2,00'])], EURO)).toEqual({});
  });

  it.each(['', '0', '-5', '101', '2.5', 'diez'])('a percentage that is not a whole one from 1 to 100 (%j) is said under it', (text) => {
    expect(suggestionErrors([fields(['percent', '3'], ['percent', text], ['amount', '2'])], EURO)).toEqual({
      'm-card.1': 'tip.settings.errors.percent',
    });
  });

  it.each(['', '0', '-1', 'dos'])('an amount that is not above zero (%j) is said under it', (text) => {
    expect(suggestionErrors([fields(['amount', text], ['percent', '5'], ['percent', '10'])], EURO)).toEqual({
      'm-card.0': 'tip.settings.errors.amount',
    });
  });

  it('the same suggestion twice in one method: «That suggestion is already there» under the repeated one', () => {
    expect(suggestionErrors([fields(['percent', '5'], ['amount', '2'], ['percent', '05'])], EURO)).toEqual({
      'm-card.2': 'tip.settings.errors.same',
    });
    expect(suggestionErrors([fields(['amount', '2'], ['amount', '2,00'], ['percent', '2'])], EURO)).toEqual({
      'm-card.1': 'tip.settings.errors.same',
    });
  });

  it('two methods may suggest the same', () => {
    const other = { ...fields(['percent', '3'], ['percent', '5'], ['percent', '10']), method_id: 'm-cash' };
    expect(suggestionErrors([fields(['percent', '3'], ['percent', '5'], ['percent', '10']), other], EURO)).toEqual({});
  });
});
