// The sections of Staff (WORKBOOK «Pantallas»; the old manifest's `navigation`): Staff, Roles, Time Off
// and Schedules, as the footer tabbar of every staff page, plus «Settings» — the tab the old shell
// generated from the module's settings block, shown only to whoever may save them (old hub#2588,
// hub#2621). Each tab follows its route and wears a registered icon, the same as the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { STAFF_TABS, staffTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return staffTabs((key) => i18n.global.t(key), { settings });
}

describe('the staff tabbar', () => {
  it('is Staff, Roles, Time Off, Schedules and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['staff', 'Staff', '/staff/members'],
      ['roles', 'Roles', '/staff/roles'],
      ['time_off', 'Time Off', '/staff/time-off'],
      ['schedules', 'Schedules', '/staff/schedules'],
      ['settings', 'Settings', '/staff/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['staff', 'roles', 'time_off', 'schedules']);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Personal', 'Roles', 'Ausencias', 'Horarios', 'Ajustes']);
  });

  it('gives every tab a registered icon, the old module’s ones', () => {
    for (const tab of STAFF_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
    expect(STAFF_TABS.map((t) => t.icon)).toEqual([
      'ion:people-outline',
      'ion:shield-outline',
      'ion:calendar-outline',
      'ion:time-outline',
      'ion:settings-outline',
    ]);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*id="([a-z_]+)",\s*label=_\("[^"]+"\),\s*icon="([^"]+)",\s*path="([^"]+)",?\s*\)/g)].map((m) => [
      m[1],
      m[2],
      m[3],
    ]);
    expect(menu).toEqual(STAFF_TABS.filter((tab) => tab.id !== 'settings').map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
