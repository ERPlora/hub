// The sections of Kitchen (WORKBOOK «Pantallas»; the old manifest's `navigation`): Display, Tickets,
// Stations and History, as the footer tabbar of every kitchen page, plus «Settings» — the tab the old shell
// generated from the module's settings block, shown only to whoever may save them. Each tab follows its
// route and wears a registered icon, the same as the menu's.

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { KITCHEN_TABS, kitchenTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return kitchenTabs((key) => i18n.global.t(key), { settings });
}

describe('the kitchen tabbar', () => {
  it('is Display, Tickets, Stations, History and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['display', 'Display', '/kitchen/display'],
      ['tickets', 'Tickets', '/kitchen/tickets'],
      ['stations', 'Stations', '/kitchen/stations'],
      ['history', 'History', '/kitchen/history'],
      ['settings', 'Settings', '/kitchen/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['display', 'tickets', 'stations', 'history']);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Pantalla', 'Comandas', 'Estaciones', 'Historial', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of KITCHEN_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const menu = appMenu('kitchen');
    expect(menu.map((entry) => [entry.id, entry.icon, entry.path])).toEqual(KITCHEN_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
    // «Settings» opens with the permission its pages show the tab with.
    expect(menu.find((entry) => entry.id === 'settings')?.permission).toBe('kitchen.change_settings');
  });
});
