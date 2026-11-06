// Test helper of a window whose «Save» waits for the business's money (hub#918): its amounts are read in the business's
// currency (`useBusinessMoney`, `base.business.get`), never before it answers, or «1500» yen would be read with two
// decimals and saved as 150000. While the business has not answered, it presses «Save» both ways a save can come — the
// button (FormModal holds a submit while it is grey) and a `submit` that gets past it (the window's own guard must hold
// that one) — and then says the window waited: nothing sent, «Save» grey and the amount field silent. Then the business
// answers (`answer`) and «Save» lights up. A window without FormModal (the till's sheets and its charge sheet, hub#921)
// says its own door past the grey button (`submit`), or `null` when its button is its only one. When the read of the
// money fails instead (`expectSaysMoneyUnreadable`, hub#938), the window says so — the platform's BusinessMoneyError,
// an alert with «Retry» — with «Save» still grey and nothing sent; «Retry» asks the server again and the notice goes,
// and once the business answers «Save» lights up. For the tests of every app with such a window (Product, Service,
// Menu, Option, the drawer's, the till's), like `business.ts`: free of side effects.
import { FormModal } from '@erplora/ui/components';
import type { LiveClient } from '@erplora/ui/sdk';
import type { VueWrapper } from '@vue/test-utils';
import { expect } from 'vitest';

import { errorFrame } from '../../../packages/ui/src/sdk/__tests__/live-harness';

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
  /** The way a save comes past the grey «Save», which the window's own guard must hold: FormModal's `submit` unless
   *  said (FormModal holds the button's click while grey); another door (the charge sheet's `confirm`), or `null` for
   *  a window whose button is its only door (the till's sheets: a click reaches their handler, grey or not). */
  submit?: (() => unknown) | null;
}

export async function expectSaveWaitsForMoney(window: WaitingWindow, answer: () => Promise<unknown>): Promise<void> {
  window.save()?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
  await window.settle();
  const submit = window.submit === undefined ? () => window.wrapper.findComponent(FormModal).vm.$emit('submit') : window.submit;
  submit?.();
  await window.settle();
  expect(window.sent(), 'sent before the business answered its money').toEqual([]);
  expect([window.save()?.disabled, window.amount()?.errorText], '[«Save» grey, the amount field’s message]').toEqual([true, undefined]);
  await answer();
  await window.settle();
  expect(window.save()?.disabled, '«Save» grey once the business answered').toBe(false);
}

/** The read of the business's money as a window's test drives it (hub#938). */
export interface MoneyRead {
  /** The read fails: an error frame of `base.business.get` (`base.hub_busy`) on the stream. */
  fail: () => Promise<unknown>;
  /** How many times the tab has asked the server so far (the stream's opens): «Retry» asks once more. */
  asked: () => number;
  /** The business answers its money, on the stream «Retry» opened. */
  answer: () => Promise<unknown>;
}

/** The live harness every app's mount spreads (`createTestClient`): its client and its fake network. */
export interface LiveHarness {
  client: LiveClient;
  net: { streams: readonly unknown[]; lastStream: () => { push: (text: string) => void } };
}

/** The read of the money of the tab `m` streams: it fails with `base.hub_busy` on the newest stream, and `answer` is
 *  the app's own (`m.result('base.business.get', …)`). */
export function moneyReadOf(m: LiveHarness, answer: () => Promise<unknown>): MoneyRead {
  return {
    fail: async () => {
      const sub = m.client.stream.subscriptions('base.business.get')[0];
      if (!sub) throw new Error('the window does not follow the business’s money');
      m.net.lastStream().push(errorFrame(sub.id, 'base.hub_busy'));
    },
    asked: () => m.net.streams.length,
    answer,
  };
}

const NOTICE = '[data-testid="base-money-error"]';
const RETRY = '[data-testid="base-money-error-retry"]';

/** In the mounted window (a test modal renders in place) or in the document (Ionic moves a real one to the body). */
function inWindow(window: WaitingWindow, selector: string): HTMLElement | null {
  const found = window.wrapper.find(selector);
  return (found.exists() ? found.element : document.querySelector(selector)) as HTMLElement | null;
}

export async function expectSaysMoneyUnreadable(window: WaitingWindow, read: MoneyRead): Promise<void> {
  await read.fail();
  await window.settle();
  expect(inWindow(window, NOTICE)?.getAttribute('role'), "an alert that says the business's money could not be read").toBe('alert');
  expect(!!inWindow(window, RETRY), '«Retry» in that alert').toBe(true);
  expect([window.save()?.disabled, window.sent()], '[«Save» grey, what was sent] while the money cannot be read').toEqual([true, []]);
  const asked = read.asked();
  inWindow(window, RETRY)?.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
  await window.settle();
  expect([read.asked() - asked, !!inWindow(window, NOTICE)], '«Retry»: [asks the server again, the notice while it asks]').toEqual([1, false]);
  await read.answer();
  await window.settle();
  expect([!!inWindow(window, NOTICE), window.save()?.disabled], 'once the business answers: [the notice, «Save» grey]').toEqual([false, false]);
}
