// The six sections of VeriFactu (the old manifest's `navigation`): Records, Contingency, Events, Recovery,
// Configuration and Settings, as the footer tabbar of every VeriFactu page. Each tab follows its route, has
// its icon (a registered one: an unregistered icon paints nothing) and its label in the reader's language.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { resolveIcon } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { VERIFACTU_TABS, verifactuTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return verifactuTabs((key) => i18n.global.t(key));
}

describe('the VeriFactu tabbar', () => {
  it('is the six sections, each on its own route, the order of the menu (apps.py)', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['records', 'Records', '/verifactu/records'],
      ['contingency', 'Contingency', '/verifactu/contingency'],
      ['events', 'Events', '/verifactu/events'],
      ['recovery', 'Recovery', '/verifactu/recovery'],
      ['config', 'Configuration', '/verifactu/config'],
      ['settings', 'Settings', '/verifactu/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Registros', 'Contingencia', 'Eventos', 'Recuperación', 'Configuración', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of VERIFACTU_TABS) expect(resolveIcon(tab.icon), tab.icon).toBeTruthy();
  });

  it('wears the same icons and paths as the menu entries of apps.py', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)",?\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(VERIFACTU_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
