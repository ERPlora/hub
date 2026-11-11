// «Check the import» (WORKBOOK INVENTORY-F09, step 1), the old preview: one select per column of the
// file («Do not import» or the field; Name and SKU carry an asterisk), «First {n} rows of {total}»
// under the field each column goes to, the server's rehearsal of the whole file («{ready} rows
// ready · {failed} with problems» with up to ten reasons), and «Import {n} products» / «Cancel»; one
// row or product is said in the singular (hub#1124).
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
  /** The rehearsal's own sentence, without the reasons and the skipped note it holds below it. */
  const summary = () => {
    const box = el('inventory-import-summary')?.cloneNode(true) as HTMLElement | undefined;
    box?.querySelectorAll('[data-testid="inventory-import-reason"], [data-testid="inventory-import-skipped"]').forEach((child) => child.remove());
    return box?.textContent?.trim();
  };
  return { ...m, el, all, summary };
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
    expect(s.summary()).toBe('5 rows ready · 12 with problems');
    expect(s.all('inventory-import-reason')).toHaveLength(10);
    expect(s.all('inventory-import-reason')[0].textContent?.trim()).toBe('Line 2: Price is not a number');
    expect(s.el('inventory-import-skipped')?.textContent?.trim()).toBe('1 row already in the catalog will be skipped.');
    expect(s.el('inventory-import-preview-submit')?.textContent?.trim()).toBe('Import 5 products');
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
    expect(s.summary()).toBe('5 filas listas · 12 con problemas');
  });
});


// hub#1124: «row(s)» and «product(s)» are gone. One row or product reads in the singular and two in the
// plural, in both languages: the rows shown, the rows ready, the rows skipped and the import button.
describe('ImportPreviewModal: singular and plural (hub#1124, INVENTORY-F09)', () => {
  const sized = (n: number) => ({
    table: parseCsv(['Nombre;Código;Notas', ...Array.from({ length: n }, (_, i) => `P${i};S${i};n${i}`)].join('\n')),
    rehearsal: { ...READY, report: { ...READY.report, total: n + 1, ready: n, skipped: n, failed: [] } },
  });

  it.each([
    { locale: 'en' as const, n: 1, rows: 'First row of 1', summary: '1 row ready · 0 with problems', skipped: '1 row already in the catalog will be skipped.', submit: 'Import 1 product' },
    { locale: 'en' as const, n: 2, rows: 'First 2 rows of 2', summary: '2 rows ready · 0 with problems', skipped: '2 rows already in the catalog will be skipped.', submit: 'Import 2 products' },
    { locale: 'es' as const, n: 1, rows: 'Primera fila de 1', summary: '1 fila lista · 0 con problemas', skipped: '1 fila que ya está en el catálogo se omitirá.', submit: 'Importar 1 producto' },
    { locale: 'es' as const, n: 2, rows: 'Primeras 2 filas de 2', summary: '2 filas listas · 0 con problemas', skipped: '2 filas que ya están en el catálogo se omitirán.', submit: 'Importar 2 productos' },
  ])('$n ($locale): «$submit»', async ({ locale, n, rows, summary, skipped, submit }) => {
    const s = await setup(sized(n), locale);
    expect(s.el('inventory-import-rows-title')?.textContent?.trim()).toBe(rows);
    expect(s.summary()).toBe(summary);
    expect(s.el('inventory-import-skipped')?.textContent?.trim()).toBe(skipped);
    expect(s.el('inventory-import-preview-submit')?.textContent?.trim()).toBe(submit);
  });
});

describe('ImportPreviewModal: Android Back with unsaved changes (hub#1046, BASE-F05)', () => {
  it('as opened closes; a change asks; restored as opened closes again', async () => {
    const s = await setup();
    const { expectUnsavedFormOnAndroidBack } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormOnAndroidBack({
      overlay: () => s.el('inventory-import-preview'),
      change: async () => {
        await s.wrapper.setProps({ mapping: ['name', 'sku', 'description'] });
        await flush();
      },
      restore: async () => {
        await s.wrapper.setProps({ mapping: ['name', 'sku', ''] });
        await flush();
      },
    });
  });
});
