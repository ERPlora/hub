// The three sections of Taxes (the WORKBOOK's screens; the old manifest's `navigation`): Categories,
// Rules and Aliases, as the footer tabbar of every tax page. Each tab follows its route, has its icon
// (a registered one: an unregistered icon paints nothing) and its label in the reader's language.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { TAX_TABS, taxTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return taxTabs((key) => i18n.global.t(key));
}

describe('the tax tabbar', () => {
  it('is Categories, Rules and Aliases, each on its own route, the order of the menu (apps.py)', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['categories', 'Categories', '/tax/categories'],
      ['rules', 'Rules', '/tax/rules'],
      ['aliases', 'Aliases', '/tax/aliases'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Categorías', 'Reglas', 'Alias']);
  });

  it('gives every tab a registered icon, the rules their receipt as in the old menu', () => {
    for (const tab of TAX_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
    expect(TAX_TABS.find((t) => t.id === 'rules')?.icon).toBe('ion:receipt-outline');
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\("([a-z]+)", _\("[^"]+"\), "([^"]+)", "([^"]+)"\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(TAX_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
