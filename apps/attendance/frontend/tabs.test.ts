// The sections of the Time clock (the WORKBOOK's screens; the old manifest's `navigation` plus its
// settings tab): Clock in, Records and Settings, as the footer tabbar of every attendance page. Each tab
// follows its route, has a registered icon (an unregistered one paints nothing) and its label in the
// reader's language. Settings is for everyone: whoever may not save reads it.

import { createShellI18n } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { appMenu } from '../../../base/frontend/__tests__/app-menu';
import { ION_ICONS } from '../../../packages/ui/src/shell/icons';
import en from './locale/en.json';
import es from './locale/es.json';
import { ATTENDANCE_TABS, attendanceTabs } from './tabs';

function tabsIn(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  return attendanceTabs((key) => i18n.global.t(key));
}

describe('the attendance tabbar', () => {
  it('is Clock in, Records and Settings, each on its own route', () => {
    expect(tabsIn('en').map((t) => [t.id, t.label, t.to])).toEqual([
      ['clock', 'Clock in', '/attendance/clock'],
      ['records', 'Records', '/attendance/records'],
      ['settings', 'Settings', '/attendance/settings'],
    ]);
  });

  it('speaks Spanish', () => {
    expect(tabsIn('es').map((t) => t.label)).toEqual(['Fichar', 'Registros', 'Ajustes']);
  });

  it('gives every tab a registered icon', () => {
    for (const tab of ATTENDANCE_TABS) expect(Object.hasOwn(ION_ICONS, tab.icon.replace(/^ion:/, '')), tab.icon).toBe(true);
  });

  it('wears the same icons and paths as the menu entries of apps.py', () => {
    const menu = appMenu('attendance');
    expect(menu.map((entry) => [entry.id, entry.icon, entry.path])).toEqual(ATTENDANCE_TABS.map((tab) => [tab.id, tab.icon, tab.to]));
  });
});
