// Customers → Fields (WORKBOOK «Pantallas · Campos»; CUSTOMER-F29): the live `customer.field.list` in
// a server-side DataTable — Name, Type, Required (Yes/No), Order, Active —, «Search field…», filters
// behind the table's funnel by type, required and active; «Add», «Edit» and «Delete» to whoever configures.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { pageOf } from '../__tests__/fixtures';
import { EMPLOYEE, flush, type MountOptions, mountCustomer } from '../__tests__/mount-customer';
import EntityDeleteDialog from '../components/EntityDeleteDialog.vue';
import FieldFormModal from '../components/FieldFormModal.vue';
import type { FieldRow } from '../operations';
import FieldListPage from './FieldListPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
afterEach(() => {
  document.body.innerHTML = '';
});

const LIST = 'customer.field.list';
const field = (id: string, name: string, extra: Partial<FieldRow> = {}): FieldRow => ({
  id,
  name,
  field_type: 'text',
  options: [],
  is_required: false,
  sort_order: 0,
  is_active: true,
  ...extra,
});
const PAGE = pageOf([field('f1', 'Allergies', { field_type: 'textarea', is_required: true }), field('f2', 'Dye', { field_type: 'select' })]);

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(FieldListPage, { path: '/customer/fields', attachTo: document.body, ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const find = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, call, table, prop, find, show: (page: unknown) => m.result(call, LIST, page) };
}

describe('FieldListPage', () => {
  it('on a phone the card names the row once: its title stands for the Name column (customers#95)', async () => {
    const s = await setup();
    expect(s.prop('cardTitleColumn')).toBe('name');
  });

  it('is «Custom fields», following the fields by their order', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Custom fields');
    expect(s.params(LIST)).toEqual([{ sort: 'sort_order', descending: false, limit: 50, offset: 0 }]);
  });

  it('paints Name, Type, Required, Order and Active', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<{ key: string; label: string }[]>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['field_type', 'Type'],
      ['is_required', 'Required'],
      ['sort_order', 'Order'],
      ['is_active', 'Active'],
    ]);
    expect(s.wrapper.findAll('[data-testid="customer-fields-type"]').map((c) => c.text())).toEqual(['Long text', 'Select']);
    expect(s.wrapper.findAll('[data-testid="customer-fields-required"]').map((c) => c.text())).toEqual(['Yes', 'No']);
  });

  it('filters behind the table funnel: type, required and active (yes/no) on their columns', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; options?: Array<{ value: string; label: string }> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.key, c.label, c.filter?.type])).toEqual([
      ['field_type', 'Type', 'select'],
      ['is_required', 'Required', 'boolean'],
      ['is_active', 'Active', 'boolean'],
    ]);
    expect(columns[1].filter?.options?.map((o) => [o.value, o.label])).toEqual([
      ['text', 'Text'],
      ['number', 'Number'],
      ['date', 'Date'],
      ['boolean', 'Yes/No'],
      ['select', 'Select'],
      ['textarea', 'Long text'],
    ]);
    await s.find('customer-fields-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('customer-fields-filters-panel');
    panel.get('[data-testid="customer-fields-filter-is_required"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'true' } }));
    await flush();
    await panel.get('[data-testid="customer-fields-filters-apply"]').trigger('click');
    await flush();
    expect(s.params(LIST)).toEqual([{ is_required: true, sort: 'sort_order', descending: false, limit: 50, offset: 0 }]);
    expect(s.find('customer-fields-filters-count').text()).toBe('1');
  });

  it('filters by type, required and active on the server', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.table().vm.$emit('update:filters', { field_type: 'select', is_required: 'true', is_active: 'false' });
    await flush();
    expect(s.params(LIST)).toEqual([
      { field_type: 'select', is_required: true, is_active: false, sort: 'sort_order', descending: false, limit: 50, offset: 0 },
    ]);
  });

  it('«Add», «Edit» and «Delete» for whoever configures', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['edit', 'delete']);
    await s.wrapper.get('[data-testid="customer-fields-add"]').trigger('click');
    expect(s.wrapper.findComponent(FieldFormModal).props()).toMatchObject({ open: true, field: null });
    s.table().vm.$emit('action', { actionId: 'delete', row: PAGE.rows[1] });
    await flush();
    expect(s.wrapper.findComponent(EntityDeleteDialog).props()).toMatchObject({ kind: 'fields', target: { id: 'f2', name: 'Dye' } });
  });

  it('the employee adds, edits and deletes with a manager’s approval', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['edit', 'delete']);
    expect(s.wrapper.find('[data-testid="customer-fields-add"]').exists()).toBe(true);
  });

  it('empty: «No custom fields.»; Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(pageOf([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('Sin campos personalizados.');
  });
});

describe('FieldListPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
