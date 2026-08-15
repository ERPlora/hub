// @vitest-environment happy-dom
// **The second origin of the SAME badge path** (hub#988, follow-up of hub#658/#993).
//
// At a counter the badge arrives through a €15 USB reader that types the number like a keyboard,
// and `badge-scanner.ts` catches the burst by its speed. On a tablet there is no USB reader — and
// the reader has been inside the device all along, unused: a salon on a tablet simply could not
// enrol or read a card.
//
// What this file pins is the design condition of the issue: **one badge path, two origins**. The
// tap goes out through `deliverBadge`, the very door the keyboard burst uses, so the login screen,
// the approval dialog and the staff form never learn where a card came from. And the reader only
// runs while somebody is actually waiting for a card — reader mode left open outlives the screen
// that asked for it and delivers the next tap to nobody.
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

import { onBadgeScan } from './badge-scanner';
import {
  NFC_READ_COMMAND,
  classifyNfcRefusal,
  installNfcBadgeReader,
  nfcBadgeReady,
} from './nfc-badge';

/**
 * A fake shell: every `invoke` is served from a queue the test writes.
 *
 * A string is a card, an `Error` is a refusal, and once the queue runs out every further read
 * answers an EMPTY window — what a real till does between cards. Writing it that way means a test
 * can assert a card was delivered ONCE without the fake handing out the same card forever.
 *
 * Note the shape: a served read is always an OBJECT, and a bare `null` means something else
 * entirely — there is no shell at all. That distinction is the contract, so the fake honours it.
 */
function shell(answers: Array<string | null | Error>) {
  const calls: Array<Record<string, unknown> | undefined> = [];
  let at = 0;
  return {
    calls,
    invoke: async (cmd: string, args?: Record<string, unknown>) => {
      expect(cmd).toBe(NFC_READ_COMMAND);
      calls.push(args);
      const answer = at < answers.length ? answers[at] : null;
      at += 1;
      if (answer instanceof Error) throw answer;
      return { badge: answer };
    },
  };
}

/** Lets the microtask queue drain, then any timer the loop armed. */
async function settle(ms = 0): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms);
}

/** Comfortably past the loop's back-off, so the read after a refusal has certainly happened. */
const BACKOFF_WAIT_MS = 5_000;

let stop: (() => void) | null = null;
let subscriptions: Array<() => void> = [];

function waitForBadge(handler: (badge: string) => void): () => void {
  const off = onBadgeScan(handler);
  subscriptions.push(off);
  return off;
}

beforeEach(() => {
  vi.useFakeTimers();
  nfcBadgeReady.value = false;
});

afterEach(() => {
  for (const off of subscriptions) off();
  subscriptions = [];
  stop?.();
  stop = null;
  vi.useRealTimers();
});

describe('classifyNfcRefusal', () => {
  // Three refusals and three different things to do about them. One shared "it did not work"
  // would send a user whose tablet has NO chip into the settings looking for a toggle (hub#338).
  it('tells the three refusals apart', () => {
    expect(classifyNfcRefusal('nfc_unavailable')).toBe('unavailable');
    expect(classifyNfcRefusal('nfc_disabled')).toBe('disabled');
    expect(classifyNfcRefusal('nfc_random_uid')).toBe('random-uid');
  });

  it('reads the refusal out of whatever wrapper it arrives in', () => {
    // Tauri hands a rejection back as the serialized `ShellError`, but a plugin failure can also
    // arrive already rendered as `[code] - message`. Both have to be recognised, or the shell
    // keeps polling a device that has no reader.
    expect(classifyNfcRefusal(new Error('nfc_disabled'))).toBe('disabled');
    expect(classifyNfcRefusal('[nfc_unavailable] - no reader on this device')).toBe('unavailable');
  });

  it('does not lend one of the three names to an unrelated failure', () => {
    expect(classifyNfcRefusal('activity is not resumed')).toBe('failed');
    expect(classifyNfcRefusal(undefined)).toBe('failed');
  });
});

