import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { SETTINGS_TABS, settingsTab, settingsTabsOf } from './settings-tabs';

const holding =
  (...granted: string[]) =>
  (permission: string) =>
    granted.includes(permission);

const ALL = SETTINGS_TABS.map((tab) => tab.id);

function translated(catalogue: unknown, key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], catalogue);
}

describe('the tabs of Settings', () => {
  it('are General, Business, Printing and Data, each with the permission of what it holds', () => {
    expect(SETTINGS_TABS.map(({ id, permission }) => ({ id, permission }))).toEqual([
      { id: 'general', permission: 'base.view_home' },
      { id: 'business', permission: 'base.view_home' },
      // It leads to the Printing app's printers, set up by whoever manages Printing.
      { id: 'tickets', permission: 'printing.manage_settings' },
      // Import, export and reset are for whoever runs the business.
      { id: 'data', permission: 'base.administer_hub' },
    ]);
  });

  it('name themselves in English and Spanish', () => {
    for (const tab of SETTINGS_TABS) {
      expect(typeof translated(en, tab.labelKey), `${tab.id} en`).toBe('string');
      expect(typeof translated(es, tab.labelKey), `${tab.id} es`).toBe('string');
    }
  });

  it('a person has only the ones whose permission they hold, in their order', () => {
    expect(settingsTabsOf(holding('base.view_home')).map((tab) => tab.id)).toEqual(['general', 'business']);
    expect(settingsTabsOf(holding('base.view_home', 'printing.manage_settings')).map((tab) => tab.id)).toEqual([
      'general',
      'business',
      'tickets',
    ]);
    expect(settingsTabsOf(holding('base.view_home', 'base.administer_hub', 'printing.manage_settings')).map((tab) => tab.id)).toEqual(ALL);
    expect(settingsTabsOf(holding())).toEqual([]);
  });
});

describe('the address of Settings', () => {
  it('opens the tab the hash names, older addresses included', () => {
    expect(settingsTab('#data', ALL)).toBe('data');
    expect(settingsTab('#general', ALL)).toBe('general');
    expect(settingsTab('#business', ALL)).toBe('business');
    expect(settingsTab('#tickets', ALL)).toBe('tickets');
    // Published versions of VeriFactu still link `#tax`: it was the business's own tab.
    expect(settingsTab('#tax', ALL)).toBe('business');
    // General used to be `#hub`.
    expect(settingsTab('#hub', ALL)).toBe('general');
  });

  it('opens the first tab, «General», without a hash or with one it does not have (`#store`, `#permissions`)', () => {
    for (const hash of ['', '#store', '#permissions', '#nonsense']) {
      expect(settingsTab(hash, ALL), hash).toBe('general');
    }
  });

  it('opens the first of the person’s tabs for one they do not have, never the one they do not have', () => {
    expect(settingsTab('#data', ['general', 'business'])).toBe('general');
    expect(settingsTab('#tickets', ['general', 'business'])).toBe('general');
    expect(settingsTab('#tax', ['general'])).toBe('general');
    expect(settingsTab('#business', ['business'])).toBe('business');
  });

  it('opens none when the person has no tab', () => {
    expect(settingsTab('#general', [])).toBeUndefined();
  });
});
