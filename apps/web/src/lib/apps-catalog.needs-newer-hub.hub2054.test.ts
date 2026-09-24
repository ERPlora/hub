// hub#2054 — a catalog card for an app that needs a newer hub still said «Available» with a live
// «Install» button. The owner pressed it, picked a version, and only THEN was told the hub was too
// old (the runtime's `core_version_too_old`, hub#1620). The store has to say it before the press, the
// way Shopify and Odoo do with an app's minimum version.
//
// The floor comes from the catalog (saas#2239): each row of `GET /api/v1/marketplace/modules/`
// carries `min_erplora_version` = the floor of the version THAT row announces for this hub's lane,
// `null` when that version declares none. It is additive: a SaaS older than the field omits it.
import { describe, expect, it } from 'vitest';

import { catalogActionFor, catalogRowState, catalogVisibleAction, hubTooOldFor } from './apps-catalog';
import { normalizeMarketplaceModule } from './cloud';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

describe('normalizeMarketplaceModule reads the floor of the announced version', () => {
  it('keeps the floor the catalog sent', () => {
    expect(normalizeMarketplaceModule({ module_id: 'sales', min_erplora_version: '9.9.9' }).minErploraVersion).toBe('9.9.9');
  });

  it('reads silence, null and an empty string as «declares no floor»', () => {
    // A SaaS older than saas#2239 sends nothing; `null` is the contract's «no floor».
    expect(normalizeMarketplaceModule({ module_id: 'sales' }).minErploraVersion).toBe(null);
    expect(normalizeMarketplaceModule({ module_id: 'sales', min_erplora_version: null }).minErploraVersion).toBe(null);
    expect(normalizeMarketplaceModule({ module_id: 'sales', min_erplora_version: '  ' }).minErploraVersion).toBe(null);
  });
});

describe('hubTooOldFor — the same comparison the runtime refuses with', () => {
  it('is too old when the hub is below the floor', () => {
    expect(hubTooOldFor('9.9.9', 'v1.4.0')).toBe(true);
    expect(hubTooOldFor('1.4.1', '1.4.0')).toBe(true);
    expect(hubTooOldFor('2', 'v1.99.99')).toBe(true);
  });

  it('is not too old at or above the floor', () => {
    expect(hubTooOldFor('1.4.0', 'v1.4.0')).toBe(false);
    expect(hubTooOldFor('1.3.9', 'v1.4.0')).toBe(false);
  });

  it('drops a prerelease/build suffix like the runtime does (a :dev build of 1.1.7 floors at 1.1.7)', () => {
    expect(hubTooOldFor('1.1.7', '1.1.7-dev.305+g1c50d429')).toBe(false);
    expect(hubTooOldFor('1.1.7-rc1', 'v1.1.7')).toBe(false);
  });

  it('never blocks on what it cannot check — the runtime still refuses at install time', () => {
    // No floor, an unknown hub version (the system endpoint did not answer) or a shape nobody
    // released: painting «needs a newer hub» on a guess would lock the owner out of a good app.
    expect(hubTooOldFor(null, 'v1.4.0')).toBe(false);
    expect(hubTooOldFor('9.9.9', null)).toBe(false);
    expect(hubTooOldFor('9.9.9', 'garbage')).toBe(false);
    expect(hubTooOldFor('latest', 'v1.4.0')).toBe(false);
  });
});

describe('catalogRowState with a floor above this hub', () => {
  const base = {
    cloudInstalled: false, id: 'sales', localInstalledIds: new Set<string>(), hasUpdate: false,
    available: true, busy: false, needsNewerHub: true,
  };

  it('is needs_newer_hub instead of available, and offers no install', () => {
    expect(catalogRowState(base)).toBe('needs_newer_hub');
    expect(catalogActionFor('needs_newer_hub')).toBe('see_hub_updates');
    expect(catalogVisibleAction('needs_newer_hub', null)).toBe('see_hub_updates');
  });

  it('stays available when the hub meets the floor', () => {
    expect(catalogRowState({ ...base, needsNewerHub: false })).toBe('available');
  });

  it('does not touch what this hub already has, nor a row that is busy or not offered', () => {
    // The floor belongs to the version the catalog announces for a NEW install; an installed module
    // keeps running whatever the catalog's newest version needs.
    expect(catalogRowState({ ...base, localInstalledIds: new Set(['sales']) })).toBe('installed');
    expect(catalogRowState({ ...base, busy: true })).toBe('installing');
    expect(catalogRowState({ ...base, available: false })).toBe('unavailable');
  });
});

describe('the card says it in the owner language', () => {
  it('names the required version in en and es', () => {
    expect(en.apps.stateNeedsNewerHub).toContain('{version}');
    expect(es.apps.stateNeedsNewerHub).toContain('{version}');
    expect(en.apps.actionSeeHubUpdates).toBeTruthy();
    expect(es.apps.actionSeeHubUpdates).toBeTruthy();
    expect(es.apps.stateNeedsNewerHub).not.toBe(en.apps.stateNeedsNewerHub);
  });
});
