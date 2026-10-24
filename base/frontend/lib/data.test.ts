// The rules of Settings › Data that are not the server's (the old hub's `ExportPanel.vue`, `import-retry.ts`,
// `data-table-labels.ts` and `blueprint-hero.ts`): pure, so each one is pinned here once.
import { describe, expect, it } from 'vitest';

import en from '../locale/en.json';
import type { AppDatasets, ImportRow, LoadReport, Template } from '../operations';
import {
  base64ToBlob,
  bytesToBase64,
  cardOutcome,
  cardTemplates,
  dataSection,
  defaultExportName,
  exportFileName,
  exportInput,
  freshExportChoice,
  MAX_FILE_BYTES,
  RETRY_BLOCKED_KEY,
  selectAll,
  settingsTab,
  STATUS_KEY,
  statusPill,
  templateMatches,
  toggleApp,
  toggleData,
  toggleDataset,
  unloaded,
} from './data';

function lookup(key: string): unknown {
  return key.split('.').reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], en);
}

const APPS: AppDatasets[] = [
  {
    id: 'inventory',
    label: 'Inventory',
    icon: 'ion:cube-outline',
    datasets: [
      { key: 'inventory.category', label: 'Categories', rows: 2, personal: false },
      { key: 'inventory.product', label: 'Products', rows: 12, personal: false },
    ],
  },
  { id: 'customer', label: 'Customers', icon: 'ion:people-outline', datasets: [{ key: 'customer.customer', label: 'Customers', rows: 3, personal: true }] },
  { id: 'kitchen', label: 'Kitchen', icon: 'ion:flame-outline', datasets: [] },
];

function template(key: string, fields: Partial<Template> = {}): Template {
  return {
    key,
    name: `Name ${key}`,
    description: `About ${key}`,
    language: 'es',
    country: 'ES',
    vertical: key.split('.')[0],
    version: '1',
    apps: [],
    contents: [],
    ...fields,
  };
}

function load(fields: Partial<ImportRow> = {}): ImportRow {
  return {
    id: 'l1',
    name: 'Restaurant',
    source: 'catalog',
    template_key: 'restaurant.es',
    status: 'complete',
    created_at: '2026-10-24T08:00:00Z',
    created_by: 'Ana',
    rows: 10,
    undone: false,
    undoable: true,
    retry: false,
    retry_blocked: 'complete',
    report: { status: 'complete', apps: [], dropped: [] },
    ...fields,
  };
}

describe('the address of Settings', () => {
  it('opens the only tab there is, whatever the hash says (old links to #hub or #tax land on it too)', () => {
    expect(settingsTab('#data')).toBe('data');
    expect(settingsTab('')).toBe('data');
    expect(settingsTab('#tax')).toBe('data');
  });

  it('opens Import unless `?data=` names another section', () => {
    expect(dataSection(undefined)).toBe('import');
    expect(dataSection('export')).toBe('export');
    expect(dataSection('reset')).toBe('reset');
    expect(dataSection('nonsense')).toBe('import');
    expect(dataSection(['export', 'reset'])).toBe('export');
  });
});

describe('the export (BASE-G101, BASE-G102)', () => {
  it('names the file as the server does: «{name}_{language}.blueprint.zip», safe for any disk', () => {
    expect(exportFileName('Bar Pepe', 'es')).toBe('bar-pepe_es.blueprint.zip');
    expect(exportFileName('  Peluquería  Ñandú! ', 'es')).toBe('peluqueria-nandu_es.blueprint.zip');
    expect(exportFileName('???', '')).toBe('blueprint_xx.blueprint.zip');
  });

  it("names the file after the business, or the hub's address while it has no name", () => {
    expect(defaultExportName('Bar Pepe', 'bar-pepe.erplora.com')).toBe('Bar Pepe');
    expect(defaultExportName('  ', 'bar-pepe.erplora.com')).toBe('bar-pepe');
    expect(defaultExportName(undefined, 'a.localhost')).toBe('a');
    expect(defaultExportName(undefined, '')).toBe('');
  });

  it('starts with every app registered and no data, as the old hub', () => {
    const choice = freshExportChoice(APPS);
    expect(exportInput(choice, APPS, { name: 'Bar', language: 'es', purpose: 'backup' })).toEqual({
      name: 'Bar',
      language: 'es',
      purpose: 'backup',
      apps: ['inventory', 'customer', 'kitchen'],
      data: [],
      datasets: [],
    });
  });

  it('takes an app\'s data only with the app: unmarking the app unmarks its data', () => {
    let choice = toggleData(freshExportChoice(APPS), 'inventory', true);
    choice = toggleApp(choice, 'inventory', false);
    const input = exportInput(choice, APPS, { name: 'Bar', language: 'es', purpose: 'backup' });
    expect(input.apps).toEqual(['customer', 'kitchen']);
    expect(input.data).toEqual([]);
    // Marking the data of an unregistered app does nothing.
    expect(exportInput(toggleData(choice, 'inventory', true), APPS, { name: 'B', language: 'es', purpose: 'backup' }).data).toEqual([]);
    // Its «Data» box is unticked too: ticking the app again does not bring its data back.
    expect(choice.data.has('inventory')).toBe(false);
    expect(exportInput(toggleApp(choice, 'inventory', true), APPS, { name: 'B', language: 'es', purpose: 'backup' }).data).toEqual([]);
  });

  it('sends «all» (no dataset named) while no table is unmarked, so a new one never stays out unseen', () => {
    const choice = toggleData(freshExportChoice(APPS), 'inventory', true);
    expect(exportInput(choice, APPS, { name: 'B', language: 'es', purpose: 'backup' })).toMatchObject({
      data: ['inventory'],
      datasets: [],
    });
  });

  it('names the tables left of an app once one of them is unmarked; with none left, its data stays home', () => {
    let choice = toggleData(freshExportChoice(APPS), 'inventory', true);
    choice = toggleDataset(choice, 'inventory.category', false);
    expect(exportInput(choice, APPS, { name: 'B', language: 'es', purpose: 'backup' })).toMatchObject({
      data: ['inventory'],
      datasets: ['inventory.product'],
    });
    choice = toggleDataset(choice, 'inventory.product', false);
    expect(exportInput(choice, APPS, { name: 'B', language: 'es', purpose: 'backup' })).toMatchObject({
      data: [],
      datasets: [],
    });
  });

  it('never asks for personal data in a template, nor the data of an app with nothing to copy', () => {
    let choice = selectAll(APPS, true);
    const template = exportInput(choice, APPS, { name: 'B', language: 'es', purpose: 'template' });
    expect(template.data).toEqual(['inventory']);
    const backup = exportInput(choice, APPS, { name: 'B', language: 'es', purpose: 'backup' });
    expect(backup.data).toEqual(['inventory', 'customer']);
    choice = selectAll(APPS, false);
    expect(exportInput(choice, APPS, { name: 'B', language: 'es', purpose: 'backup' })).toMatchObject({ apps: [], data: [] });
  });

  it('turns the file the server wrote into bytes to save', async () => {
    const blob = base64ToBlob(bytesToBase64(new Uint8Array([80, 75, 3, 4, 255])), 'application/zip');
    expect(blob.type).toBe('application/zip');
    expect([...new Uint8Array(await blob.arrayBuffer())]).toEqual([80, 75, 3, 4, 255]);
  });
});

