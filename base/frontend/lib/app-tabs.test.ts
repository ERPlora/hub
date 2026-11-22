import { createShellSession, SESSION_KEY, type SessionMe, type SessionMenuSection } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import { createApp, ref } from 'vue';

import { appTabs, useAppTabs } from './app-tabs';

const KITCHEN: SessionMenuSection = {
  id: 'kitchen',
  label: 'Kitchen',
  items: [
    { path: '/kitchen/display', label: 'Display', icon: 'ion:desktop-outline' },
    { path: '/kitchen/history', label: 'History', icon: 'ion:time-outline' },
  ],
};
const SALE: SessionMenuSection = {
  id: 'sale',
  label: 'Sales & POS',
  items: [
    { path: '/sale/pos', label: 'POS', icon: 'ion:storefront-outline' },
    { path: '/sale/quick-notes', label: 'Quick notes', icon: 'ion:chatbubbles-outline' },
  ],
};

describe('appTabs', () => {
  it("is one tab per entry of the app's menu the session opens, in its order, with its label, icon and path", () => {
    expect(appTabs([SALE, KITCHEN], 'kitchen')).toEqual([
      { id: 'display', label: 'Display', icon: 'ion:desktop-outline', to: '/kitchen/display' },
      { id: 'history', label: 'History', icon: 'ion:time-outline', to: '/kitchen/history' },
    ]);
  });

  it('names a tab by the last part of its path, which its test id `tab-<id>` carries', () => {
    expect(appTabs([SALE], 'sale').map((tab) => tab.id)).toEqual(['pos', 'quick-notes']);
  });

  it('has no tabs for an app the menu leaves out: none of its entries opens to the person', () => {
    expect(appTabs([SALE], 'kitchen')).toEqual([]);
    expect(appTabs([], 'kitchen')).toEqual([]);
  });
});

describe('useAppTabs', () => {
  it('follows the session: a tab leaves the bar as soon as its entry closes', () => {
    const me = ref<SessionMe>({ user: { id: '1', label: 'Ana' }, permissions: [], menu: [KITCHEN], apps: [], language: 'en' });
    const app = createApp({});
    app.provide(SESSION_KEY, createShellSession(me, ref('live')));
    const tabs = app.runWithContext(() => useAppTabs('kitchen'));
    expect(tabs.value.map((tab) => tab.id)).toEqual(['display', 'history']);

    me.value = { ...me.value, menu: [{ ...KITCHEN, items: KITCHEN.items.slice(0, 1) }] };
    expect(tabs.value.map((tab) => tab.id)).toEqual(['display']);
  });
});
