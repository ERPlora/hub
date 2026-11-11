// Every number field of a settings form of the Hub is painted the same way (hub#982): `SettingsNumberField` of
// `@erplora/ui/components`, from what `useSettingsForm` gives, one line per field (or per `v-for` of fields). Nine
// pages had copied the outlined number `ion-input` with its error text, its red mark and its `set(field, text(…))`,
// twice in Reservations, so a fix to it had to be repeated page by page. This guard reads every `.vue` under
// `apps/*/frontend` whose script builds its form with `useSettingsForm` (tests and their helpers left out), and
// there may be none that writes an `ion-input` of `type="number"` by hand.
import { describe, expect, it } from 'vitest';

import { settingsForms } from './__tests__/settings-form';

/** Each `<ion-input …>` tag of `source` (or `<IonInput …>`, as its import is named), up to the `>` that closes it:
 *  a `<` or a `>` inside a quoted attribute is the attribute's. */
function ionInputs(source: string): string[] {
  return [...source.matchAll(/<(?:ion-input|IonInput)\b(?:"[^"]*"|'[^']*'|[^>"'])*>/g)].map(([tag]) => tag);
}

describe('settings forms paint their number fields with SettingsNumberField (hub#982)', () => {
  const forms = settingsForms();

  it('finds the settings forms it guards, and the number fields they paint with the piece', () => {
    expect(forms.length).toBeGreaterThan(0);
    expect(forms.filter(({ source }) => /<SettingsNumberField\b/.test(source)).length).toBeGreaterThan(0);
  });

  it('reads a hand-written number field as one (the guard catches what it guards)', () => {
    const byHand = '<ion-input\n  v-for="field in NUMBERS"\n  type="number"\n  @ion-input="set(field, text($event.detail.value))"\n/>\n<ion-toggle />';
    expect(ionInputs(byHand).filter((tag) => /\btype="number"/.test(tag))).toHaveLength(1);
    expect(ionInputs('<ion-input type="text" />\n<SettingsNumberField field="a" />')).toHaveLength(1);
    // Written as the import is named (`<IonInput`: the Hub has both spellings and no lint rule picks one), and with
    // a `<` or a `>` inside an attribute before its `type`.
    const numberFields = (source: string) => ionInputs(source).filter((tag) => /\btype="number"/.test(tag));
    expect(numberFields('<IonInput type="number" fill="outline" />\n<ion-toggle />')).toHaveLength(1);
    expect(numberFields('<ion-input :disabled="a < b" type="number" />')).toHaveLength(1);
    expect(numberFields('<ion-input @ion-input="(e) => set(e)" type="number" />')).toHaveLength(1);
    // The next tag's `type` is not this one's.
    expect(numberFields('<ion-input type="text" />\n<ion-input type="number" />')).toHaveLength(1);
    expect(numberFields('<ion-input type="text" />\n<input type="number" />')).toHaveLength(0);
  });

  it('no form built on useSettingsForm writes a number ion-input by hand', () => {
    const byHand = forms
      .filter(({ source }) => ionInputs(source).some((tag) => /\btype="number"/.test(tag)))
      .map(({ file }) => file);
    expect(byHand, 'paint it with <SettingsNumberField :settings="…" field="…" testid="…" :label="…" /> of @erplora/ui/components').toEqual([]);
  });
});
