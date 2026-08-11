// hub#488 — the import report named apps by their manifest id.
//
// «Estas hay que añadirlas antes a tu plan: invoice, cash_register» is a sentence a restaurant owner
// is supposed to ACT on, and `cash_register` is not a word he ever chose: it is a key of our
// manifest. In the marketplace he would be looking for that same app under its translated name.
// Same defect ADR-0254 (hub#365) took out of the login → till path, still sitting on the first
// screen a new business sees.
//
// The name is resolved when the report is PAINTED, never baked into it: the id is the stable key
// (undo, retry, install) and a name frozen into a report goes stale and is stuck in whoever ran the
// import's language — and since hub#763 that report is persisted and re-read later.
import { beforeEach, describe, expect, it, vi } from 'vitest';

const listInstalledModules = vi.fn();
const cloudMarketplaceModules = vi.fn();

vi.mock('./runtime', () => ({ listInstalledModules: () => listInstalledModules() }));
vi.mock('./cloud', () => ({ cloudMarketplaceModules: () => cloudMarketplaceModules() }));

import { appLabel, loadAppNames } from './app-names';

beforeEach(() => {
  listInstalledModules.mockReset().mockResolvedValue([]);
  cloudMarketplaceModules.mockReset().mockResolvedValue([]);
});

describe('appLabel — the app is named the way the owner knows it (hub#488)', () => {
  it('uses the human name when there is one', () => {
    expect(appLabel('cash_register', new Map([['cash_register', 'Caja']]))).toBe('Caja');
  });

  it('falls back to the id verbatim, never to an invention', () => {
    // A made-up prettified name («Cash Register») would be worse than the id: it is not what the
    // marketplace calls it either, so the owner would search for a name nobody uses.
    expect(appLabel('cash_register', new Map())).toBe('cash_register');
  });
});

describe('loadAppNames — where the names come from (hub#488)', () => {
  it('takes installed apps from the runtime, which already localises them (ADR-0055)', async () => {
    listInstalledModules.mockResolvedValue([{ id: 'inventory', name: 'Inventario' }]);

    expect((await loadAppNames()).get('inventory')).toBe('Inventario');
  });

  it('covers an app that is NOT installed — the blocked case the report is about', async () => {
    // A module blocked on the plan was never installed, so the runtime knows nothing about it.
    // Without the marketplace this is exactly the row that would keep showing a raw id.
    cloudMarketplaceModules.mockResolvedValue([{ id: 'invoice', name: 'Facturación' }]);

    expect((await loadAppNames()).get('invoice')).toBe('Facturación');
  });

  it('prefers what the hub itself installed over the catalogue', async () => {
    // Both know the app: the local one is the version this business actually runs.
    listInstalledModules.mockResolvedValue([{ id: 'pos', name: 'TPV' }]);
    cloudMarketplaceModules.mockResolvedValue([{ id: 'pos', name: 'Point of sale' }]);

    expect((await loadAppNames()).get('pos')).toBe('TPV');
  });

  it('a cloud it cannot reach costs names, never the report', async () => {
    // The report is the whole point of the screen; a local hub with no cloud still shows it, with
    // ids where a name was missing.
    listInstalledModules.mockResolvedValue([{ id: 'inventory', name: 'Inventario' }]);
    cloudMarketplaceModules.mockRejectedValue(new Error('offline'));

    const names = await loadAppNames();
    expect(names.get('inventory')).toBe('Inventario');
    expect(appLabel('invoice', names)).toBe('invoice');
  });

  it('a runtime that will not answer is survivable too', async () => {
    listInstalledModules.mockRejectedValue(new Error('runtime restarting'));
    cloudMarketplaceModules.mockResolvedValue([{ id: 'invoice', name: 'Facturación' }]);

    expect((await loadAppNames()).get('invoice')).toBe('Facturación');
  });

  it('an empty name is not a name: the id wins', async () => {
    // The catalogue serialises a missing name as '', and painting '' would leave the row blank —
    // strictly worse than the id it was meant to replace.
    cloudMarketplaceModules.mockResolvedValue([{ id: 'invoice', name: '' }]);

    expect(appLabel('invoice', await loadAppNames())).toBe('invoice');
  });
});
