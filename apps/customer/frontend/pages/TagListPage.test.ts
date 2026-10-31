// Customers → Tags (WORKBOOK «Pantallas · Etiquetas»; CUSTOMER-F28): the live `customer.tag.list` in
// a server-side DataTable — Name, Color, Customers, Active —, «Search tag…» and the active filter behind the table's funnel;
// the same actions as Groups.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { pageOf } from '../__tests__/fixtures';
import { EMPLOYEE, flush, MANAGER, type MountOptions, mountCustomer, VIEWER } from '../__tests__/mount-customer';
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
  const find = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, call, table, prop, find, show: (page: unknown) => m.result(call, LIST, page) };
}

describe('TagListPage', () => {
  it('on a phone the card names the row once: its title stands for the Name column (customers#95)', async () => {
    const s = await setup();
    expect(s.prop('cardTitleColumn')).toBe('name');
  });

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

  it('filters by active behind the table funnel, on its column', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; options?: Array<{ value: string; label: string }> };
    const columns = s.prop<Array<{ key: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.key, c.filter?.type])).toEqual([['is_active', 'select']]);
    expect(columns.find((c) => c.key === 'is_active')?.filter?.options).toEqual([
      { value: 'true', label: 'Active' },
      { value: 'false', label: 'Not active' },
    ]);
    await s.find('customer-tags-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('customer-tags-filters-panel');
    panel.get('[data-testid="customer-tags-filter-is_active"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'false' } }));
    await flush();
    await panel.get('[data-testid="customer-tags-filters-apply"]').trigger('click');
    await flush();
    expect(s.params(LIST)).toEqual([{ is_active: false, sort: 'name', descending: false, limit: 50, offset: 0 }]);
    expect(s.find('customer-tags-filters-count').text()).toBe('1');
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

  it('the manager does not delete; the employee adds and edits with a manager’s approval, never deletes', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(PAGE);
    expect(manager.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['edit']);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(PAGE);
    expect(employee.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['edit']);
    expect(employee.wrapper.find('[data-testid="customer-tags-add"]').exists()).toBe(true);
  });

  it('who only views neither adds, edits nor deletes', async () => {
    const viewer = await setup({ session: VIEWER });
    await viewer.show(PAGE);
    expect(viewer.prop<{ id: string }[]>('actions')).toEqual([]);
    expect(viewer.wrapper.find('[data-testid="customer-tags-add"]').exists()).toBe(false);
  });

  it('empty: «No tags.»; Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(pageOf([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('Sin etiquetas.');
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Etiquetas de clientes');
  });

  it('wears the product’s icon, pricetags, on each card and on the empty list', async () => {
    const s = await setup();
    await s.show(pageOf([]));
    expect(s.wrapper.findComponent(EmptyState).props('icon')).toBe('pricetags');
    expect(s.prop<(row: unknown) => string>('cardIcon')(PAGE.rows[0])).toBe('ion:pricetags');
  });
});

describe('TagListPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
