// The sections of Staff (WORKBOOK «Pantallas»; the old manifest's `navigation`): Staff, Roles, Time Off
// and Schedules, as the footer tabbar of every staff page, plus «Commissions» (STAFF-F21), shown only to
// whoever sees the pay, and «Settings» — the tab the old shell generated from the module's settings
// block, shown only to whoever may save them (old hub#2588, hub#2621). Each tab follows its route and
// wears a registered icon, the same as the menu's.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { STAFF_TABS, staffTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true, commissions = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return staffTabs((key) => i18n.global.t(key), { settings, commissions });
}

describe('the staff tabbar', () => {
  it('is Staff, Roles, Time Off, Schedules, Commissions and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['staff', 'Staff', '/staff/members'],
      ['roles', 'Roles', '/staff/roles'],
      ['time_off', 'Time Off', '/staff/time-off'],
      ['schedules', 'Schedules', '/staff/schedules'],
      ['commissions', 'Commissions', '/staff/commissions'],
      ['settings', 'Settings', '/staff/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['staff', 'roles', 'time_off', 'schedules', 'commissions']);
  });

  it('leaves Commissions out for whoever does not see the pay (an employee)', () => {
    expect(tabsIn('en', true, false).map((t) => t.id)).toEqual(['staff', 'roles', 'time_off', 'schedules', 'settings']);
    expect(tabsIn('en', false, false).map((t) => t.id)).toEqual(['staff', 'roles', 'time_off', 'schedules']);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Personal', 'Roles', 'Ausencias', 'Horarios', 'Comisiones', 'Ajustes']);
  });

  it('gives every tab a registered icon, the old module’s ones', () => {
    for (const tab of STAFF_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
    expect(STAFF_TABS.map((t) => t.icon)).toEqual([
      'ion:people-outline',
      'ion:shield-outline',
      'ion:calendar-outline',
      'ion:time-outline',
      'ion:wallet-outline',
      'ion:settings-outline',
    ]);
  });

  it('every staff page offers Commissions to whoever sees the pay and Settings to whoever saves them', () => {
    const pages = join(dirname(fileURLToPath(import.meta.url)), 'pages');
    const vues = readdirSync(pages).filter((name) => name.endsWith('.vue'));
    expect(vues).toHaveLength(6);
    for (const name of vues) {
      const source = readFileSync(join(pages, name), 'utf8');
      expect(source, name).toMatch(/staffTabs\(\$t, \{ settings: \w+, commissions: \w+ \}\)/);
      expect(source, name).toContain("session.can('staff.view_compensation')");
    }
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*id="([a-z_]+)",\s*label=_\("[^"]+"\),\s*icon="([^"]+)",\s*path="([^"]+)",?\s*\)/g)].map((m) => [
      m[1],
      m[2],
      m[3],
    ]);
    // Commissions and Settings depend on a permission: the menu (apps.py) cannot say so, the tabbar does.
    expect(menu).toEqual(STAFF_TABS.filter((tab) => !['commissions', 'settings'].includes(tab.id)).map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
