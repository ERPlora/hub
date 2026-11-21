// The sections of Sales & POS (the WORKBOOK's screens): Sell, Sales, Quick notes, Sections and Settings, as the footer
// tabbar of every sale page. «Sections», not «Departments»: that word is wider than a fifth of a phone's strip, so the
// five tabs would not fit whole. Each tab follows its route, has a registered icon and its label in the reader's
// language, and wears the same icon and path as its menu entry in apps.py.

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { SALE_TABS, saleTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return saleTabs((key) => i18n.global.t(key));
}

describe('the sale tabbar', () => {
  it('is Sell, Sales, Quick notes, Sections and Settings, each on its own route, the order of the menu', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['pos', 'Sell', '/sale/pos'],
      ['sales', 'Sales', '/sale/sales'],
      ['quick_notes', 'Quick notes', '/sale/quick-notes'],
      ['departments', 'Sections', '/sale/departments'],
      ['settings', 'Settings', '/sale/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Vender', 'Ventas', 'Notas rápidas', 'Secciones', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of SALE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py', () => {
    const menu = appMenu('sale').map((entry) => [entry.id, entry.icon, entry.path]);
    expect(menu).toEqual(SALE_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
