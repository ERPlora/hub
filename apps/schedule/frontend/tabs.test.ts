// The three sections of Schedules (the old manifest's `navigation`): Hours, Special days and Settings, as
// the footer tabbar of every schedule page. Each tab follows its route, has its icon (a registered one:
// an unregistered icon paints nothing) and its label in the reader's language.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { SCHEDULE_TABS, scheduleTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return scheduleTabs((key) => i18n.global.t(key));
}

describe('the schedule tabbar', () => {
  it('is Hours, Special days and Settings, each on its own route, the order of the menu (apps.py)', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['hours', 'Hours', '/schedule/hours'],
      ['special_days', 'Special days', '/schedule/special-days'],
      ['settings', 'Settings', '/schedule/settings'],
    ]);
  });

  it('speaks Spanish with the old module’s words', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Horario', 'Días especiales', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of SCHEDULE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same ids, icons and paths as the menu entries of apps.py', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.replace(/\s+/g, ' ').matchAll(/Nav\( ?"([a-z_]+)", .*?, "(ion:[a-z-]+)", "(\/schedule\/[a-z-]+)",? ?\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(SCHEDULE_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