describe('the import (BASE-G103–G107)', () => {
  it('reads a file in base64, in chunks, whatever its size', () => {
    const bytes = new Uint8Array(100_000).map((_, i) => i % 256);
    expect(bytesToBase64(bytes)).toBe(Buffer.from(bytes).toString('base64'));
    expect(MAX_FILE_BYTES).toBe(5 * 1024 * 1024);
  });

  it('finds a template by its name, description or apps, without minding case or accents', () => {
    const salon = template('hair_salon.es', { name: 'Peluquería', apps: [{ id: 'appointment', label: 'Citas' }] });
    expect(templateMatches(salon, '')).toBe(true);
    expect(templateMatches(salon, 'PELUQUERIA')).toBe(true);
    expect(templateMatches(salon, 'citas')).toBe(true);
    expect(templateMatches(salon, 'pizza')).toBe(false);
  });

  it('paints every status in words and tone; one it does not know as failed, with its own text (never a success)', () => {
    expect(statusPill('applied')).toEqual({ tone: 'success', key: 'base.data.status.applied' });
    expect(statusPill('already')).toEqual({ tone: 'neutral', key: 'base.data.status.already' });
    expect(statusPill('partial')).toEqual({ tone: 'warning', key: 'base.data.status.partial' });
    expect(statusPill('failed')).toEqual({ tone: 'danger', key: 'base.data.status.failed' });
    expect(statusPill('exploded')).toEqual({ tone: 'danger', key: 'base.data.status.failed', raw: 'exploded' });
  });

  it('has a sentence for every status and every reason a load cannot be retried', () => {
    for (const key of [...Object.values(STATUS_KEY), ...Object.values(RETRY_BLOCKED_KEY)]) expect(typeof lookup(key), key).toBe('string');
  });

  it('lists the apps of a report that did not go in, by name', () => {
    const report: LoadReport = {
      status: 'partial',
      dropped: [],
      apps: [
        { id: 'inventory', label: 'Inventory', status: 'applied', datasets: [] },
        { id: 'table', label: 'Tables', status: 'partial', datasets: [] },
        { id: 'service', label: 'Services', status: 'failed', datasets: [] },
        { id: 'customer', label: 'Customers', status: 'discarded', datasets: [] },
        { id: 'kitchen', label: 'Kitchen', status: 'already', datasets: [] },
      ],
    };
    expect(unloaded(report)).toEqual(['Tables', 'Services']);
  });
});

describe('the templates card of the Home (BASE-G131, BASE-F02)', () => {
  it('offers at most four, in the order the catalogue gives (the hub\'s country, then the language)', () => {
    const list = ['a.es', 'b.es', 'c.es', 'd.es', 'e.es'].map((key) => template(key));
    expect(cardTemplates(list).map((t) => t.key)).toEqual(['a.es', 'b.es', 'c.es', 'd.es']);
  });

  it('offers one template per kind of business: the first the catalogue gives, in the person\'s language', () => {
    // A Spanish owner would otherwise read «Restaurante» and «Restaurant» as two different businesses.
    const list = ['restaurant.es', 'hair_salon.es', 'restaurant.en', 'hair_salon.en', 'bakery.en'].map((key) => template(key));
    expect(cardTemplates(list).map((t) => t.key)).toEqual(['restaurant.es', 'hair_salon.es', 'bakery.en']);
  });

  it('says how a load from the card went: ready, partial with what did not go in, or not started', () => {
    expect(cardOutcome(load())).toEqual({ kind: 'ready', missing: [] });
    const partial = load({
      status: 'partial',
      report: { status: 'partial', dropped: [], apps: [{ id: 'table', label: 'Tables', status: 'failed', datasets: [] }] },
    });
    expect(cardOutcome(partial)).toEqual({ kind: 'partial', missing: ['Tables'] });
    expect(cardOutcome(load({ status: 'failed', report: { status: 'failed', dropped: [], apps: [] } }))).toEqual({
      kind: 'failed',
      missing: [],
    });
  });
});
