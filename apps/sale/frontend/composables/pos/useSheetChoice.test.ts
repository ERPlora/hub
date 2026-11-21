// flow: SALE-F11, SALE-F12 — what a tap does in a choosing sheet of the till (the options sheet of a product, the menu
// sheet): the choice follows the rules of `modifierChoice`, a tap a full group refuses points at it, and a minus or a
// fresh start forgets where it pointed.
import { describe, expect, it } from 'vitest';

import type { ChoiceGroup } from '../../lib/modifierChoice';
import { useSheetChoice } from './useSheetChoice';

const extras: ChoiceGroup = { id: 'extras', min_choices: 0, max_choices: 1, allow_repeat: false, options: [{ id: 'cheese', price_delta: 100, is_default: true }, { id: 'bacon', price_delta: 150 }] };
const sides: ChoiceGroup = { id: 'sides', min_choices: 0, max_choices: 2, allow_repeat: true, options: [{ id: 'fries', price_delta: 0 }] };

describe('useSheetChoice', () => {
  it('starts with the defaults of the groups given and nothing pointed at', () => {
    const sheet = useSheetChoice();
    sheet.start([extras]);
    expect(sheet.choice.value.picks).toEqual(['cheese']);
    expect(sheet.attention.value).toBeNull();
  });

  it('a tap follows the group’s rule, and a tap a full group refuses points at it', () => {
    const sheet = useSheetChoice();
    sheet.start([sides]);
    sheet.tap(sides, 'fries');
    sheet.tap(sides, 'fries');
    sheet.tap(sides, 'fries');
    expect(sheet.choice.value.picks).toEqual(['fries', 'fries']);
    expect(sheet.attention.value).toBe('sides');
  });

  it('a minus takes one out and forgets where it pointed; starting again clears everything', () => {
    const sheet = useSheetChoice();
    sheet.start([sides]);
    sheet.tap(sides, 'fries');
    sheet.attention.value = 'sides';
    sheet.less('fries');
    expect(sheet.choice.value.picks).toEqual([]);
    expect(sheet.attention.value).toBeNull();
    sheet.tap(sides, 'fries');
    sheet.start([]);
    expect(sheet.choice.value.picks).toEqual([]);
  });
});
