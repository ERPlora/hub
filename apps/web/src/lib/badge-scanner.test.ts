// @vitest-environment happy-dom
// **The burst is caught by TIMING, in a global listener — never by a focused field** (hub#658).
//
// The market decision of the issue is explicit about this, and names the reason: the Odoo forum is
// a ten-year record of what the other way costs. A reader is a keyboard. If the capture depends on
// a field having focus, the burst lands wherever the caret happens to be — the search box, a
// quantity, a customer name — and the trailing Enter "presses" whichever button is under the
// mouse. There is no field to focus at the counter: nobody clicks before swiping.
//
// So the rule this file pins is a rule about SPEED, not about focus:
//   · a reader types ~1–10 ms per character; a person types ~100 ms+;
//   · the burst ends with Enter;
//   · anything slower is a human, and a human's keystrokes must reach the page untouched.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

import {
  BADGE_MAX_GAP_MS,
  deliverBadge,
  installBadgeScanner,
  onBadgeScan,
  onBadgeWaiting,
} from './badge-scanner';

/** One keystroke, `gap` ms after the previous one. Returns the event so a test can inspect it. */
function press(key: string, gap = 0): KeyboardEvent {
  vi.advanceTimersByTime(gap);
  const ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  document.dispatchEvent(ev);
  return ev;
}

/** A reader's burst: every character within the machine window, terminated by Enter. */
function swipe(badge: string, gap = 5): void {
  for (const ch of badge) press(ch, gap);
  press('Enter', gap);
}

let uninstall: () => void;
/** Every subscription of the running test, so none of them leaks into the next one. */
let subscriptions: Array<() => void> = [];

function listen(handler: (badge: string) => void): () => void {
  const off = onBadgeScan(handler);
  subscriptions.push(off);
  return off;
}

beforeEach(() => {
  vi.useFakeTimers();
  uninstall = installBadgeScanner();
});

afterEach(() => {
  for (const off of subscriptions) off();
  subscriptions = [];
  uninstall();
  vi.useRealTimers();
});

describe('badge scanner', () => {
  it('reports a fast burst terminated by Enter as a badge', () => {
    const seen: string[] = [];
    listen((badge) => seen.push(badge));

    swipe('0009171456');

    expect(seen).toEqual(['0009171456']);
  });

  it('ignores a human typing the very same characters', () => {
    // The whole test suite in one case: identical keys, identical order, identical Enter — only
    // the pace differs, and the pace is the only thing that can tell a reader from a person.
    const seen: string[] = [];
    listen((badge) => seen.push(badge));

    swipe('0009171456', BADGE_MAX_GAP_MS + 40);

    expect(seen).toEqual([]);
  });

  it('does not need any field to be focused, and swallows the burst so it cannot land in one', () => {
    // The Odoo failure mode is the burst reaching the page. A burst is consumed from the SECOND
    // keystroke on — the point at which the pace proves it is a machine — and, crucially, the
    // trailing Enter always is: that is the keystroke that submits a form or "clicks" whatever
    // button is under the mouse, and it is the one that turns a stray swipe into an action.
    //
    // The first character is deliberately NOT swallowed, and that is a limit of timing detection
    // rather than an oversight: at the instant of key one there is nothing to tell it apart from
    // somebody starting to type, and eating every first keystroke would kill the keyboard.
    const seen: string[] = [];
    listen((badge) => seen.push(badge));

    const events: KeyboardEvent[] = [];
    for (const ch of '0009171456') events.push(press(ch, 5));
    const enter = press('Enter', 5);

    expect(seen).toEqual(['0009171456']);
    expect(enter.defaultPrevented).toBe(true);
    expect(events.slice(1).every((e) => e.defaultPrevented)).toBe(true);
    expect(events[0]?.defaultPrevented).toBe(false);
  });

  it('leaves a human keystroke completely alone', () => {
    const ev = press('a', 500);
    expect(ev.defaultPrevented).toBe(false);
  });

  it('forgets a burst that stops halfway, so the next swipe is not polluted', () => {
    const seen: string[] = [];
    listen((badge) => seen.push(badge));

    for (const ch of '00091') press(ch, 5);
    // …the reader was pulled away. Long silence, then a real swipe.
    vi.advanceTimersByTime(BADGE_MAX_GAP_MS * 20);
    swipe('4A00B7C219E3', 5);

    expect(seen).toEqual(['4A00B7C219E3']);
  });

  it('ignores a burst too short to be a card', () => {
    // Someone hammering Enter, or a two-key shortcut, is not a badge.
    const seen: string[] = [];
    listen((badge) => seen.push(badge));

    swipe('12');

    expect(seen).toEqual([]);
  });

  it('hands the scan to the LAST subscriber, so a dialog takes precedence over the page behind it', () => {
    // The elevation dialog opens on top of a screen that is also listening. Delivering to both
    // would approve an action and sign somebody in with one swipe.
    const page: string[] = [];
    const dialog: string[] = [];
    listen((badge) => page.push(badge));
    const closeDialog = listen((badge) => dialog.push(badge));

    swipe('0009171456');
    expect([page, dialog]).toEqual([[], ['0009171456']]);

    closeDialog();
    swipe('0009171456');
    expect(page).toEqual(['0009171456']);
  });

  it('reports nothing at all when nobody is listening', () => {
    // No subscriber means no screen wants a badge right now — and then the keystrokes are not ours
    // to swallow either.
    const enter = (() => {
      for (const ch of '0009171456') press(ch, 5);
      return press('Enter', 5);
    })();
    expect(enter.defaultPrevented).toBe(false);
  });

  it('stops listening once uninstalled', () => {
    const seen: string[] = [];
    listen((badge) => seen.push(badge));
    uninstall();

    swipe('0009171456');

    expect(seen).toEqual([]);
  });
});

