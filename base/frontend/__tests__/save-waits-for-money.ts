// Test helper of a window whose «Save» waits for the business's money (hub#918): its amounts are read in the business's
// currency (`useBusinessMoney`, `base.business.get`), never before it answers, or «1500» yen would be read with two
// decimals and saved as 150000. While the business has not answered, it presses «Save» both ways a save can come — the
// button (FormModal holds a submit while it is grey) and a `submit` that gets past it (the window's own guard must hold
// that one) — and then says the window waited: nothing sent, «Save» grey and the amount field silent. Then the business
// answers (`answer`) and «Save» lights up. For the tests of every app with such a window (Product, Service, Menu,
// Option), like `business.ts`: free of side effects.
import { FormModal } from '@erplora/ui/components';
import type { VueWrapper } from '@vue/test-utils';
import { expect } from 'vitest';

type Control = HTMLElement & { disabled?: boolean; errorText?: string };

export interface WaitingWindow {
  /** The mounted window: its FormModal is found inside. */
  wrapper: VueWrapper;
  /** Its «Save». */
  save: () => Control | null;
  /** The amount field, which says nothing while the window waits. */
  amount: () => Control | null;
  /** What the window has sent so far. */
  sent: () => unknown[];
  /** Lets the window's promises run (the app's own `settle`). */
  settle: () => Promise<void>;
}

export async function expectSaveWaitsForMoney(window: WaitingWindow, answer: () => Promise<unknown>): Promise<void> {
  window.save()?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
  await window.settle();
  window.wrapper.findComponent(FormModal).vm.$emit('submit');
  await window.settle();
  expect(window.sent(), 'sent before the business answered its money').toEqual([]);
  expect([window.save()?.disabled, window.amount()?.errorText], '[«Save» grey, the amount field’s message]').toEqual([true, undefined]);
  await answer();
  await window.settle();
  expect(window.save()?.disabled, '«Save» grey once the business answered').toBe(false);
}
