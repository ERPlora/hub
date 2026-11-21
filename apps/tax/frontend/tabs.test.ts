// The three sections of Taxes (the WORKBOOK's screens; the old manifest's `navigation`): Categories,
// Rules and Aliases, as the footer tabbar of every tax page. Each tab follows its route, has its icon
// (a registered one: an unregistered icon paints nothing) and its label in the reader's language.

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { TAX_TABS, taxTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return taxTabs((key) => i18n.global.t(key));
}

describe('the tax tabbar', () => {
  it('is Categories, Rules, Aliases and Settings, each on its own route, the order of the menu (apps.py)', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['categories', 'Categories', '/tax/categories'],
      ['rules', 'Rules', '/tax/rules'],
      ['aliases', 'Aliases', '/tax/aliases'],
      ['settings', 'Settings', '/tax/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Categorías', 'Reglas', 'Alias', 'Ajustes']);
  });

  it('gives every tab a registered icon, the old menu\'s: price tags, receipt and the horizontal swap', () => {
    for (const tab of TAX_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
    expect(TAX_TABS.map((t) => t.icon)).toEqual([
      'ion:pricetags-outline',
      'ion:receipt-outline',
      'ion:swap-horizontal-outline',
      'ion:settings-outline',
    ]);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const menu = appMenu('tax').map((entry) => [entry.id, entry.icon, entry.path]);
    expect(menu).toEqual(TAX_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