describe('the NFC badge reader', () => {
  it('delivers a tapped card through the same door as the USB reader', async () => {
    // The whole point. Nothing subscribes to NFC: the staff form and the login screen subscribe to
    // `onBadgeScan`, and a tap arrives there indistinguishable from a swipe.
    const seen: string[] = [];
    const app = shell(['04A23B5C6D7E80']);
    stop = installNfcBadgeReader({ invoke: app.invoke });

    waitForBadge((badge) => seen.push(badge));
    await settle();

    expect(seen).toEqual(['04A23B5C6D7E80']);
  });

  it('does not open the reader while nobody is waiting for a card', async () => {
    // Reader mode is a radio. Polling with no screen waiting drains the battery of a device that
    // spends its day on a counter, and delivers taps to nobody.
    const app = shell([]);
    stop = installNfcBadgeReader({ invoke: app.invoke });

    await settle(60_000);

    expect(app.calls).toHaveLength(0);
  });

  it('stops reading when the last screen stops waiting', async () => {
    const app = shell([]);
    stop = installNfcBadgeReader({ invoke: app.invoke });

    const off = waitForBadge(() => {});
    await settle(1_000);
    const whileWaiting = app.calls.length;
    expect(whileWaiting).toBeGreaterThan(0);

    off();
    await settle(60_000);

    expect(app.calls).toHaveLength(whileWaiting);
  });

  it('keeps polling after a window that nothing was tapped in', async () => {
    // An empty window is the ordinary outcome of every read: it closed with no card on it. Treating
    // it as the end would give the user exactly one chance to find the card in their pocket.
    const app = shell([null, null, '0ABCDEF1']);
    const seen: string[] = [];
    stop = installNfcBadgeReader({ invoke: app.invoke });

    waitForBadge((badge) => seen.push(badge));
    await settle(1_000);

    expect(app.calls.length).toBeGreaterThanOrEqual(3);
    expect(seen).toEqual(['0ABCDEF1']);
  });

  it('stops for good on a device with no reader', async () => {
    // `nfc_unavailable` is a fact about the hardware, not a transient failure. Retrying it is an
    // infinite loop across the whole shift on every desktop and every tablet without a chip.
    const app = shell([new Error('nfc_unavailable')]);
    stop = installNfcBadgeReader({ invoke: app.invoke });

    waitForBadge(() => {});
    await settle(120_000);

    expect(app.calls).toHaveLength(1);
    expect(nfcBadgeReady.value).toBe(false);
  });

  it('announces the reader only once a read has actually been served', async () => {
    // The enrolment field says «or tap the card on this device» — and it must only say it where
    // that is true. Guessing from `isTauri()` would promise a tap on every desktop install.
    const app = shell([]);
    stop = installNfcBadgeReader({ invoke: app.invoke });
    expect(nfcBadgeReady.value).toBe(false);

    waitForBadge(() => {});
    await settle();

    expect(nfcBadgeReady.value).toBe(true);
  });

  it('says NFC is switched off once, not on every retry', async () => {
    // The refusal the user CAN act on, and the one that repeats every window until they do. A
    // toast per poll would be a toast every fifteen seconds on top of the till.
    const told: string[] = [];
    const app = shell([new Error('nfc_disabled')]);
    stop = installNfcBadgeReader({ invoke: app.invoke, notify: (key) => told.push(key) });

    waitForBadge(() => {});
    await settle(120_000);

    expect(told).toEqual(['badge.nfcDisabled']);
    // A reader that is merely off is still a reader: the device can read a card the moment the
    // user flips the toggle, so polling must not stop the way `unavailable` does.
    expect(app.calls.length).toBeGreaterThan(1);
  });

  it('says a card that randomises its id cannot be a badge — and keeps reading', async () => {
    // Enrolling one would work and then never match again: the employee is locked out by a card
    // that demonstrably worked when it was set up. The person just needs another card, so the
    // reader stays open for it.
    const told: string[] = [];
    const seen: string[] = [];
    const app = shell([new Error('nfc_random_uid'), '04112233445566']);
    stop = installNfcBadgeReader({ invoke: app.invoke, notify: (key) => told.push(key) });

    waitForBadge((badge) => seen.push(badge));
    await settle(BACKOFF_WAIT_MS);

    expect(told).toEqual(['badge.nfcRandomUid']);
    expect(seen).toEqual(['04112233445566']);
  });

  it('backs off after an unexplained failure instead of hammering the radio', async () => {
    const app = shell([new Error('activity is not resumed')]);
    stop = installNfcBadgeReader({ invoke: app.invoke });

    waitForBadge(() => {});
    await settle();
    expect(app.calls).toHaveLength(1);

    await settle(5_000);
    expect(app.calls.length).toBeGreaterThan(1);
  });

  it('asks for a bounded window on every read', async () => {
    // A read with no deadline never returns, so the loop could never notice that the screen it was
    // reading for is gone.
    const app = shell([]);
    stop = installNfcBadgeReader({ invoke: app.invoke });

    waitForBadge(() => {});
    await settle();

    expect(app.calls[0]).toMatchObject({ timeoutMs: expect.any(Number) });
    expect((app.calls[0] as { timeoutMs: number }).timeoutMs).toBeGreaterThan(0);
  });

  it('stops at once in a browser, where there is no shell to ask', async () => {
    // `invokeTauri` answers a bare `null` outside the installed app. That is NOT an empty window:
    // it means there is nothing to ask, ever. Reading it as "nothing tapped" would leave every
    // browser tab polling a command that does not exist for the rest of the session.
    let calls = 0;
    stop = installNfcBadgeReader({
      invoke: async () => {
        calls += 1;
        return null;
      },
    });

    waitForBadge(() => {});
    await settle(60_000);

    expect(calls).toBe(1);
    expect(nfcBadgeReady.value).toBe(false);
  });
});
