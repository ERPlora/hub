// The sections of Tables (WORKBOOK «Pantallas»; the old manifest's `navigation`): Floor plan, Zones,
// Tables and Sessions, as the footer tabbar of every table page, plus «Settings» — the tab the old shell
// generated from the module's settings block, shown only to whoever may save them. Each tab follows its
// route and wears a registered icon, the same as the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { TABLE_TABS, tableTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return tableTabs((key) => i18n.global.t(key), { settings });
}

describe('the tables tabbar', () => {
  it('is Floor plan, Zones, Tables, Sessions and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['floor_plan', 'Floor plan', '/table/floor-plan'],
      ['zones', 'Zones', '/table/zones'],
      ['tables', 'Tables', '/table/tables'],
      ['sessions', 'Sessions', '/table/sessions'],
      ['settings', 'Settings', '/table/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['floor_plan', 'zones', 'tables', 'sessions']);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Plano de sala', 'Zonas', 'Mesas', 'Sesiones', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of TABLE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z_]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)",?\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(TABLE_TABS.filter((tab) => tab.id !== 'settings').map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
