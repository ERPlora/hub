// Services → Categories (WORKBOOK «Pantallas · Categorías»; SERVICE-F07, F08): the live
// `service.category.list` — Name, Parent category, Order and Services (the offered ones in it) —,
// «Search category…», by order and name. «New category» (whoever may add) and a row (whoever may edit)
// open the form; Delete asks first, saying how many services will be left without a category.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { CategoryOut } from '../operations';
import { EMPLOYEE, flush, MANAGER, type MountOptions, mountService, page } from '../__tests__/mount-service';
import CategoryFormModal from '../components/CategoryFormModal.vue';
import CategoriesPage from './CategoriesPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'service.category.list';
const category = (id: string, over: Partial<CategoryOut> = {}): CategoryOut => ({
  id,
  name: 'Hair',
  description: '',
  parent_id: null,
  parent_name: null,
  icon: '',
  color: '',
  sort_order: 1,
  service_count: 3,
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
  ...over,
});
const ROWS = [category('c1'), category('c2', { name: 'Colour', parent_id: 'c1', parent_name: 'Hair', sort_order: 2, service_count: 0 })];

async function setup(options: MountOptions = {}) {
  const m = await mountService(CategoriesPage, { path: '/service/categories', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="service-categories-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('CategoriesPage', () => {
  it('follows the categories by their order, with Name, Parent, Order and Services', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'sort_order', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search category…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New category');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['parent_name', 'Parent category'],
      ['sort_order', 'Order'],
      ['service_count', 'Services'],
    ]);
    expect(s.cells(0).slice(0, 4)).toEqual(['Hair', '—', '1', '3']);
    expect(s.cells(1).slice(0, 4)).toEqual(['Colour', 'Hair', '2', '0']);
  });

  it('searches and sorts on the server; none at all says «No categories.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No categories.');
    s.table().vm.$emit('sortChange', { sort: 'service_count', dir: 'desc' });
    s.table().vm.$emit('update:search', 'ha');
    await flush();
    expect(s.list()).toEqual([{ search: 'ha', sort: '-service_count', limit: 50, offset: 0 }]);
  });

  it('«New category» and a row open the form', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    const modal = () => s.wrapper.findComponent(CategoryFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('category')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([modal().props('open'), modal().props('category')]).toEqual([true, ROWS[1]]);
  });

  it('deletes after its confirmation, saying how many services are left without a category', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('title'), dialog.props('message'), dialog.props('consequences'), dialog.props('confirmLabel')]).toEqual([
      'Delete category',
      'Hair — the category disappears; the services in it are kept, without a category.',
      ['3 service(s) will be left without a category.'],
      'Delete',
    ]);
    s.answer(200, { id: 'c1' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/service/categories/delete', query: {}, body: { id: 'c1' } }]);
  });

  it('an empty category says nothing about its services when deleted', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[1] });
    await flush();
    expect(s.wrapper.findComponent(ConfirmDialog).props('consequences')).toEqual([]);
  });

  it('a manager edits but does not delete; an employee only reads', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(page(ROWS));
    expect(manager.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['edit']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(page(ROWS));
    expect([employee.prop('addable'), employee.prop('rowClickable'), employee.prop<unknown[]>('actions')]).toEqual([false, false, []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect([s.prop('searchPlaceholder'), s.prop<{ add: string }>('labels').add]).toEqual(['Buscar categoría…', 'Nueva categoría']);
  });
});
