// Inventory → Categories (WORKBOOK «Categorías», INVENTORY-F06/F07/F10/F11): the live
// `inventory.category.list` — Name, Slug and Products (active ones) —, «Search category…», 25 a page,
// sorted by name. «+», a row or «Edit» open the form; «Delete» confirms «Delete category» with what
// will happen and «Delete and unlink»; import and export CSV. Whoever cannot change categories sees
// the list only. A refused row action is said above the table.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { category, EMPLOYEE, errorFrame, flush, type MountOptions, mountInventory, ok, page, refusal, subId } from '../__tests__/mount-inventory';
import CategoryFormModal from '../components/CategoryFormModal.vue';
import CsvButtons from '../components/CsvButtons.vue';
import ImportReportModal from '../components/ImportReportModal.vue';
import CategoriesPage from './CategoriesPage.vue';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), save: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('../lib/download', () => ({ saveTextFile: mocks.save }));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  mocks.confirm.mockReset();
  mocks.save.mockReset();
  document.body.innerHTML = '';
});

const LIST = page([category(), category({ id: 'c2', name: 'Food', slug: 'food', product_count: 0 })], 2, 25);

async function setup(options: MountOptions = {}) {
  const m = await mountInventory(CategoriesPage, { path: '/inventory/categories', ...options });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="inventory-categories-row"]');
  const form = () => m.wrapper.findComponent(CategoryFormModal);
  async function act(actionId: string, row = LIST.rows[0]) {
    table().vm.$emit('action', { actionId, row });
    await flush();
  }
  return { ...m, call, testid, table, prop, rows, form, act, show: (data: unknown, rev?: number) => m.result(call, 'inventory.category.list', data, rev) };
}

describe('CategoriesPage: the list', () => {
  it('is the inventory page on its Categories tab, following the categories by name, 25 a page', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Inventory');
    expect(s.params('inventory.category.list')).toEqual([{ sort: 'name', limit: 25, offset: 0 }]);
    await s.show(LIST);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, pageSize: 25, total: 2, rowClickable: true, addable: true });
    expect(s.prop('searchPlaceholder')).toBe('Search category…');
  });

  it('paints Name, Slug and Products', async () => {
    const s = await setup();
    await s.show(LIST);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, c.sortable])).toEqual([
      ['name', 'Name', true],
      ['slug', 'Slug', true],
      ['product_count', 'Products', true],
    ]);
    expect(s.rows().map((r) => r.text())).toEqual([expect.stringMatching(/Drinks.*drinks.*2/), expect.stringMatching(/Food.*food.*0/)]);
  });

  it('searches and sorts on the server, from the first page', async () => {
    const s = await setup();
    await s.show(page(LIST.rows, 60, 25));
    await s.testid('inventory-categories-page-next').trigger('click');
    await flush();
    s.table().vm.$emit('sortChange', { sort: 'product_count', dir: 'desc' });
    await flush();
    expect(s.params('inventory.category.list')).toEqual([{ sort: '-product_count', limit: 25, offset: 0 }]);
    const bar = s.testid('inventory-categories-search').element as HTMLElement & { value?: string };
    bar.value = 'dri';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'dri' } }));
    await flush();
    expect(s.params('inventory.category.list')).toEqual([{ search: 'dri', sort: '-product_count', limit: 25, offset: 0 }]);
  });

  it('an empty list says «No categories.»; an empty search says nothing matches', async () => {
    const s = await setup();
    await s.show(page([], 0, 25));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No categories.');
    const bar = s.testid('inventory-categories-search').element as HTMLElement & { value?: string };
    bar.value = 'zzz';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'zzz' } }));
    await flush();
    await s.clock.advance(150);
    await s.result(s.net.lastStream(), 'inventory.category.list', page([], 0, 25));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No category matches the search.');
  });

  it('a failed load says so with Retry; an inactive app says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'inventory.category.list'), 'inventory.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg inventory.boom');
    const t = await setup();
    t.call.push(errorFrame(subId(t.client, 'inventory.category.list'), 'app_inactive'));
    await flush();
    expect(t.testid('inventory-categories-inactive').exists()).toBe(true);
    expect(t.table().exists()).toBe(false);
  });
});

