// The bell at the end of the topbar (BASE-G137, hub#1678): `base.bell.counters`, live — it no longer asks every
// 30 s —; its badge sums the counters above zero; opened, one row per counter («Failed events (2)») that leads to
// its screen when this hub has it. A failed read keeps the last counters.
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BellCounter } from '../operations';
import { accessibleName, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import HubBell from './HubBell.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonPopover: IonModalStub };
});

function counter(key: string, count: number, route: string, label = `Counter ${key}`): BellCounter {
  return { key, app: key.split('.')[0], count, route, label, icon: 'ion:warning-outline' };
}

async function setup(options: { routes?: string[]; locale?: 'en' | 'es' } = {}) {
  const m = await mountBase(HubBell, options);
  const call = await m.live();
  const show = (counters: BellCounter[], rev?: number) => m.result(call, 'base.bell.counters', { counters }, rev);
  const badge = () => m.wrapper.find('[data-testid="hub-bell-badge"]');
  const inDoc = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const rows = () => [...document.querySelectorAll<HTMLElement>('[data-testid="hub-bell-row"]')];
  async function open() {
    await m.wrapper.get('[data-testid="hub-bell"]').trigger('click');
    await flush();
  }
  return { ...m, call, show, badge, inDoc, rows, open };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('HubBell', () => {
  it('follows base.bell.counters live and names itself', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.client.stream.subscriptions('base.bell.counters').map((sub) => sub.params)).toEqual([{}]);
    expect(accessibleName(s.wrapper.get('[data-testid="hub-bell"]').element)).toBe('Notificaciones');
  });

  it('with nothing to tell: no badge, and «All caught up» when opened', async () => {
    const s = await setup();
    await s.show([]);
    expect(s.badge().exists()).toBe(false);
    await s.open();
    expect(s.inDoc('hub-bell-empty')?.textContent?.trim()).toBe('All caught up. No notifications.');
  });

  it('sums the counters on the badge and lists one row per counter, with its count', async () => {
    const s = await setup({ locale: 'es' });
    await s.show([counter('base.failed_events', 2, '/system#events', 'Eventos caídos'), counter('demo.open_items', 3, '/demo/items')]);
    expect(s.badge().text()).toBe('5');
    await s.open();
    // Ionic's hydrated elements patch `textContent`: the markup is what the person sees.
    const text = (row: HTMLElement) => row.innerHTML.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
    expect(s.rows().map(text)).toEqual([
      'Eventos caídos (2)',
      'Counter demo.open_items (3)',
    ]);
  });

  it('a row leads to its screen and closes the bell; one whose screen this hub lacks leads nowhere', async () => {
    const s = await setup({ routes: ['/demo/items'] });
    await s.show([counter('base.failed_events', 1, '/system#events'), counter('demo.open_items', 3, '/demo/items')]);
    await s.open();
    const [failed, demo] = s.rows();
    expect(failed.getAttribute('data-reachable')).toBe('false');
    failed.click();
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/');
    demo.click();
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/demo/items');
    expect(s.rows()).toEqual([]);
  });

  it('a new result moves the badge without a reload; a failed read keeps the last one', async () => {
    const s = await setup();
    await s.show([counter('demo.open_items', 3, '/demo/items')]);
    await s.show([counter('demo.open_items', 4, '/demo/items')], 2);
    expect(s.badge().text()).toBe('4');
    s.call.push(errorFrame(subId(s.client, 'base.bell.counters'), 'internal'));
    await flush();
    expect(s.badge().text()).toBe('4');
  });

  it('a read that never came says so when opened, never «All caught up»', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'base.bell.counters'), 'internal'));
    await flush();
    await s.open();
    expect(s.inDoc('hub-bell-empty')).toBeNull();
    expect(s.inDoc('hub-bell-error')?.textContent?.trim()).toBe(
      'Could not check the notifications. They will show up when the connection is back.',
    );
  });
});

describe('HubBell does not poll', () => {
  // The old hub's bell asked the server every 30 s; this one is told by the live query, and asks again only when a
  // counter says so (`refresh_every`, below). Fake timers run the page's clock five minutes ahead: with no counter
  // asking, nothing else must have asked the server, nor reopened the stream.
  it('asks nothing more once subscribed, however long the page stays open', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'] });
    try {
      const s = await setup();
      await s.show([counter('demo.open_items', 1, '/demo/items')]);
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

describe('HubBell reads again by the clock when a counter asks', () => {
  // FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE: a counter whose figure moves as time passes (a job waiting a
  // minute with no device alive) has no event to re-run the live query; `refresh_every` says how often the bell reads
  // `base.bell.counters` again. The fake timers are the test's only: real ones come back in `finally`.
  const BELL = '/api/home/bell';

  async function clocked(answer: (call: number) => Response | Promise<Response>) {
    let calls = 0;
    const s = await setup();
    s.net.onApi(() => answer(++calls));
    const reads = () => s.net.api.filter((call) => call.url.startsWith(BELL)).length;
    const tick = async (ms: number) => {
      vi.advanceTimersByTime(ms);
      await flush();
    };
    return { ...s, reads, tick };
  }

  function withFakeTimers(test: () => Promise<void>) {
    return async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['setTimeout', 'setInterval', 'clearTimeout', 'clearInterval'] });
      try {
        await test();
      } finally {
        vi.useRealTimers();
      }
    };
  }

  it(
    'every refresh_every seconds it reads the counters again and shows them without a reload',
    withFakeTimers(async () => {
      const s = await clocked(() => Response.json({ counters: [counter('printing.stalled_kitchen', 2, '/printing/printers')], refresh_every: 30 }));
      await s.result(s.call, 'base.bell.counters', { counters: [], refresh_every: 30 });
      expect(s.badge().exists()).toBe(false);

      await s.tick(29_000);
      expect(s.reads()).toBe(0);
      await s.tick(1_000);
      expect(s.reads()).toBe(1);
      expect(s.badge().text()).toBe('2');
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
        call === 1
          ? new Response('{}', { status: 500 })
          : new Promise<Response>((resolve) => (release = resolve)),
      );
      await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 3, '/demo/items')], refresh_every: 30 });
      const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      await s.tick(30_000);
      expect(s.badge().text()).toBe('3');
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();

      await s.tick(30_000); // the second reading is on its way…
      await s.result(s.call, 'base.bell.counters', { counters: [counter('demo.open_items', 5, '/demo/items')], refresh_every: 30 }, 2);
      release(Response.json({ counters: [counter('demo.open_items', 4, '/demo/items')], refresh_every: 30 }));
      await flush();
      expect(s.badge().text()).toBe('5');
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
