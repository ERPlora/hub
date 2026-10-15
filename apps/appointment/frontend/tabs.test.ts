// The sections of Appointments: the Agenda, plus «Settings» — the tab the old shell generated from the
// module's settings block, shown only to whoever may save them. Each tab follows its route and wears a
// registered icon; the Agenda's is the menu's.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { APPOINTMENT_TABS, appointmentTabs } from './tabs';

function tabsIn(locale: 'en' | 'es', settings = true) {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return appointmentTabs((key) => i18n.global.t(key), { settings });
}

describe('the appointment tabbar', () => {
  it('is Agenda and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['agenda', 'Agenda', '/appointment/agenda'],
      ['settings', 'Settings', '/appointment/settings'],
    ]);
  });

  it('leaves Settings out for whoever may not save them, and speaks Spanish', () => {
    expect(tabsIn('en', false).map((t) => t.id)).toEqual(['agenda']);
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Agenda', 'Ajustes']);
  });

  it('gives every tab a registered icon, the Agenda the menu’s', () => {
    for (const tab of APPOINTMENT_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
    const appsPy = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'apps.py'), 'utf8');
    expect(appsPy).toMatch(new RegExp(`"${APPOINTMENT_TABS[0].icon}",\\s*"${APPOINTMENT_TABS[0].to}"`));
  });
});
