// The sections of Online booking, as the old module's menu: «Bookings» (the inbox) and «Settings», this one
// only for whoever may save them. Each tab follows its route and wears the registered icon of its menu entry.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { ONLINE_BOOKING_TABS, onlineBookingTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return onlineBookingTabs((key) => i18n.global.t(key), { settings });
}

describe('the online booking tabbar', () => {
  it('is Bookings and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['bookings', 'Bookings', '/online_booking/bookings'],
      ['settings', 'Settings', '/online_booking/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them, and speaks Spanish', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['bookings']);
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Reservas', 'Ajustes']);
  });

  it('gives every tab the registered icon of its menu entry in apps.py', () => {
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    for (const tab of ONLINE_BOOKING_TABS) {
      expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
      expect(appsPy).toMatch(new RegExp(`"${tab.icon}",\\s*"${tab.to}"`));
    }
  });
});
