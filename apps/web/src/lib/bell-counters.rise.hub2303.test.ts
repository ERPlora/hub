// @vitest-environment happy-dom
// hub#2303 — **the bell counted, but only for whoever was looking at it.**
//
// A WhatsApp customer the automation could not answer, or a booking waiting to be confirmed, raised
// a counter on the bell (hub#1678) — and nothing else. With the tablet propped on the counter, the
// app in the background or the phone in a pocket, nobody found out until they opened the hub.
//
// What is pinned here is the TRIGGER, not the notice (that is `bell-notice.hub2303.test.ts`): a
// counter that goes UP between two polls is announced, once; what was already waiting when the
// shell started, when somebody logged in or when a query recovered from a failure is not — else
// every boot would ring for the whole backlog. And the poll keeps running with the window hidden:
// that is precisely when the notice is needed.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { nextTick, ref } from 'vue';

import type { InstalledManifest } from './module-loader';

const isAuthed = { value: true };
const user = ref<{ id: string } | null>({ id: 'owner' });
const allowed = new Set<string>(['appointments.view', 'whatsapp_inbox.view']);
let installed: InstalledManifest[] = [];
const query = vi.fn<(name: string, params?: Record<string, unknown>) => Promise<unknown>>();

vi.mock('./session', () => ({
  get isAuthed() {
    return isAuthed;
  },
  get user() {
    return user;
  },
  hasPermission: (p: string) => allowed.has(p),
}));
vi.mock('./runtime', () => ({ getClient: () => ({ query }) }));
vi.mock('./module-loader', () => ({ loadInstalledManifests: async () => installed }));

const { refreshBellCounters, bootBellCountersWatch, stopBellCountersWatch, onBellCounterRise } =
  await import('./bell-counters');

const settle = async (): Promise<void> => {
  await nextTick();
  for (let i = 0; i < 10; i++) await Promise.resolve();
};

const NEEDS_ATTENTION = {
  label: 'WhatsApp customers waiting for a reply',
  icon: 'logo-whatsapp',
  query: 'whatsapp_inbox.conversations.count_needs_attention',
  nav: 'inbox',
  permission: 'whatsapp_inbox.view',
};

function inbox(locale?: InstalledManifest['locale']): InstalledManifest {
  return {
    moduleId: 'whatsapp_inbox',
    manifest: {
      id: 'whatsapp_inbox',
      name: 'WhatsApp',
      version: '1.0.0',
      ui: { entry: 'x.js' },
      bell: { 'whatsapp_inbox.needs_attention': NEEDS_ATTENTION },
    } as never,
    entryUrl: '/modules/whatsapp_inbox/x.js',
    locale,
  };
}

/** The count the runtime answers next, per poll. */
function answers(...counts: Array<number | Error>): void {
  for (const c of counts) {
    if (c instanceof Error) query.mockRejectedValueOnce(c);
    else query.mockResolvedValueOnce([{ count: c }]);
  }
}

