// @vitest-environment happy-dom
// hub#2444 — **a link from Settings or Employees to a System tab opened Resources instead.**
//
// Ionic keeps every visited page mounted, and `useRoute()` is the app's ONE route. Each tabbed page
// synced its tab with `route.hash` without asking whose address it was, so the page left behind
// read the next page's hash as one of its own unknown tabs and wrote its default back onto it:
// `/settings#tickets` → «Go to Updates» ended on `/system#hub` (System → Resources), and
// `/apps#all` → `/system#updates` silently flipped Apps back to «My apps» behind the scenes.
// System got the path guard in hub#2332; `useHashTab` is that same guard for every tabbed page.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { defineComponent, h, type Ref } from 'vue';

const { route, replace } = await vi.hoisted(async () => {
  const vue = await import('vue');
  const route = vue.reactive({ path: '/settings', hash: '' });
  // The router applies a replace: the address changes, and the watchers see it.
  const replace = vi.fn((to: { path?: string; hash?: string }) => {
    if (to.path !== undefined) route.path = to.path;
    if (to.hash !== undefined) route.hash = to.hash;
    return Promise.resolve();
  });
  return { route, replace };
});

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, push: vi.fn() }),
}));

import { useHashTab } from './hash-tab';

type Tab = 'hub' | 'tickets' | 'data';
const TABS: readonly Tab[] = ['hub', 'tickets', 'data'];
const resolve = (hash: string): Tab => TABS.find((v) => v === hash.slice(1)) ?? 'hub';
const resolveWithRetired = (hash: string): Tab => (hash === '#export' ? 'data' : resolve(hash));

// Every page shares the ONE route: a page left mounted by a previous test would still react to it.
const mounted: Array<{ unmount: () => void }> = [];

function mountTabbed(options?: { canonicalize?: boolean; resolver?: (hash: string) => Tab }): Ref<Tab> {
  let tab!: Ref<Tab>;
  const wrapper = mount(
    defineComponent({
      setup() {
        tab = useHashTab('/settings', options?.resolver ?? resolve, { canonicalize: options?.canonicalize });
        return () => h('div');
      },
    }),
  );
  mounted.push(wrapper);
  return tab;
}

async function goTo(path: string, hash: string): Promise<void> {
  route.path = path;
  route.hash = hash;
  await flushPromises();
}

afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount());
});

beforeEach(() => {
  route.path = '/settings';
  route.hash = '';
  replace.mockClear();
});

describe('a tabbed page follows its own address', () => {
  it('opens the tab its address names', () => {
    route.hash = '#tickets';
    expect(mountTabbed().value).toBe('tickets');
  });

  it('opens the default tab on a plain address', () => {
    expect(mountTabbed().value).toBe('hub');
  });

  it('a link to another of its tabs opens it, without rewriting the address', async () => {
    const tab = mountTabbed();
    await goTo('/settings', '#data');
    expect(tab.value).toBe('data');
    expect(replace).not.toHaveBeenCalled();
  });

  it('choosing a tab writes it to the address', async () => {
    const tab = mountTabbed();
    tab.value = 'tickets';
    await flushPromises();
    expect(replace).toHaveBeenCalledWith({ hash: '#tickets' });
    expect(route.hash).toBe('#tickets');
  });

  it('choosing the default tab on a plain address leaves it plain', async () => {
    route.hash = '#tickets';
    const tab = mountTabbed();
    await goTo('/settings', '');
    expect(tab.value).toBe('hub');
    expect(replace).not.toHaveBeenCalled();
  });
});

describe("leaving the page leaves the next screen's address alone", () => {
  it('a link to another page with a hash is not rewritten by the page left behind', async () => {
    route.hash = '#tickets';
    const tab = mountTabbed();
    await goTo('/system', '#updates');
    expect(replace).not.toHaveBeenCalled();
    expect(route.hash).toBe('#updates');
    expect(tab.value).toBe('tickets');
  });

  it('a page that canonicalizes its hash does not canonicalize somebody else’s', async () => {
    route.hash = '#tickets';
    mountTabbed({ canonicalize: true });
    await goTo('/system', '#updates');
    expect(replace).not.toHaveBeenCalled();
    expect(route.hash).toBe('#updates');
  });

  it('a tab changed while the page is behind does not write onto the other page', async () => {
    route.hash = '#tickets';
    const tab = mountTabbed();
    await goTo('/system', '#updates');
    tab.value = 'hub'; // e.g. Employees taking a session that stopped being admin off an admin tab
    await flushPromises();
    expect(replace).not.toHaveBeenCalled();
    expect(route.hash).toBe('#updates');
  });

  // The guard must not turn into «remember the last tab» (hub#2447): back on a plain address the
  // page opens the tab that address names, as a fresh visit would.
  it('coming back to a plain address opens the tab it names', async () => {
    route.hash = '#tickets';
    const tab = mountTabbed();
    await goTo('/home', '');
    await goTo('/settings', '');
    expect(tab.value).toBe('hub');
    expect(replace).not.toHaveBeenCalled();
  });

  it('coming back with the same hash it left with still opens that tab', async () => {
    route.hash = '#data';
    const tab = mountTabbed();
    await goTo('/home', '');
    tab.value = 'tickets';
    await flushPromises();
    await goTo('/settings', '#data');
    expect(tab.value).toBe('data');
  });
});

describe('canonicalize: a retired or unknown hash is rewritten to the tab it opened', () => {
  it('on arrival', () => {
    route.hash = '#export';
    const tab = mountTabbed({ canonicalize: true, resolver: resolveWithRetired });
    expect(tab.value).toBe('data');
    expect(replace).toHaveBeenCalledWith({ hash: '#data' });
  });

  it('when a link lands on it while the page is open', async () => {
    const tab = mountTabbed({ canonicalize: true, resolver: resolveWithRetired });
    await goTo('/settings', '#export');
    expect(tab.value).toBe('data');
    expect(route.hash).toBe('#data');
  });

  it('a page that does not canonicalize keeps an unknown hash that does not change its tab', async () => {
    const tab = mountTabbed();
    await goTo('/settings', '#bogus');
    expect(tab.value).toBe('hub');
    expect(replace).not.toHaveBeenCalled();
  });

  it('…and it does canonicalize, as before, that same hash on the page', async () => {
    const tab = mountTabbed({ canonicalize: true });
    await goTo('/settings', '#bogus');
    expect(tab.value).toBe('hub');
    expect(route.hash).toBe('#hub');
  });

  it('does not canonicalize when the page is first built under another address', () => {
    route.path = '/system';
    route.hash = '#updates';
    mountTabbed({ canonicalize: true });
    expect(replace).not.toHaveBeenCalled();
  });
});
