// The unsaved-changes contract of a form window (BASE-F05), exercised through its own controls. With the IonModal stub of
// @erplora/ui (`vi.mock('@ionic/vue', …)` in the window's test), as every window test does.
//   - `expectUnsavedFormAsksBeforeClosing` — the whole contract of a FormModal window: Android's Back holds it while
//     something is typed (hub#1015, hub#1020) and so do its own ways out (hub#1156): «Cancel», the «×», Escape and a tap
//     outside ask «Discard changes?», and «Keep editing» leaves it open with what was typed.
//   - `expectUnsavedFormOnAndroidBack` — only the Back, for the windows whose own ways out do not ask yet: those that
//     are not a FormModal (hub#1233) and those of Caja (hub#1234).
//   - `answerUnsavedQuestion` — answers the question on screen, for a test that follows one way out to its end.
import { expect, type Mock } from 'vitest';

import { ionModalStubOf } from '../../../packages/ui/src/components/FormModal/__tests__/ionModalStub';
import { flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';
import { unsavedChangesIn } from '../lib/system-back';
import en from '../locale/en.json';
import es from '../locale/es.json';

interface UnsavedFormWindow {
  /** An element of the window: its overlay, its FormModal or one of its fields. */
  overlay: () => Element | null;
  /** Types something in it, through its own fields. */
  change: () => Promise<void> | void;
  /** Leaves its fields as they opened. */
  restore: () => Promise<void> | void;
  /** The `confirm` of a test that mocks `useConfirm`: there the question is a call to it, answered «Keep editing». */
  confirm?: Mock;
}

/** The question, in either language of the test — or by its key, in a window test that mounts only its own app's
 *  catalogue (the shell loads base's too, `frontend/main.ts`). */
const QUESTION_TITLES = [en.base.unsavedChanges.title, es.base.unsavedChanges.title, 'base.unsavedChanges.title'];

const presented = (modal: Element): boolean => modal.querySelector(':scope > .ion-delegate-host') !== null;

/** «Discard changes?» on screen, or null. */
function question(): HTMLElement | null {
  const modals = [...document.querySelectorAll<HTMLElement>('[data-stub="ion-modal"]')];
  return modals.find((m) => QUESTION_TITLES.includes(m.getAttribute('aria-label') ?? '') && presented(m)) ?? null;
}

/** Answers «Discard changes?» on screen: «Keep editing» or «Discard changes». */
export async function answerUnsavedQuestion(answer: 'keep' | 'discard'): Promise<void> {
  const asked = question();
  expect(asked, '«Discard changes?» is on screen').not.toBeNull();
  own(asked!, answer === 'keep' ? '.ep-form-modal__cancel' : '.ep-form-modal__submit')!.click();
  await flush();
}

/** The window's own control (not one of a dialog nested in it). */
function own(modal: HTMLElement, selector: string): HTMLElement | null {
  return [...modal.querySelectorAll<HTMLElement>(selector)].find((el) => el.closest('[data-stub="ion-modal"]') === modal) ?? null;
}

/** Escape pressed in the window: FormModal hears it on its content, Ionic (the stub) on the document — which a window
 *  mounted outside the document does not reach on its own. */
function escape(content: HTMLElement): void {
  const press = () => new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
  content.dispatchEvent(press());
  if (!document.contains(content)) document.dispatchEvent(press());
}

/** The ways out of a FormModal window: its «Cancel» (FormModal's, or the `<testid>-cancel` of a footer of its own,
 *  when it has one), its «×», Escape, and a tap outside when a tap closes it. */
function waysOut(modal: HTMLElement): [string, () => void][] {
  const testid = modal.dataset.testid;
  const cancel = own(modal, '.ep-form-modal__cancel') ?? (testid ? own(modal, `[data-testid="${testid}-cancel"]`) : null);
  const close = own(modal, '.ep-form-modal__close');
  const content = own(modal, '.ep-form-modal__content');
  expect(close, 'the window is a FormModal with its «×»').not.toBeNull();
  const ways: [string, () => void][] = [];
  if (cancel) ways.push(['«Cancel»', () => cancel.click()]);
  ways.push(['the «×»', () => close!.click()]);
  ways.push(['Escape', () => escape(content!)]);
  // Not awaited: with the question up, the tap settles only once it is answered.
  if (modal.dataset.backdropDismiss === 'true') ways.push(['a tap outside', () => void ionModalStubOf(modal).tapBackdrop()]);
  return ways;
}

async function expectBackHolds(window: UnsavedFormWindow, between: (overlay: Element) => Promise<void>): Promise<void> {
  const overlay = window.overlay();
  expect(overlay).not.toBeNull();
  expect(unsavedChangesIn(overlay!)).toBeUndefined();
  await window.change();
  expect(unsavedChangesIn(overlay!)).toBeDefined();
  await between(overlay!);
  await window.restore();
  expect(unsavedChangesIn(overlay!)).toBeUndefined();
}

/** Only Android's Back: as opened nothing holds it, a change does, and restored as opened it lets go. */
export async function expectUnsavedFormOnAndroidBack(window: UnsavedFormWindow): Promise<void> {
  await expectBackHolds(window, async () => {});
}

/** Back, and every way out of the window's FormModal, ask «Discard changes?» while something is typed; «Keep editing»
 *  leaves the window open and still holding what was typed. */
export async function expectUnsavedFormAsksBeforeClosing(window: UnsavedFormWindow): Promise<void> {
  await expectBackHolds(window, async (overlay) => {
    const modal = overlay.closest<HTMLElement>('[data-stub="ion-modal"]');
    expect(modal, 'the window is an IonModal').not.toBeNull();
    for (const [way, leave] of waysOut(modal!)) {
      if (window.confirm) {
        const before = window.confirm.mock.calls.length;
        window.confirm.mockResolvedValueOnce(false);
        leave();
        await flush();
        expect(window.confirm.mock.calls.length, `${way} with something typed asks «Discard changes?»`).toBe(before + 1);
        expect(QUESTION_TITLES).toContain((window.confirm.mock.calls.at(-1)![0] as { title: string }).title);
      } else {
        leave();
        await flush();
        expect(question(), `${way} with something typed asks «Discard changes?»`).not.toBeNull();
        await answerUnsavedQuestion('keep');
        expect(question(), `«Keep editing» after ${way} closes the question`).toBeNull();
      }
      expect(presented(modal!), `«Keep editing» after ${way} keeps the window open`).toBe(true);
      expect(unsavedChangesIn(overlay), `«Keep editing» after ${way} keeps what was typed`).toBeDefined();
    }
  });
}
