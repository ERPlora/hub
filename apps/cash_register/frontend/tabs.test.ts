// The two sections of Cash register (the old menu entry and the settings tab the old hub added), as the
// footer tabbar of every page: each tab follows its route, has a registered icon and its label in the
// reader's language, and wears the same icon and path as its menu entry in apps.py.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { CASH_REGISTER_TABS, cashRegisterTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return cashRegisterTabs((key) => i18n.global.t(key));
}

describe('the cash register tabbar', () => {
  it('is the drawer and its settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['sessions', 'Cash register', '/cash_register/sessions'],
      ['settings', 'Settings', '/cash_register/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Caja', 'Ajustes']);
  });

  it('gives every tab a registered icon, the same as its menu entry in apps.py', () => {
    for (const tab of CASH_REGISTER_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8').replace(/\s+/g, ' ');
    const menu = [...appsPy.matchAll(/Nav\( ?"([a-z_]+)", _\("[^"]+"\), "([^"]+)", "([^"]+)",? ?\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(CASH_REGISTER_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