// ── The door a second origin comes in through (hub#988) ────────────────────────────────────────
//
// The tablet's own NFC reader produces the same thing a swipe produces, and it has to reach the
// same subscribers or every screen would need a second code path. What it needs from here is a way
// IN (`deliverBadge`) and a way to know when anybody is actually waiting (`onBadgeWaiting`) — a
// radio held open under a screen nobody is looking at drains a counter tablet and delivers taps to
// callbacks that are long gone.

describe('the badge door', () => {
  it('delivers a badge from another origin to the same last subscriber', () => {
    const page: string[] = [];
    const dialog: string[] = [];
    listen((badge) => page.push(badge));
    const closeDialog = listen((badge) => dialog.push(badge));

    expect(deliverBadge('04A23B5C6D7E80')).toBe(true);
    expect([page, dialog]).toEqual([[], ['04A23B5C6D7E80']]);

    closeDialog();
    deliverBadge('04A23B5C6D7E80');
    expect(page).toEqual(['04A23B5C6D7E80']);
  });

  it('says so when nobody is listening, instead of dropping the card in silence', () => {
    expect(deliverBadge('04A23B5C6D7E80')).toBe(false);
  });

  it('announces the first subscriber and the departure of the last one', () => {
    // The edges, not every subscription: a dialog opening on top of a listening page must not read
    // as "start the radio again", and its closing must not read as "stop" while the page waits.
    const waiting: boolean[] = [];
    // The snapshot on subscribing (nobody is waiting yet) — see the test below for why it is there.
    const stopWatching = onBadgeWaiting((isWaiting) => waiting.push(isWaiting));
    expect(waiting).toEqual([false]);

    const offPage = listen(() => {});
    const offDialog = listen(() => {});
    expect(waiting).toEqual([false, true]);

    offDialog();
    expect(waiting).toEqual([false, true]);

    offPage();
    expect(waiting).toEqual([false, true, false]);

    stopWatching();
  });

  it('tells a late watcher whether somebody is already waiting', () => {
    // The NFC reader is installed once at boot and screens subscribe later — but a hot reload, or
    // an install after the login screen has already mounted, would otherwise leave it convinced
    // that nobody wants a card.
    listen(() => {});

    const waiting: boolean[] = [];
    const stopWatching = onBadgeWaiting((isWaiting) => waiting.push(isWaiting));
    expect(waiting).toEqual([true]);

    stopWatching();
  });
});
