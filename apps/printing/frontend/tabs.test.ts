// The four sections of Printing (the old single «Printers» screen split as the platform's apps do), as
// the footer tabbar of every page: each tab follows its route, has a registered icon and its label in the
// reader's language, and wears the same icon and path as its menu entry in apps.py.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { resolveIcon } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { PRINTING_TABS, printingTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return printingTabs((key) => i18n.global.t(key));
}

describe('the printing tabbar', () => {
  it('is the printers, the devices that print, the queue and the settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['printers', 'Printers', '/printing/printers'],
      ['devices', 'Devices', '/printing/devices'],
      ['jobs', 'Queue', '/printing/jobs'],
      ['settings', 'Settings', '/printing/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Impresoras', 'Dispositivos', 'Cola', 'Ajustes']);
  });

  it('gives every tab a registered icon, the same as its menu entry in apps.py', () => {
    for (const tab of PRINTING_TABS) expect(resolveIcon(tab.icon), tab.icon).toBeTruthy();
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8').replace(/\s+/g, ' ');
    const menu = [...appsPy.matchAll(/Nav\( ?"([a-z_]+)", _\("[^"]+"\), "([^"]+)", "([^"]+)",? ?\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(PRINTING_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
