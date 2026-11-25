import { describe, expect, it } from 'vitest';

import type { SuggestionOut } from '../operations';
import { afterMethod, opening } from './choice';

const read = (over: Partial<SuggestionOut> = {}): SuggestionOut => ({
  enabled: true,
  allow_custom: true,
  preselected: 0,
  suggestions: [
    { percent: 3, amount: 30 },
    { percent: null, amount: 200 },
    { percent: 10, amount: 100 },
  ],
  ...over,
});

describe('opening', () => {
  it('opens on «No tip» from the factory and on the suggestion the settings mark', () => {
    expect(opening(read())).toEqual({ kind: 'none' });
    expect(opening(read({ preselected: 2 }))).toEqual({ kind: 'suggestion', index: 1 });
  });

  it('opens on «No tip» when the method has no such suggestion', () => {
    expect(opening(read({ preselected: 3, suggestions: [] }))).toEqual({ kind: 'none' });
  });
});

describe('afterMethod', () => {
  const card = read({ preselected: 1, suggestions: [{ percent: 5, amount: 50 }, { percent: null, amount: 200 }, { percent: null, amount: 500 }] });

  it('keeps an amount chosen on its own suggestion of the new method', () => {
    expect(afterMethod({ kind: 'suggestion', index: 1 }, read(), card)).toEqual({ choice: { kind: 'suggestion', index: 1 } });
  });

  it('keeps an amount the new method does not suggest as another amount, when another amount is allowed', () => {
    const cash = read({ suggestions: [{ percent: null, amount: 100 }, { percent: null, amount: 300 }, { percent: 5, amount: 50 }] });
    expect(afterMethod({ kind: 'suggestion', index: 1 }, read(), cash)).toEqual({ choice: { kind: 'custom' }, custom: 200 });
    expect(afterMethod({ kind: 'suggestion', index: 1 }, read(), { ...cash, allow_custom: false })).toEqual({ choice: { kind: 'none' } });
  });

  it('takes a percentage back to how the charge opens with the new method', () => {
    expect(afterMethod({ kind: 'suggestion', index: 0 }, read(), card)).toEqual({ choice: { kind: 'suggestion', index: 0 } });
    expect(afterMethod({ kind: 'suggestion', index: 2 }, read(), { ...card, preselected: 0 })).toEqual({ choice: { kind: 'none' } });
  });

  it('keeps «No tip» and another amount as they are', () => {
    expect(afterMethod({ kind: 'none' }, read(), card)).toEqual({ choice: { kind: 'none' } });
    expect(afterMethod({ kind: 'custom' }, read(), card)).toEqual({ choice: { kind: 'custom' } });
  });
});
