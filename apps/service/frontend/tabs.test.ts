// The sections of Services (WORKBOOK «Pantallas»; the old manifest's `navigation`): Services,
// Categories and «Bonos y paquetes», as the footer tabbar of every service page, plus «Settings» — the
// tab the old shell generated from the module's settings block, shown only to whoever may save them.
// Each tab follows its route and wears a registered icon, the same as the menu's.

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { SERVICE_TABS, serviceTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return serviceTabs((key) => i18n.global.t(key), { settings });
}

describe('the service tabbar', () => {
  it('is Services, Categories, Packages and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['services', 'Services', '/service/services'],
      ['categories', 'Categories', '/service/categories'],
      ['packages', 'Packages', '/service/packages'],
      ['settings', 'Settings', '/service/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['services', 'categories', 'packages']);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Servicios', 'Categorías', 'Bonos y paquetes', 'Ajustes']);
  });

  it("wears the old module's briefcase on Services and its gift on Packages", () => {
    expect(SERVICE_TABS.map((tab) => [tab.id, tab.icon])).toEqual([
      ['services', 'ion:briefcase-outline'],
      ['categories', 'ion:pricetags-outline'],
      ['packages', 'ion:gift-outline'],
      ['settings', 'ion:settings-outline'],
    ]);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of SERVICE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const menu = appMenu('service');
    expect(menu.map((entry) => [entry.id, entry.icon, entry.path])).toEqual(SERVICE_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
    // «Settings» opens with the permission its pages show the tab with.
    expect(menu.find((entry) => entry.id === 'settings')?.permission).toBe('service.manage_settings');
  });
});