describe('CategoriesPage: create, edit and delete', () => {
  it('«+» opens «New category»', async () => {
    const s = await setup();
    await s.show(LIST);
    await s.testid('inventory-categories-add').trigger('click');
    await flush();
    expect([s.form().props('open'), s.form().props('category')]).toEqual([true, null]);
  });

  it('a row and «Edit» open «Editing category» with that category', async () => {
    const s = await setup();
    await s.show(LIST);
    await s.rows()[1].trigger('click');
    await flush();
    expect([s.form().props('open'), (s.form().props('category') as { id: string }).id]).toEqual([true, 'c2']);
    await s.act('edit');
    expect((s.form().props('category') as { id: string }).id).toBe('c1');
    expect(s.prop<Array<{ id: string; label: string }>>('actions').map((a) => [a.id, a.label])).toEqual([
      ['edit', 'Edit'],
      ['delete', 'Delete'],
    ]);
  });

  it('«Delete» says what will happen and, confirmed, deletes and unlinks', async () => {
    const s = await setup();
    await s.show(LIST);
    mocks.confirm.mockResolvedValue(true);
    s.net.onApi(() => ok({ id: 'c1' }));
    await s.act('delete');
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete category',
      message: 'Drinks — 2 product(s) will lose this category (unlinked; products are kept)',
      confirmLabel: 'Delete and unlink',
      tone: 'danger',
    });
    const [call] = s.calls('/api/inventory/categories/delete');
    expect(s.body(call)).toEqual({ id: 'c1' });
  });

  it('cancelled, nothing is deleted; refused, the reason is said above the table', async () => {
    const s = await setup();
    await s.show(LIST);
    mocks.confirm.mockResolvedValue(false);
    await s.act('delete');
    expect(s.calls('/api/inventory/categories/delete')).toHaveLength(0);
    mocks.confirm.mockResolvedValue(true);
    s.net.onApi(() => refusal(404, 'not_found', 'Not found'));
    await s.act('delete');
    expect(s.testid('inventory-categories-page-error').text()).toContain('Not found');
  });

  it('whoever cannot change categories sees the list only: no «+», no actions, no CSV; a row opens nothing', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(LIST);
    expect(s.prop('addable')).toBe(false);
    expect(s.prop('actions')).toEqual([]);
    expect(s.prop('rowClickable')).toBe(false);
    expect(s.wrapper.findComponent(CsvButtons).props()).toMatchObject({ importable: false, exportable: false });
    expect(s.form().exists()).toBe(false);
  });
});

describe('CategoriesPage: import and export', () => {
  it('imports the file in calls of at most 100 rows and shows the result', async () => {
    const s = await setup();
    await s.show(LIST);
    const lines = ['Nombre;Slug;IVA', ...Array.from({ length: 150 }, (_, i) => `Cat ${i};;IVA 10`)].join('\n');
    s.net.onApi((call) => {
      const rows = (JSON.parse(String(call.init.body)) as { rows: Array<{ line: number; name: string }> }).rows;
      return ok({
        dry_run: false,
        total: rows.length,
        ready: 0,
        created: rows.length - 1,
        skipped: 0,
        failed: 1,
        rows: rows.map((r, i) => ({ line: r.line, key: r.name, status: i === 0 ? 'failed' : 'created', id: null, reason: i === 0 ? 'Tax category not recognized: IVA 10' : '' })),
      });
    });
    s.wrapper.findComponent(CsvButtons).vm.$emit('import', lines);
    await flush();
    await flush();
    const calls = s.calls('/api/inventory/categories/bulk_create');
    expect(calls.map((c) => (s.body(c) as { rows: unknown[] }).rows.length)).toEqual([100, 50]);
    expect((s.body(calls[0]) as { rows: unknown[] }).rows[0]).toEqual({ line: 2, name: 'Cat 0', slug: '', tax_category_key: 'IVA 10' });
    const report = s.wrapper.findComponent(ImportReportModal);
    expect(report.props('open')).toBe(true);
    expect(report.props('report')).toMatchObject({ total: 150, created: 148, skipped: 0 });
    expect((report.props('report') as { failed: unknown[] }).failed).toHaveLength(2);
  });

  it('a file without rows says so', async () => {
    const s = await setup();
    await s.show(LIST);
    s.wrapper.findComponent(CsvButtons).vm.$emit('import', 'Nombre;Slug\n');
    await flush();
    expect(s.testid('inventory-categories-page-error').text()).toContain('The file has no rows to import.');
    expect(s.calls('/api/inventory/categories/bulk_create')).toHaveLength(0);
  });

  it('exports what the search finds, with the file the server wrote', async () => {
    const s = await setup();
    await s.show(LIST);
    const bar = s.testid('inventory-categories-search').element as HTMLElement & { value?: string };
    bar.value = 'dri';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'dri' } }));
    await flush();
    s.net.onApi(() => ok({ filename: 'inventario-categorias.csv', content_type: 'text/csv', content: '﻿Nombre;Slug;Productos\n' }));
    s.wrapper.findComponent(CsvButtons).vm.$emit('export');
    await flush();
    const [call] = s.calls('/api/inventory/categories/export');
    expect(s.query(call)).toEqual({ search: 'dri', sort: 'name' });
    expect(mocks.save).toHaveBeenCalledWith('inventario-categorias.csv', '﻿Nombre;Slug;Productos\n', 'text/csv');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(LIST);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Nombre', 'Slug', 'Productos']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar categoría…');
  });
});
