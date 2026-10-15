// The sections of Reservations (WORKBOOK «Pantallas»; the old manifest's `navigation`): Reservations,
// Waitlist and Availability, as the footer tabbar of every reservation page, plus «Settings», shown only
// to whoever may save them. Each tab follows its route and wears a registered icon, the same as the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { RESERVATION_TABS, reservationTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return reservationTabs((key) => i18n.global.t(key), { settings });
}

describe('the reservations tabbar', () => {
  it('is Reservations, Waitlist, Availability and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['reservations', 'Reservations', '/reservation/reservations'],
      ['waitlist', 'Waitlist', '/reservation/waitlist'],
      ['availability', 'Availability', '/reservation/availability'],
      ['settings', 'Settings', '/reservation/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['reservations', 'waitlist', 'availability']);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Reservas', 'Lista de espera', 'Disponibilidad', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of RESERVATION_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py (one icon per section everywhere)', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    const menu = [...appsPy.matchAll(/Nav\(\s*"([a-z_]+)",\s*_\("[^"]+"\),\s*"([^"]+)",\s*"([^"]+)",?\s*\)/g)].map((m) => [m[1], m[2], m[3]]);
    expect(menu).toEqual(RESERVATION_TABS.filter((tab) => tab.id !== 'settings').map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
