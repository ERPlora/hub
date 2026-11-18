import { afterEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import type { BellCounter } from '../operations-bell';
import { clockReads, withFakeTimers } from '../__tests__/clock-reads';
import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import { type BellReading, useBellCounters } from './bell-counters';

let reading: BellReading;
const Host = defineComponent({
  setup() {
    reading = useBellCounters();
    return () => h('div');
  },
});

function counter(key: string, count: number, route = '/demo/items'): BellCounter {
  const label = `Counter ${key}`;
  return {
    key,
    app: key.split('.')[0],
    count,
    route,
    label,
    icon: 'ion:warning-outline',
    severity: 'warning',
    title: `${label} (${count})`,
    body: null,
    action_label: 'Open',
    due: null,
  };
}

const counts = () => reading.counters.value?.counters.map((c) => c.count);

async function setup() {
  const m = await mountBase(Host);
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useBellCounters', () => {
  it('follows base.bell.counters live: nothing until the first result, then each new one', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('base.bell.counters').map((sub) => sub.params)).toEqual([{}]);
    expect(reading.counters.value).toBeUndefined();
    await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 3)], refresh_every: null });
    expect(counts()).toEqual([3]);
    await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 4)], refresh_every: null }, 2);
    expect(counts()).toEqual([4]);
  });

  it('a failed read keeps the last counters and says it failed; retrying reopens the stream', async () => {
    const s = await setup();
    await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 3)], refresh_every: null });
    s.call.push(errorFrame(subId(s.client, 'base.bell.counters'), 'internal'));
    await flush();
    expect(counts()).toEqual([3]);
    expect(reading.status.value).toBe('error');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    reading.refresh();
    expect(reconnect).toHaveBeenCalledOnce();
  });
});

describe('useBellCounters does not poll', () => {
  // The counters are told by the live query and asked again only when a counter says so (`refresh_every`, below).
  // Fake timers run the page's clock five minutes ahead: with no counter asking, nothing else must have asked the
  // server, nor reopened the stream.
  it('asks nothing more once subscribed, however long the page stays open', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'] });
    try {
      const s = await setup();
      await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 1)], refresh_every: null });
      const streams = s.net.streams.length;
      vi.advanceTimersByTime(5 * 60_000);
      await flush();
      expect(fetchSpy).not.toHaveBeenCalled();
      expect(s.net.api).toEqual([]);
      expect(s.net.streams.length).toBe(streams);
      expect(s.client.stream.subscriptions('base.bell.counters')).toHaveLength(1);
    } finally {
      vi.useRealTimers();
      fetchSpy.mockRestore();
    }
  });
});

describe('useBellCounters reads again by the clock when a counter asks', () => {
  // A counter whose figure moves as time passes (a job waiting a minute with no device alive) has no event to re-run
  // the live query; `refresh_every` says how often `base.bell.counters` is read again. The fake timers are the test's
  // only: real ones come back in `finally`.
  const BELL = '/api/home/bell';

  async function clocked(answer: (call: number) => Response | Promise<Response>) {
    const s = await setup();
    return { ...s, ...clockReads(s.net, BELL, answer) };
  }

  it(
    'every refresh_every seconds it reads the counters again and gives them without a reload',
    withFakeTimers(async () => {
      const s = await clocked(() =>
        Response.json({ counters: [counter('printing.stalled_kitchen', 2, '/printing/printers')], refresh_every: 30 }),
      );
      await s.result(s.call, 'base.bell.counters', { counters: [], refresh_every: 30 });
      expect(counts()).toEqual([]);

      await s.tick(29_000);
      expect(s.reads()).toBe(0);
      await s.tick(1_000);
      expect(s.reads()).toBe(1);
      expect(counts()).toEqual([2]);
      await s.tick(30_000);
      expect(s.reads()).toBe(2);
    }),
  );

  it(
    'stops reading when no counter asks any more, and when it is gone',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json({ counters: [], refresh_every: 30 }));
      await s.result(s.call, 'base.bell.counters', { counters: [], refresh_every: 30 });
      await s.tick(30_000);
      expect(s.reads()).toBe(1);

      await s.result(s.call, 'base.bell.counters', { counters: [], refresh_every: null }, 2);
      await s.tick(5 * 60_000);
      expect(s.reads()).toBe(1);

      await s.result(s.call, 'base.bell.counters', { counters: [], refresh_every: 30 }, 3);
      s.wrapper.unmount();
      await s.tick(5 * 60_000);
      expect(s.reads()).toBe(1);
    }),
  );

  it(
    'a reading that fails keeps the last counters, and one older than a live result does not undo it',
    withFakeTimers(async () => {
      let release: (response: Response) => void = () => undefined;
      const s = await clocked((call) =>
        call === 1 ? new Response('{}', { status: 500 }) : new Promise<Response>((resolve) => (release = resolve)),
      );
      await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 3)], refresh_every: 30 });
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      await s.tick(30_000);
      expect(counts()).toEqual([3]);
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();

      await s.tick(30_000); // the second reading is on its way…
      await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 5)], refresh_every: 30 }, 2);
      release(Response.json({ counters: [counter('demo.open_items', 4)], refresh_every: 30 }));
      await flush();
      expect(counts()).toEqual([5]);
    }),
  );

  it(
    'reads nothing while the page is hidden',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json({ counters: [], refresh_every: 30 }));
      await s.result(s.call, 'base.bell.counters', { counters: [], refresh_every: 30 });
      const hidden = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
      try {
        await s.tick(60_000);
        expect(s.reads()).toBe(0);
      } finally {
        hidden.mockRestore();
      }
      await s.tick(30_000);
      expect(s.reads()).toBe(1);
    }),
  );
});
