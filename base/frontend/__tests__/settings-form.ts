// What the tests of every settings page check the same way (hub#867, hub#897): the page builds its form on
// `useSettingsForm` and ends it with `SettingsFormFooter` (@erplora/ui/components), so where the save's notices sit,
// what Enter in a field does and what a refused field shows are read alike in every app.
import { flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';

/** Whether `middle` comes after `first` and before `last` on the page. */
export function between(first: Element, middle: Element, last: Element): boolean {
  return (
    !!(first.compareDocumentPosition(middle) & Node.DOCUMENT_POSITION_FOLLOWING) &&
    !!(middle.compareDocumentPosition(last) & Node.DOCUMENT_POSITION_FOLLOWING)
  );
}

/** Enter in a field of the settings form `form`: Ionic puts a hidden submit button in it, so the form is submitted;
 *  then the save lands. */
export async function pressEnter(form: Element | null | undefined): Promise<void> {
  if (!form) throw new Error('no settings form to submit');
  form.dispatchEvent(new Event('submit', { cancelable: true }));
  await flush();
  await flush();
}

/** What a refusal shows: whether the red notice above «Save» is on screen (`notice`, the page's own probe), and each
 *  refused field's message under it (`says`) and its red mark (`marked`). */
export function refusalMarks(field: (name: string) => Element & { errorText?: string }, notice: () => boolean) {
  return {
    notice,
    says: (name: string): string => field(name).errorText ?? '',
    marked: (name: string): boolean => field(name).classList.contains('ion-invalid'),
  };
}
