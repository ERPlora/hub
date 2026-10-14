// «Check the import» (WORKBOOK INVENTORY-F09, step 1), the old preview: one select per column of the
// file («Do not import» or the field; Name and SKU carry an asterisk), «First {n} rows of {total}»
// under the field each column goes to, the server's rehearsal of the whole file («{ready} row(s)
// ready · {failed} with problems» with up to ten reasons), and «Import {n} product(s)» / «Cancel».
// Without Name and SKU mapped it says so and cannot import.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import { parseCsv } from '../lib/csv';
import { emptyReport } from '../lib/import-report';
import ImportPreviewModal from './ImportPreviewModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; disabled?: boolean; label?: string };

const TABLE = parseCsv(['Nombre;Código;Notas', ...Array.from({ length: 7 }, (_, i) => `P${i};S${i};n${i}`)].join('\n'));
const READY = {
  status: 'ready' as const,
  error: '',
  report: {
    ...emptyReport(),
    total: 7,
    ready: 5,
    skipped: 1,
    failed: Array.from({ length: 12 }, (_, i) => ({ line: i + 2, key: `S${i}`, reason: 'Price is not a number' })),
  },
};

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(ImportPreviewModal, {
    props: { open: true, table: TABLE, mapping: ['name', 'sku', ''], requiredMapped: true, rehearsal: READY, ...props },
    locale,
    attach: true,
  });
  await flush();
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  const all = (id: string) => [...document.querySelectorAll<Control>(`[data-testid="${id}"]`)];
  return { ...m, el, all };
}

describe('ImportPreviewModal', () => {
  it('one select per column with its guessed field; Name and SKU required', async () => {
    const s = await setup();
    expect(s.el('inventory-import-preview')?.getAttribute('aria-label')).toBe('Check the import');
    const selects = s.all('inventory-import-column');
    expect(selects.map((select) => [select.label, select.value])).toEqual([
      ['Nombre', 'name'],
      ['Código', 'sku'],
      ['Notas', ''],
    ]);
    const options = [...selects[0].querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim());
    expect(options.slice(0, 3)).toEqual(['Do not import', 'Name *', 'SKU *']);
    expect(options).toContain('Tax category');
  });

  it('picking a field for a column asks the importer', async () => {
    const s = await setup();
    const select = s.all('inventory-import-column')[2];
    select.value = 'description';
    select.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'description' } }));
    await flush();
    expect(s.wrapper.emitted('setMapping')).toEqual([[2, 'description']]);
  });

  it('shows the first five rows under the field of each column', async () => {
    const s = await setup();
    expect(s.el('inventory-import-rows-title')?.textContent?.trim()).toBe('First 5 rows of 7');
    const heads = [...document.querySelectorAll('[data-testid="inventory-import-preview-table"] th')].map((th) => th.textContent?.trim());
    expect(heads).toEqual(['Name', 'SKU', 'Notas']);
    expect(document.querySelectorAll('[data-testid="inventory-import-preview-table"] tbody tr')).toHaveLength(5);
  });

  it('says what the rehearsal found, with up to ten reasons and the rows already in the catalog', async () => {
    const s = await setup();
    expect(s.el('inventory-import-summary')?.textContent).toContain('5 row(s) ready · 12 with problems');
    expect(s.all('inventory-import-reason')).toHaveLength(10);
    expect(s.all('inventory-import-reason')[0].textContent?.trim()).toBe('Line 2: Price is not a number');
    expect(s.el('inventory-import-skipped')?.textContent?.trim()).toBe('1 row(s) already in the catalog will be skipped.');
    expect(s.el('inventory-import-preview-submit')?.textContent?.trim()).toBe('Import 5 product(s)');
    s.el('inventory-import-preview-submit')!.click();
    await flush();
    expect(s.wrapper.emitted('confirm')).toHaveLength(1);
  });

  it('while checking says so and cannot import; without Name and SKU says why', async () => {
    const s = await setup({ rehearsal: { status: 'checking', report: null, error: '' } });
    expect(s.el('inventory-import-checking')?.textContent?.trim()).toBe('Checking the whole file…');
    expect(s.el('inventory-import-preview-submit')?.disabled).toBe(true);
    const t = await setup({ requiredMapped: false, rehearsal: { status: 'idle', report: null, error: '' } });
    expect(t.el('inventory-import-missing')?.textContent).toContain('Map the Name and SKU columns');
    expect(t.el('inventory-import-preview-submit')?.disabled).toBe(true);
  });

  it('while the import is under way it cannot be launched again', async () => {
    const s = await setup({ pending: true });
    expect(s.el('inventory-import-preview-submit')?.disabled).toBe(true);
  });

  it('«Cancel» leaves the catalog as it was', async () => {
    const s = await setup();
    s.el('inventory-import-preview-cancel')!.click();
    await flush();
    expect(s.wrapper.emitted('cancel')).toHaveLength(1);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.el('inventory-import-preview')?.getAttribute('aria-label')).toBe('Revisa la importación');
    expect(s.el('inventory-import-summary')?.textContent).toContain('5 fila(s) listas · 12 con problemas');
  });
});
