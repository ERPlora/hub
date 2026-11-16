// Test helper of a window whose fields the server refuses with the same words (hub#888): FormModal (@erplora/ui) takes
// the mark away from the refused field a person corrects, and it tells that field by its `name`; without one it falls
// back to the words the field shows, and two fields saying «Check this field.» are not told apart, so correcting one
// leaves them all marked. The window's test answers «Save» with `refusedWithTheSameWords(keys)`; the helper presses it,
// checks every field says those same words (else it would prove nothing), corrects one as a person does — a keystroke
// in a text field (the native `input` bubbling out of it, then Ionic's `ionInput`), a choice in a picker (`ionChange`) —
// and says only that field lost its words. A field without its name, or named after another key, fails it. A window's
// test declares its cases with `itTellsTheCorrectedFieldApart`: one per field, and one in Spanish. For the tests of
// every app with such a window, like `save-waits-for-money.ts`: free of side effects.
import { expect, it } from 'vitest';

/** The words the server refuses every field with, in a test that does not give its own. */
export const SAME_WORDS = 'Check this field.';
/** The same, in Spanish. */
export const SAME_WORDS_ES = 'Revisa este campo.';

/** The server's refusal of `keys`, every one with the same `words`, as a window's test answers «Save» with it. */
export function refusedWithTheSameWords(keys: readonly string[], words = SAME_WORDS) {
  return {
    error: {
      code: 'invalid_payload',
      message: 'Check the highlighted details.',
      fields: Object.fromEntries(keys.map((key) => [key, words])) as Record<string, string>,
    },
  };
}

export interface RefusedWindow {
  /** The field the server refuses under `key`. */
  field: (key: string) => Element | null;
  /** Presses «Save»: the server answers with `refusedWithTheSameWords(keys)`. */
  send: () => Promise<void>;
  /** Lets the window's promises run (the app's own `settle`). */
  settle: () => Promise<void>;
}

/** The fields a person changes by choosing, not by typing: they speak by `ionChange` only. */
const CHOSEN = 'ion-select, ion-toggle, ion-checkbox, ion-radio-group, ion-range';

/** The words under a field: Ionic Vue sets `error-text` as the element's property. */
function wordsOf(field: Element | null): string {
  const shown = (field as (Element & { errorText?: unknown }) | null)?.errorText;
  return typeof shown === 'string' ? shown : '';
}

/** The keys whose field still says words under it. */
const saying = (window: RefusedWindow, keys: readonly string[]): string[] => keys.filter((key) => wordsOf(window.field(key)) !== '');

/** A person corrects the field of `key`: types in it, or chooses in it. */
async function correct(window: RefusedWindow, key: string): Promise<void> {
  const field = window.field(key);
  if (!field) throw new Error(`the window has no field for "${key}"`);
  const value = (field as Element & { value?: unknown }).value;
  if (field.matches(CHOSEN)) {
    field.dispatchEvent(new CustomEvent('ionChange', { detail: { value }, bubbles: true }));
  } else {
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value: `${typeof value === 'string' ? value : ''}1` }, bubbles: true }));
  }
  await window.settle();
}

export async function expectTheCorrectedFieldAloneLosesItsMark(window: RefusedWindow, keys: readonly string[], corrected: string): Promise<void> {
  await window.send();
  const words = keys.map((key) => wordsOf(window.field(key)));
  expect(
    words.every((said) => said !== '' && said === words[0]),
    `every field refused with the same words: ${JSON.stringify(Object.fromEntries(keys.map((key, i) => [key, words[i]])))}`,
  ).toBe(true);
  await correct(window, corrected);
  expect(saying(window, keys), `the fields still saying the refusal once "${corrected}" is corrected`).toEqual(keys.filter((key) => key !== corrected));
}

/** The window of a test, opened in `locale`, whose «Save» the server answers with `refusal` (`refusedWithTheSameWords`). */
export type OpenRefused = (locale: 'en' | 'es', refusal: ReturnType<typeof refusedWithTheSameWords>) => Promise<RefusedWindow>;

/** A window's cases: each field of `keys`, refused with the same words as the others and then corrected, alone loses
 *  them; and `spanish` (the first key unless said) does the same in a window in Spanish, refused in Spanish. `test`
 *  declares them (`it`; this helper's own test passes `it.fails` with a window that gets it wrong). */
export function itTellsTheCorrectedFieldApart(keys: readonly string[], open: OpenRefused, spanish = keys[0], test: typeof it = it): void {
  test.each(keys)('%s, corrected, alone loses the words every field was refused with', async (key) => {
    await expectTheCorrectedFieldAloneLosesItsMark(await open('en', refusedWithTheSameWords(keys)), keys, key);
  });
  test(`in Spanish too: the corrected ${spanish} alone loses «${SAME_WORDS_ES}»`, async () => {
    await expectTheSameInSpanish(open, keys, spanish);
  });
}

/** A window's «Cancel»: FormModal's own, or the one of a footer the window paints itself (with «Delete» beside Cancel
 *  and Save), told by its testid `<window>-cancel`. */
const CANCEL = '.ep-form-modal__cancel, .ep-form-modal__footer [data-testid$="-cancel"]';

/** The window, opened in Spanish and refused in Spanish, speaks Spanish (its «Cancel» says «Cancelar»), and the
 *  field of `corrected` alone loses the words. */
export async function expectTheSameInSpanish(open: OpenRefused, keys: readonly string[], corrected: string): Promise<void> {
  const window = await open('es', refusedWithTheSameWords(keys, SAME_WORDS_ES));
  const cancel = window.field(corrected)?.closest('.ep-form-modal')?.querySelector(CANCEL);
  expect(cancel?.textContent?.trim(), 'the window’s «Cancel», in Spanish').toBe('Cancelar');
  await expectTheCorrectedFieldAloneLosesItsMark(window, keys, corrected);
}
