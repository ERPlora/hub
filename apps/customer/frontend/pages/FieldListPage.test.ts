// Customers → Fields (WORKBOOK «Pantallas · Campos»; CUSTOMER-F29): the live `customer.field.list` in
// a server-side DataTable — Name, Type, Required (Yes/No), Order, Active —, «Search field…», filters
// by type, required and active; «Add», «Edit» and «Delete» to whoever configures.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { pageOf } from '../__tests__/fixtures';
import { EMPLOYEE, flush, type MountOptions, mountCustomer } from '../__tests__/mount-customer';
import EntityDeleteDialog from '../components/EntityDeleteDialog.vue';
import FieldFormModal from '../components/FieldFormModal.vue';
import SelectFilters from '../components/SelectFilters.vue';
import type { FieldRow } from '../operations';
import FieldListPage from './FieldListPage.vue';

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
  return { ...m, call, table, prop, show: (page: unknown) => m.result(call, LIST, page) };
}

describe('FieldListPage', () => {
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

  it('filters by type, required and active on the server', async () => {
    const s = await setup();
    await s.show(PAGE);
    const filters = s.wrapper.findComponent(SelectFilters);
    expect((filters.props('filters') as unknown as { key: string }[]).map((f) => f.key)).toEqual(['field_type', 'is_required', 'is_active']);
    filters.vm.$emit('update:modelValue', { field_type: 'select', is_required: 'true', is_active: 'false' });
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

  it('the employee only sees', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(PAGE);
    expect(s.prop<{ id: string }[]>('actions')).toEqual([]);
    expect(s.wrapper.find('[data-testid="customer-fields-add"]').exists()).toBe(false);
  });

  it('empty: «No custom fields.»; Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(pageOf([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('Sin campos personalizados.');
  });
});
