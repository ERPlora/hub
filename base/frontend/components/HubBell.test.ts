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
  // The old hub's bell asked the server every 30 s; this one is told by the live query. Fake timers run the
  // page's clock five minutes ahead: nothing else must have asked the server, nor reopened the stream.
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
