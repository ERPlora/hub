// Staff → Roles (WORKBOOK «Pantallas · Roles»; STAFF-F04, F23): the live `staff.role.list` in a
// server-side DataTable — Role (with its colour, and «Retired» on a retired one), Description and
// Members (the ACTIVE people who hold it) —, «Search role…», sort by any column, filters (status,
// colour, members from–to), 50 a page. «+» opens «New» and a row «Edit · {name}» for whoever manages
// roles; everyone else only reads. Changes come back through the stream.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import type { RoleOut } from '../operations';
import { EMPLOYEE, flush, type MountOptions, mountStaff, page } from '../__tests__/mount-staff';
import RoleFormModal from '../components/RoleFormModal.vue';
import RolesPage from './RolesPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'staff.role.list';
const role = (id: string, over: Partial<RoleOut> = {}): RoleOut => ({
  id,
  name: 'Stylist',
  description: 'Cuts and colour',
  color: '#AA3300',
  order: 0,
  is_active: true,
  member_count: 3,
  ...over,
});
const ROWS = [role('r1'), role('r2', { name: 'Barber', description: '', color: '', is_active: false, member_count: 0 })];

async function setup(options: MountOptions = {}) {
  const m = await mountStaff(RolesPage, { path: '/staff/roles', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="staff-roles-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  return { ...m, table, prop, rows, cells, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('RolesPage', () => {
  it('follows the roles sorted by name, 50 from the first', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'staff-roles', total: 2, views: ['table', 'cards'] });
    expect(s.prop('searchPlaceholder')).toBe('Search role…');
    expect(s.prop('entityLabel')).toEqual({ one: 'role', many: 'roles' });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Staff');
  });

  it('paints Role (marked «Retired» when it is), Description and Members, all sortable', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, c.sortable])).toEqual([
      ['name', 'Role', true],
      ['description', 'Description', true],
      ['member_count', 'Members', true],
    ]);
    expect(s.cells(0).slice(0, 3)).toEqual(['Stylist', 'Cuts and colour', '3']);
    expect(s.cells(1)[0]).toContain('Barber');
    expect(s.cells(1)[0]).toContain('Retired');
    expect(s.cells(1).slice(1, 3)).toEqual(['—', '0']);
    expect(s.find('staff-roles-retired').exists()).toBe(true);
  });

  it('sorts and searches on the server; no role at all says «No roles defined.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No roles defined.');
    s.table().vm.$emit('sortChange', { sort: 'member_count', dir: 'desc' });
    s.table().vm.$emit('update:search', 'sty');
    await flush();
    expect(s.list()).toEqual([{ search: 'sty', sort: '-member_count', limit: 50, offset: 0 }]);
  });

  it('filters behind the table funnel: members from–to on its column, then status (a yes/no on the server) and colour', async () => {
    // flow: ninguno — FIX DataTable parte 2b-1 (PLAN-MIGRATIONS §13: filtros como en la vieja)
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; key?: string; keys?: string[]; min?: number; step?: number; options?: unknown[] };
    const columns = s.prop<Array<{ key: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.key, c.filter])).toEqual([
      ['member_count', { type: 'range', keys: ['member_count_min', 'member_count_max'], min: 0, step: 1 }],
    ]);
    const fields = s.prop<Array<Filter & { key: string; label: string }>>('filterFields');
    expect(fields.map((f) => [f.key, f.label, f.type])).toEqual([
      ['is_active', 'Status', 'select'],
      ['color', 'Color (#RRGGBB)', 'text'],
    ]);
    expect(fields[0].options).toEqual([
      { value: 'true', label: 'Active' },
      { value: 'false', label: 'Retired' },
    ]);
    s.table().vm.$emit('update:filters', { is_active: 'false', member_count_min: '1' });
    await flush();
    expect(s.list()).toEqual([{ is_active: false, member_count_min: 1, sort: 'name', limit: 50, offset: 0 }]);
    expect(s.find('staff-roles-filters-count').text()).toBe('2');
  });

  it('who manages roles adds and opens a row; «+» is «New», a row «Edit · {name}»', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable')]).toEqual([true, true]);
    const modal = () => s.wrapper.findComponent(RoleFormModal);
    s.table().vm.$emit('add');
    await flush();
    expect([modal().props('open'), modal().props('role')]).toEqual([true, null]);
    modal().vm.$emit('update:open', false);
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([modal().props('open'), modal().props('role')]).toEqual([true, ROWS[1]]);
  });

  it('an employee only reads', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.prop('rowClickable')]).toEqual([false, false]);
    expect(s.wrapper.findComponent(RoleFormModal).exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Buscar rol…');
    expect(s.cells(1)[0]).toContain('Retirado');
  });
});

describe('RolesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