describe('a bell counter that goes up is announced (hub#2303)', () => {
  const rises: unknown[] = [];
  let off: () => void = () => {};

  beforeEach(() => {
    isAuthed.value = true;
    user.value = { id: 'owner' };
    allowed.clear();
    allowed.add('whatsapp_inbox.view');
    query.mockReset();
    stopBellCountersWatch();
    installed = [inbox()];
    rises.length = 0;
    off = onBellCounterRise((r) => rises.push(r));
  });

  afterEach(() => {
    off();
    vi.useRealTimers();
  });

  // THE symptom: nobody waiting, then a customer the automation handed over → one notice, with the
  // module's label, the new total and the tab the bell row leads to.
  it('announces a counter that goes from nothing to one', async () => {
    answers(0, 1);
    await refreshBellCounters();
    await refreshBellCounters();

    expect(rises).toEqual([
      {
        key: 'whatsapp_inbox.needs_attention',
        moduleId: 'whatsapp_inbox',
        label: 'WhatsApp customers waiting for a reply',
        icon: 'logo-whatsapp',
        count: 1,
        previous: 0,
        path: '/m/whatsapp_inbox/inbox',
      },
    ]);
  });

  it('speaks the label in the language of the app, as the bell row does', async () => {
    installed = [inbox({ bell: { 'whatsapp_inbox.needs_attention': { label: 'Clientes de WhatsApp esperando' } } })];
    answers(1, 2);
    await refreshBellCounters();
    await refreshBellCounters();

    expect(rises).toMatchObject([{ label: 'Clientes de WhatsApp esperando', count: 2, previous: 1 }]);
  });

  // What was already waiting when the shell started is the bell's job, not a notice's: announcing
  // it would ring on every boot of every tablet for the same two customers.
  it('does not announce what was already waiting at the first poll', async () => {
    answers(2);
    await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  it('does not announce a count that stays, or one that goes down', async () => {
    answers(2, 2, 1, 1);
    for (let i = 0; i < 4; i++) await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  it('announces every new rise, not only the first one', async () => {
    answers(0, 1, 1, 3);
    for (let i = 0; i < 4; i++) await refreshBellCounters();

    expect(rises).toMatchObject([
      { count: 1, previous: 0 },
      { count: 3, previous: 1 },
    ]);
  });

  // A first poll that FAILED knows nothing: the backlog it recovers into on the next one is still
  // the backlog, not something that just arrived.
  it('does not announce the backlog when the first query failed and the next one answers', async () => {
    answers(new Error('runtime down'), 2);
    await refreshBellCounters();
    await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  // …while a failure in the middle keeps the last known count (hub#1678), so the recovery is not a
  // rise either — and a real one after it still is.
  it('a failure between two polls is not a rise, and a real rise after it is', async () => {
    answers(1, new Error('blip'), 1, 2);
    for (let i = 0; i < 4; i++) await refreshBellCounters();

    expect(rises).toMatchObject([{ count: 2, previous: 1 }]);
  });

  // Logging in again is a new start: what waited meanwhile is the backlog of whoever arrives.
  it('does not announce the backlog to whoever logs in after a logout', async () => {
    answers(0);
    await refreshBellCounters();
    stopBellCountersWatch();
    answers(3);
    await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  // …and the shell never calls `stopBellCountersWatch` on a logout: the poll keeps running and sees
  // the session gone. That path has to drop the baseline too, or the next login rings for the
  // backlog that grew while nobody was logged in.
  it('does not announce the backlog after a logout the shell only sees as a poll without session', async () => {
    answers(0);
    await refreshBellCounters();
    isAuthed.value = false;
    await refreshBellCounters();
    isAuthed.value = true;
    answers(3);
    await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  // A PIN hand-over to somebody who may see a counter the previous cashier could not: its count is
  // new to this session, not new to the business.
  it('does not announce a counter the session only just became allowed to see', async () => {
    allowed.clear();
    await refreshBellCounters();
    allowed.add('whatsapp_inbox.view');
    answers(2);
    await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  it('stops telling a listener that unsubscribed', async () => {
    off();
    answers(0, 1);
    await refreshBellCounters();
    await refreshBellCounters();

    expect(rises).toEqual([]);
  });

  // A listener that throws must neither break the bell nor starve the other listeners.
  it('a listener that throws does not break the bell or the next listener', async () => {
    const other: unknown[] = [];
    const offBad = onBellCounterRise(() => {
      throw new Error('boom');
    });
    const offOther = onBellCounterRise((r) => other.push(r));
    answers(0, 1);
    await refreshBellCounters();
    await expect(refreshBellCounters()).resolves.toBeUndefined();
    offBad();
    offOther();

    expect(other).toHaveLength(1);
    expect(rises).toHaveLength(1);
  });

  // The notice matters most exactly when nobody is looking: a minimised window or the app in the
  // background is a HIDDEN document, and a poll that only ran while visible never saw the rise.
  it('keeps polling while the window is hidden', async () => {
    vi.useFakeTimers();
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    query.mockResolvedValue([{ count: 0 }]);
    bootBellCountersWatch();
    await settle();
    query.mockResolvedValue([{ count: 1 }]);

    await vi.advanceTimersByTimeAsync(30_000);
    await settle();

    expect(rises).toMatchObject([{ count: 1, previous: 0 }]);
    visibility.mockRestore();
    stopBellCountersWatch();
  });
});
