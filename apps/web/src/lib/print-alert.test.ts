// Tests of the undrained-printing signal that feeds the topbar bell (hub#987).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { notificationCount, setNotificationCount } from './shell';

const isAuthed = { value: true };

vi.mock('./session', () => ({
  get isAuthed() {
    return isAuthed;
  },
}));
vi.mock('./runtime', () => ({ runtimeHeaders: () => ({}) }));

// Imported after the mocks so the module under test picks them up.
const { refreshUndrainedPrinting, undrainedStations } = await import('./print-alert');

/** `GET /api/print/undrained` answering with `count` stalled stations. */
function answers(count: number, stations: unknown[] = []): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ ok: true, count, thresholdSeconds: 60, stations }),
    })),
  );
}

describe('undrained printing feeds the bell', () => {
  beforeEach(() => {
    isAuthed.value = true;
    setNotificationCount(0, 'printing');
    setNotificationCount(0, 'deadLetters');
  });
  afterEach(() => vi.unstubAllGlobals());

  // THE alarm reaching a screen is the whole point of hub#987: `coverage` already knew the kitchen
  // was piling up, and the only place that said so was a tab in Settings nobody opens mid-service.
  it('puts a stalled station on the bell', async () => {
    answers(1, [{ role: 'kitchen', waiting: 3, liveHosts: 0, waitingSeconds: 240 }]);

    await refreshUndrainedPrinting();

    expect(notificationCount.value).toBe(1);
    expect(undrainedStations.value[0]?.role).toBe('kitchen');
  });

  // It self-heals: switch the till back on, the queue drains, the badge goes. No dismiss button,
  // because there is nothing to dismiss — the state IS the notification (ADR-0067).
  it('clears itself once the queue drains', async () => {
    answers(1, [{ role: 'kitchen', waiting: 3, liveHosts: 0, waitingSeconds: 240 }]);
    await refreshUndrainedPrinting();
    expect(notificationCount.value).toBe(1);

    answers(0);
    await refreshUndrainedPrinting();

    expect(notificationCount.value).toBe(0);
    expect(undrainedStations.value).toEqual([]);
  });

  // The bell has two sources now (dead-letters, hub#660; printing, hub#987) and one number. Whoever
  // reports second must ADD to the badge, not replace it: a hub with a dead event AND a dead printer
  // that showed "1" would be hiding one of the two.
  it('adds to the bell instead of overwriting the other source', async () => {
    setNotificationCount(2, 'deadLetters');
    answers(1, [{ role: 'kitchen', waiting: 1, liveHosts: 0, waitingSeconds: 90 }]);

    await refreshUndrainedPrinting();

    expect(notificationCount.value).toBe(3);
  });

  // A fetch that fails leaves the bell where it was. A runtime restarting or a tab that went offline
  // is not a clean bill of health, and flashing zero would teach the operator to trust a green bell
  // that means "we could not ask" — the same rule `fetchPrintHosts` follows for the settings screen.
  it('a failed probe never reads as all-clear', async () => {
    answers(1, [{ role: 'kitchen', waiting: 3, liveHosts: 0, waitingSeconds: 240 }]);
    await refreshUndrainedPrinting();

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline');
      }),
    );
    await refreshUndrainedPrinting();

    expect(notificationCount.value).toBe(1);
  });

  // Unlike the dead-letter count this is NOT admin-only — the person at the counter is the one who
  // can switch the till back on — but it is still a session signal: logged out, no polling, no badge.
  it('says nothing when nobody is logged in', async () => {
    isAuthed.value = false;
    answers(1, [{ role: 'kitchen', waiting: 3, liveHosts: 0, waitingSeconds: 240 }]);

    await refreshUndrainedPrinting();

    expect(notificationCount.value).toBe(0);
  });
});
