// Settings › Data › Export (BASE-G101, BASE-G102): only for who administers the hub. The name (the business's to
// start), the language and the file's final name; «Backup of this business» or «Template to share»; the apps on with
// «App» (registered) and «Data» (its data travels) and, under a marked «Data», one box per table with its rows —
// personal data only in a backup —; «Select all» / «Deselect all»; «Export» saves the file and says so.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, flush, mountBase } from '../../__tests__/mount-base';
import type { AppDatasets } from '../../operations';
import ExportPanel from './ExportPanel.vue';

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

const FILE = { filename: 'bar-pepe_en.blueprint.zip', content_type: 'application/zip', content_base64: 'UEsDBA==' };

let clicked: string[] = [];

beforeEach(() => {
  clicked = [];
  document.head.innerHTML = `<script id="hub-home" type="application/json">${JSON.stringify({ name: 'Bar Pepe' })}</script>`;
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push(this.download);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

async function settle() {
  for (let i = 0; i < 4; i += 1) await flush();
}

async function panel(answer: (url: string) => Response = (url) => (url.includes('/datasets') ? Response.json({ apps: APPS }) : Response.json(FILE))) {
  const urls: string[] = [];
  const m = await mountBase(ExportPanel, {
    path: '/settings?data=export#data',
    routes: ['/settings'],
    onApi: ({ url }) => {
      urls.push(url);
      return answer(url);
    },
  });
  await settle();
  return { ...m, urls };
}

const box = (m: Awaited<ReturnType<typeof panel>>, testid: string) =>
  m.wrapper.get(`[data-testid="${testid}"]`).element as HTMLElement & { checked?: boolean; disabled?: boolean };

async function change(m: Awaited<ReturnType<typeof panel>>, testid: string, detail: Record<string, unknown>) {
  m.wrapper.get(`[data-testid="${testid}"]`).element.dispatchEvent(new CustomEvent('ionChange', { detail }));
  await settle();
}

const exportQuery = (m: Awaited<ReturnType<typeof panel>>) =>
  new URL(m.urls.filter((url) => url.startsWith('/api/settings/data/export')).at(-1) ?? '', 'http://a.localhost').searchParams;

describe('ExportPanel', () => {
  it('to a person who does not administer the hub, says only an administrator can, and asks nothing', async () => {
    const urls: string[] = [];
    const m = await mountBase(ExportPanel, { session: EMPLOYEE, onApi: ({ url }) => (urls.push(url), Response.json({})) });
    await settle();
    expect(m.wrapper.text()).toContain('Only an administrator can export the business.');
    expect(urls).toEqual([]);
  });

  it('starts with the business\'s name, the page\'s language and the final file name; a backup by default', async () => {
    const m = await panel();
    expect((m.wrapper.get('[data-testid="export-name"]').element as HTMLElement & { value?: string }).value).toBe('Bar Pepe');
    expect(m.wrapper.get('[data-testid="export-file-name"]').text()).toBe('File: bar-pepe_en.blueprint.zip');
    expect((m.wrapper.get('[data-testid="export-purpose"]').element as HTMLElement & { value?: string }).value).toBe('backup');
  });

  it('lists the apps on: every one registered, none with its data; an app with nothing to copy says so', async () => {
    const m = await panel();
    expect(m.wrapper.findAll('[data-testid="export-app"]').map((row) => row.attributes('data-id'))).toEqual(['inventory', 'customer', 'kitchen']);
    expect([box(m, 'export-app-inventory').checked, box(m, 'export-data-inventory').checked]).toEqual([true, false]);
    expect(box(m, 'export-data-kitchen').disabled).toBe(true);
    expect(m.wrapper.get('[data-id="kitchen"]').text()).toContain('Nothing of its own to copy');
  });

  it('exports what was ticked, saves the file and says so', async () => {
    const m = await panel();
    await change(m, 'export-data-inventory', { checked: true });
    expect(m.wrapper.get('[data-testid="export-tables-inventory"]').text()).toContain('Products · 12');
    await change(m, 'export-table-inventory.category', { checked: false });
    await change(m, 'export-app-kitchen', { checked: false });
    await m.wrapper.get('[data-testid="export-submit"]').trigger('click');
    await settle();
    const query = exportQuery(m);
    expect(query.get('name')).toBe('Bar Pepe');
    expect(query.get('language')).toBe('en');
    expect(query.get('purpose')).toBe('backup');
    expect(query.getAll('apps')).toEqual(['inventory', 'customer']);
    expect(query.getAll('data')).toEqual(['inventory']);
    expect(query.getAll('datasets')).toEqual(['inventory.product']);
    expect(clicked).toEqual(['bar-pepe_en.blueprint.zip']);
    expect(m.wrapper.get('[data-testid="export-done"]').text()).toContain('bar-pepe_en.blueprint.zip downloaded.');
  });

  it('a template never takes personal data: its tables cannot be marked and say why', async () => {
    const m = await panel();
    await change(m, 'export-purpose', { value: 'template' });
    await change(m, 'export-data-customer', { checked: true });
    expect(box(m, 'export-table-customer.customer').disabled).toBe(true);
    expect(m.wrapper.get('[data-testid="export-tables-customer"]').text()).toContain('Only in a backup');
  });

  it('«Select all» marks every app and its data; «Deselect all» leaves none, and then there is nothing to export', async () => {
    const m = await panel();
    await m.wrapper.get('[data-testid="export-select-all"]').trigger('click');
    await settle();
    expect([box(m, 'export-data-inventory').checked, box(m, 'export-data-customer').checked]).toEqual([true, true]);
    await m.wrapper.get('[data-testid="export-deselect-all"]').trigger('click');
    await settle();
    expect(box(m, 'export-app-inventory').checked).toBe(false);
    expect(box(m, 'export-submit').disabled).toBe(true);
  });

  it('cannot export without a name, and says so', async () => {
    const m = await panel();
    m.wrapper.get('[data-testid="export-name"]').element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: '  ' } }));
    await settle();
    expect(box(m, 'export-submit').disabled).toBe(true);
    expect(m.wrapper.text()).toContain('Write a name for the file.');
  });

  it('says why an export failed', async () => {
    const m = await panel((url) =>
      url.includes('/datasets')
        ? Response.json({ apps: APPS })
        : Response.json({ error: { code: 'invalid_payload', message: 'The app «x» is not on in this business.' } }, { status: 422 }),
    );
    await m.wrapper.get('[data-testid="export-submit"]').trigger('click');
    await settle();
    expect(m.wrapper.get('[data-testid="export-error"]').text()).toContain('The export failed: The app «x» is not on in this business.');
    expect(clicked).toEqual([]);
  });

  it('says when the apps could not be read, and reads them again', async () => {
    let fail = true;
    const m = await panel(() => (fail ? Response.json({ error: { code: 'internal', message: 'down' } }, { status: 500 }) : Response.json({ apps: APPS })));
    expect(m.wrapper.text()).toContain('The apps of this business could not be loaded.');
    fail = false;
    await m.wrapper.get('[data-testid="export-retry"]').trigger('click');
    await settle();
    expect(m.wrapper.findAll('[data-testid="export-app"]')).toHaveLength(3);
  });
});
