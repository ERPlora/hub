// Customers → Groups (WORKBOOK «Pantallas · Grupos»; CUSTOMER-F27): the live `customer.group.list`
// in a server-side DataTable — Name, Description, Customers (live cards in it), Order, Active —,
// «Search group…», the active filter behind the table's funnel; «Add» and «Edit» (also a tap on the row) to whoever
// configures, «Delete» to the owner and the admin.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { pageOf } from '../__tests__/fixtures';
import { EMPLOYEE, errorFrame, flush, MANAGER, type MountOptions, mountCustomer, subId } from '../__tests__/mount-customer';
import EntityDeleteDialog from '../components/EntityDeleteDialog.vue';
import GroupFormModal from '../components/GroupFormModal.vue';
import type { GroupRow } from '../operations';
import GroupListPage from './GroupListPage.vue';
import source from './GroupListPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
afterEach(() => {
  document.body.innerHTML = '';
});

const LIST = 'customer.group.list';
const group = (id: string, name: string, extra: Partial<GroupRow> = {}): GroupRow => ({
  id,
  name,
  description: 'For the best',
  color: 'primary',
  sort_order: 1,
  is_active: true,
  customer_count: 4,
  ...extra,
});
const PAGE = pageOf([group('g1', 'VIP'), group('g2', 'Old', { is_active: false })]);

async function setup(options: MountOptions = {}) {
  const m = await mountCustomer(GroupListPage, { path: '/customer/groups', attachTo: document.body, ...options });
  const call = await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const find = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  return { ...m, call, table, prop, find, show: (page: unknown) => m.result(call, LIST, page) };
}

describe('GroupListPage', () => {
  it('on a phone the card names the row once: its title stands for the Name column (customers#95)', async () => {
    const s = await setup();
    expect(s.prop('cardTitleColumn')).toBe('name');
  });

  it('is «Customer groups» in the Groups tab, following the groups by name, 50 a page', async () => {
    const s = await setup();
    const page = s.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Customer groups');
    expect((page.props('tabs') as { id: string }[]).map((t) => t.id)).toEqual(['customers', 'groups', 'tags', 'fields']);
    expect(s.params(LIST)).toEqual([{ sort: 'name', descending: false, limit: 50, offset: 0 }]);
  });

  it('paints Name, Description, Customers, Order and Active', async () => {
    const s = await setup();
    await s.show(PAGE);
    expect(s.prop<{ key: string; label: string }[]>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['description', 'Description'],
      ['customer_count', 'Customers'],
      ['sort_order', 'Order'],
      ['is_active', 'Active'],
    ]);
    expect(s.wrapper.findAll('[data-testid="customer-groups-row"]').map((r) => r.attributes('data-id'))).toEqual(['g1', 'g2']);
    expect(s.wrapper.findAll('[data-testid="customer-groups-active"]').map((c) => c.text())).toEqual(['Yes', 'No']);
    expect(s.prop('searchPlaceholder')).toBe('Search group…');
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
    await s.find('customer-groups-filters-toggle').trigger('click');
    await flush();
    const panel = s.find('customer-groups-filters-panel');
    panel.get('[data-testid="customer-groups-filter-is_active"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'false' } }));
    await flush();
    await panel.get('[data-testid="customer-groups-filters-apply"]').trigger('click');
    await flush();
    expect(s.params(LIST)).toEqual([{ is_active: false, sort: 'name', descending: false, limit: 50, offset: 0 }]);
    expect(s.find('customer-groups-filters-count').text()).toBe('1');
  });

  it('«Add» opens «New group»; «Edit» and a tap on the row open «Edit · {name}»', async () => {
    const s = await setup();
    await s.show(PAGE);
    await s.wrapper.get('[data-testid="customer-groups-add"]').trigger('click');
    expect(s.wrapper.findComponent(GroupFormModal).props()).toMatchObject({ open: true, group: null });
    s.wrapper.findComponent(GroupFormModal).vm.$emit('update:open', false);
    await flush();
    s.table().vm.$emit('action', { actionId: 'edit', row: PAGE.rows[0] });
    await flush();
    expect(s.wrapper.findComponent(GroupFormModal).props()).toMatchObject({ open: true, group: PAGE.rows[0] });
    s.wrapper.findComponent(GroupFormModal).vm.$emit('update:open', false);
    await flush();
    await s.wrapper.findAll('[data-testid="customer-groups-row"]')[1].trigger('click');
    expect(s.wrapper.findComponent(GroupFormModal).props('group')).toEqual(PAGE.rows[1]);
  });

  it('«Delete» asks in its dialog', async () => {
    const s = await setup();
    await s.show(PAGE);
    s.table().vm.$emit('action', { actionId: 'delete', row: PAGE.rows[0] });
    await flush();
    expect(s.wrapper.findComponent(EntityDeleteDialog).props()).toMatchObject({ kind: 'groups', target: { id: 'g1', name: 'VIP' } });
  });

  it('the manager adds and edits but does not delete; the employee only sees', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(PAGE);
    expect(manager.prop<{ id: string }[]>('actions').map((a) => a.id)).toEqual(['edit']);
    expect(manager.wrapper.find('[data-testid="customer-groups-add"]').exists()).toBe(true);
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(PAGE);
    expect(employee.prop<{ id: string }[]>('actions')).toEqual([]);
    expect(employee.wrapper.find('[data-testid="customer-groups-add"]').exists()).toBe(false);
    expect(employee.prop('rowClickable')).toBe(false);
  });

  it('empty: «No groups.»; a search with nothing: «No results»; a failure with Retry', async () => {
    const s = await setup();
    await s.show(pageOf([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No groups.');
    s.call.push(errorFrame(subId(s.client, LIST), 'boom'));
    await flush();
    expect(s.prop('error')).toBe('msg boom');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(PAGE);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Grupos de clientes');
    expect(s.prop<{ label: string }[]>('columns').map((c) => c.label)).toEqual(['Nombre', 'Descripción', 'Clientes', 'Orden', 'Activo']);
  });

  it('has no OutfitKit tag', () => {
    expect(source).not.toMatch(/<ok[-]/);
  });
});

describe('GroupListPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
