// Menus (WORKBOOK «Pantallas · Menús»; COMBO-F01 to F04): the live `combo.combo.list` — Name, Closed
// price, How it is sold, On sale and Order —, «Search a menu…», filters by name, how it is sold and on
// sale, by order then name, 50 a page. With the right to manage: «+», and per row «Edit details» and
// «Withdraw» (after its confirmation). Tapping a row opens the menu's builder.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountCombo, page } from '../__tests__/mount-combo';
import MenuFormModal from '../components/MenuFormModal.vue';
import type { ComboOut } from '../operations';
import MenusPage from './MenusPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'combo.combo.list';

const menu = (fields: Partial<ComboOut> = {}): ComboOut => ({
  id: 'm1',
  name: 'Menu of the day',
  kitchen_name: '',
  price: 1350,
  supply_kind: 'service',
  tax_category_key: 'restaurant.food',
  tax_category_name: 'Restaurant — food',
  sort_order: 1,
  is_active: true,
  group_count: 3,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
  ...fields,
});
const ROWS = [menu(), menu({ id: 'm2', name: 'Sandwich pack', price: 600, supply_kind: 'goods', is_active: false, sort_order: 2 })];

async function setup(options: MountOptions = {}) {
  const m = await mountCombo(MenusPage, { path: '/combo/menus', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="combo-menus-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const actions = () => prop<Array<{ id: string }>>('actions').map((a) => a.id);
  return { ...m, table, prop, rows, cells, actions, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('MenusPage', () => {
  it('follows the menus by their order, with the old columns', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'sort_order', dir: 'asc', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search a menu…');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['price', 'Closed price'],
      ['supply_kind', 'How it is sold'],
      ['is_active', 'On sale'],
      ['sort_order', 'Order'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['Menu of the day', '€13.50', 'Eat in', 'Yes', '1']);
    expect(s.cells(1).slice(1, 4)).toEqual(['€6.00', 'Take away', 'No']);
  });

  it('none at all says how to start; the filters narrow it on the server', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No menus yet. Create the first one with the + button.');
    s.table().vm.$emit('filtersChange', { name: 'day', supply_kind: 'goods', is_active: 'false' });
    await flush();
    expect(s.list()).toEqual([{ name: 'day', supply_kind: 'goods', is_active: false, sort: 'sort_order', dir: 'asc', limit: 50, offset: 0 }]);
  });

  it('pm#611: while the menus are on their way the table says it is loading, never «0 records» nor «No menus»', async () => {
    const s = await setup();
    expect(s.prop('loading')).toBe(true);
    expect(s.wrapper.findComponent(EmptyState).exists()).toBe(false);
    await s.show(page(ROWS));
    expect(s.prop('loading')).toBe(false);
  });

  it('pm#533, hub#2328: a list that cannot be read says so with «Retry», never that there are no menus', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await flush();
    expect(s.prop('error')).toBe('The menus could not be loaded.');
    expect(s.prop('loading')).toBe(false);
    expect(s.wrapper.findComponent(EmptyState).exists()).toBe(false);
    const asked = s.list().length;
    s.table().vm.$emit('retry');
    await flush();
    await s.reopen();
    expect(s.list().length).toBeGreaterThanOrEqual(asked);
    await s.show(page(ROWS));
    expect(s.prop('error')).toBeUndefined();
    expect(s.rows()).toHaveLength(2);
  });

  it('tapping a row opens its builder', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/combo/menus/m2');
  });

  it('«+» and «Edit details» open the menu form', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.actions()]).toEqual([true, ['edit', 'delete']]);
    s.table().vm.$emit('add');
    await flush();
    expect([s.wrapper.findComponent(MenuFormModal).props('open'), s.wrapper.findComponent(MenuFormModal).props('combo')]).toEqual([true, null]);
    s.table().vm.$emit('action', { actionId: 'edit', row: ROWS[0] });
    await flush();
    expect(s.wrapper.findComponent(MenuFormModal).props('combo')).toEqual(ROWS[0]);
  });

  it('withdraws after its confirmation', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('title'), dialog.props('message'), dialog.props('confirmLabel')]).toEqual([
      'Withdraw this menu?',
      '«Menu of the day» stops being on sale, together with its courses and choices. Tickets already issued keep reading it.',
      'Withdraw',
    ]);
    s.answer(200, { id: 'm1' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/combo/combos/delete', query: {}, body: { id: 'm1' } }]);
  });

  it('an employee only looks, and still opens a menu', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page(ROWS));
    expect([s.prop('addable'), s.actions(), s.prop('rowClickable')]).toEqual([false, [], true]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Buscar un menú…');
    expect(s.cells(1).slice(2, 4)).toEqual(['Para llevar', 'No']);
    expect(s.cells(0)[3]).toBe('Sí');
  });
});

describe('MenusPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
