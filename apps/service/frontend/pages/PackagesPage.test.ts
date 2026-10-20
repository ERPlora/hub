// Services → «Bonos y paquetes» (WORKBOOK «Pantallas · Bonos y paquetes»; SERVICE-F12 to F19, F30):
// the live `service.package.list` — Name, Discount, Closed price, Lines and Status —, «Search
// package…», the Status filter (Deleted = the deleted vouchers somebody bought). Above, «Vouchers with
// no customer» for whoever may see them. A row offers Edit, Movements, Sold vouchers and Delete (with
// its confirmation); in the deleted view only Movements and Sold vouchers, and the row opens the sales.
import { ConfirmDialog, DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { click, EMPLOYEE, flush, MANAGER, type MountOptions, mountService, page } from '../__tests__/mount-service';
import { pkg } from '../__tests__/package';
import GrantsSheet from '../components/GrantsSheet.vue';
import MovementsSheet from '../components/MovementsSheet.vue';
import OrphansSheet from '../components/OrphansSheet.vue';
import PackageFormModal from '../components/PackageFormModal.vue';
import PackagesPage from './PackagesPage.vue';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'service.package.list';
const ROWS = [
  pkg(),
  pkg({ id: 'p2', name: 'Bono color', discount_type: 'fixed', discount_percent_bp: 0, discount_amount: 500, fixed_price: null, status: 'archived', is_active: false }),
];

async function setup(options: MountOptions = {}) {
  const m = await mountService(PackagesPage, { path: '/service/packages', ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="service-packages-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const actions = () => prop<Array<{ id: string }>>('actions').map((a) => a.id);
  return { ...m, table, prop, rows, cells, actions, list: () => m.params(OP), show: (data: unknown) => m.result(OP, data) };
}

describe('PackagesPage', () => {
  it('follows the packages by their order, with Name, Discount, Closed price, Lines and Status', async () => {
    const s = await setup();
    expect(s.list()).toEqual([{ sort: 'sort_order', limit: 50, offset: 0 }]);
    await s.show(page(ROWS));
    expect(s.prop('searchPlaceholder')).toBe('Search package…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New package');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['discount', 'Discount'],
      ['fixed_price', 'Closed price'],
      ['item_count', 'Lines'],
      ['status', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 5)).toEqual(['Bono 5 cortes', '10.5%', '€90.00', '1', 'Active']);
    expect(s.cells(1).slice(1, 5)).toEqual(['€5.00', '—', '1', 'Archived']);
  });

  it('a voucher with no discount says «—», never «-0 %» or «€0.00» (services#166)', async () => {
    const s = await setup();
    await s.show(page([pkg({ discount_percent_bp: 0 }), pkg({ id: 'p3', name: 'Bono uñas', discount_type: 'fixed', discount_percent_bp: 0, discount_amount: 0 })]));
    expect([s.cells(0)[1], s.cells(1)[1]]).toEqual(['—', '—']);
  });

  it('keeps the column filters behind «Filters», as the old screen\'s funnel', async () => {
    const s = await setup();
    expect(s.prop('filterable')).toBe(true);
  });

  it('none at all says «No packages.»; the Status filter on Deleted is the deleted view', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No packages.');
    s.table().vm.$emit('filtersChange', { status: 'deleted', name: 'bono' });
    await flush();
    expect(s.list()).toEqual([{ status: 'deleted', name: 'bono', sort: 'sort_order', limit: 50, offset: 0 }]);
    expect(s.actions()).toEqual(['movements', 'grants']);
    s.table().vm.$emit('rowClick', pkg({ status: 'deleted' }));
    await flush();
    expect(s.wrapper.findComponent(GrantsSheet).props()).toMatchObject({ open: true, pkg: pkg({ status: 'deleted' }) });
  });

  it('a row offers Edit, Movements, Sold vouchers and Delete, and each opens its own', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    expect(s.actions()).toEqual(['edit', 'movements', 'grants', 'delete']);
    s.table().vm.$emit('action', { actionId: 'movements', row: ROWS[0] });
    await flush();
    expect(s.wrapper.findComponent(MovementsSheet).props()).toMatchObject({ open: true, pkg: ROWS[0] });
    s.table().vm.$emit('action', { actionId: 'grants', row: ROWS[0] });
    await flush();
    expect(s.wrapper.findComponent(GrantsSheet).props()).toMatchObject({ open: true, pkg: ROWS[0] });
    s.table().vm.$emit('rowClick', ROWS[1]);
    await flush();
    expect([s.wrapper.findComponent(PackageFormModal).props('open'), s.wrapper.findComponent(PackageFormModal).props('pkg')]).toEqual([true, ROWS[1]]);
  });

  it('deletes after its confirmation, saying what happens to the vouchers sold', async () => {
    const s = await setup();
    await s.show(page(ROWS));
    s.table().vm.$emit('action', { actionId: 'delete', row: ROWS[0] });
    await flush();
    const dialog = s.wrapper.findComponent(ConfirmDialog);
    expect([dialog.props('title'), dialog.props('message')]).toEqual([
      'Delete package',
      'Bono 5 cortes — the package and its 1 line(s) leave the catalogue and can no longer be sold; vouchers already sold can still be spent, and you find them filtering Status by Deleted.',
    ]);
    s.answer(200, { id: 'p1' });
    dialog.vm.$emit('confirm');
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/service/packages/delete', query: {}, body: { id: 'p1' } }]);
  });

  it('«Vouchers with no customer» opens its sheet, for whoever may see them', async () => {
    const s = await setup();
    await click(s.inDoc('service-packages-orphans-open'));
    expect(s.wrapper.findComponent(OrphansSheet).props('open')).toBe(true);
  });

  it('a manager edits and sees the orphans but does not delete; an employee only looks', async () => {
    const manager = await setup({ session: MANAGER });
    await manager.show(page(ROWS));
    expect(manager.actions()).toEqual(['edit', 'movements', 'grants']);
    expect(manager.inDoc('service-packages-orphans-open')).not.toBeNull();
    const employee = await setup({ session: EMPLOYEE });
    await employee.show(page(ROWS));
    expect([employee.prop('addable'), employee.prop('rowClickable'), employee.actions()]).toEqual([false, false, ['movements', 'grants']]);
    expect(employee.inDoc('service-packages-orphans-open')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page(ROWS));
    expect([s.prop('searchPlaceholder'), s.cells(1)[4]]).toEqual(['Buscar paquete…', 'Archivado']);
    expect(s.inDoc('service-packages-orphans-open')?.textContent).toContain('Bonos sin cliente');
  });
});

describe('PackagesPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
});
