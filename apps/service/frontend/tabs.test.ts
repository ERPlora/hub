// The sections of Services (WORKBOOK «Pantallas»; the old manifest's `navigation`): Services,
// Categories and «Bonos y paquetes», as the footer tabbar of every service page, plus «Settings» — the
// tab the old shell generated from the module's settings block, shown only to whoever may save them.
// Each tab follows its route and wears a registered icon, the same as the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

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

  it('gives every tab a registered icon', () => {
    for (const tab of SERVICE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z_]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)",?\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(SERVICE_TABS.filter((tab) => tab.id !== 'settings').map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
