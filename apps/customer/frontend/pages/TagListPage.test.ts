// Customers → Tags (WORKBOOK «Pantallas · Etiquetas»; CUSTOMER-F28): the live `customer.tag.list` in
// a server-side DataTable — Name, Color, Customers, Active —, «Search tag…» and the active filter;
// the same actions as Groups.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { pageOf } from '../__tests__/fixtures';
import { EMPLOYEE, flush, MANAGER, type MountOptions, mountCustomer } from '../__tests__/mount-customer';
import EntityDeleteDialog from '../components/EntityDeleteDialog.vue';
import TagFormModal from '../components/TagFormModal.vue';
import type { TagRow } from '../operations';
import TagListPage from './TagListPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
afterEach(() => {
  document.body.innerHTML = '';
});

const LIST = 'customer.tag.list';
const tag = (id: string, name: string, extra: Partial<TagRow> = {}): TagRow => ({ id, name, color: 'success', is_active: true, customer_count: 2, ...extra });
const PAGE = pageOf([tag('t1', 'Loyal'), tag('t2', 'Odd', { color: '#ff00aa', is_active: false })]);

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(TagListPage, { path: '/customer/tags', attachTo: document.body, ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  return { ...m, call, table, prop, show: (page: unknown) => m.result(call, LIST, page) };
}

describe('TagListPage', () => {
  it('is «Customer tags», following the tags by name', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Customer tags');
    expect(s.params(LIST)).toEqual([{ sort: 'name', descending: false, limit: 50, offset: 0 }]);
  });

  it('paints Name, Color (its name), Customers and Active', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<{ key: string; label: string }[]>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['color', 'Color'],
      ['customer_count', 'Customers'],
      ['is_active', 'Active'],
    ]);
    expect(s.wrapper.findAll('[data-testid="customer-tags-color"]').map((c) => c.text())).toEqual(['Green', '#ff00aa']);
    expect(s.wrapper.findAll('[data-testid="customer-tags-active"]').map((c) => c.text())).toEqual(['Yes', 'No']);
  });

  it('«Add», «Edit» and the row open the tag\'s dialog; «Delete» asks in its own', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.wrapper.get('[data-testid="customer-tags-add"]').trigger('click');
    expect(s.wrapper.findComponent(TagFormModal).props()).toMatchObject({ open: true, tag: null });
    s.table().vm.$emit('action', { actionId: 'edit', row: PAGE.rows[0] });
    await flush();
    expect(s.wrapper.findComponent(TagFormModal).props('tag')).toEqual(PAGE.rows[0]);
    s.table().vm.$emit('action', { actionId: 'delete', row: PAGE.rows[1] });
    await flush();
    expect(s.wrapper.findComponent(EntityDeleteDialog).props()).toMatchObject({ kind: 'tags', target: { id: 't2', name: 'Odd' } });
  });

  it('the manager does not delete; the employee only sees', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(PAGE);
    expect(manager.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['edit']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(PAGE);
    expect(employee.prop<{ id: string }[]>('actions')).toEqual([]);
    expect(employee.wrapper.find('[data-testid="customer-tags-add"]').exists()).toBe(false);
  });

  it('empty: «No tags.»; Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(pageOf([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('Sin etiquetas.');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Etiquetas de clientes');
  });
});

describe('TagListPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
