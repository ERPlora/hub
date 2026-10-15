// Inventory → Movements (WORKBOOK «Movimientos», INVENTORY-F16): the stock ledger, read only, live
// (`inventory.movement.list`): Date, Name, SKU, Type, Quantity with its sign, Balance, Reason and
// Reference; most recent first, 50 a page; search by product, SKU or reference; filters by Type and
// by Reference; sort by Date, Type, Quantity or Balance. An empty ledger says where movements come
// from; a search that finds nothing says how a sale is found. A new movement (a reception, a count, a
// sale) arrives through the stream.
import { DataTable, formatDateTime } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, errorFrame, flush, type MountOptions, mountInventory, page, subId } from '../__tests__/mount-inventory';
import MovementsPage from './MovementsPage.vue';
import source from './MovementsPage.vue?raw';

const movement = (id: string, type: string, qty: string, after: string, overrides: Record<string, unknown> = {}) => ({
  id,
  product_id: 'p1',
  product_name: 'Coffee',
  sku: 'CAF-1',
  movement_type: type,
  qty,
  stock_after: after,
  reason: '',
  reference: '',
  unit_cost: null,
  actor: 'u1',
  created_at: '2026-10-13T10:00:00Z',
  ...overrides,
});

const LEDGER = page([
  movement('m2', 'count', '-1.500', '8.500', { reason: 'Broken bottle' }),
  movement('m1', 'reception', '10.000', '10.000', { reference: 'ALB-2026-0001' }),
]);

async function setup(options: MountOptions = {}) {
  const m = await mountInventory(MovementsPage, { path: '/inventory/movements', ...options });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="inventory-movements-row"]');
  async function onNewStream(data: unknown) {
    await m.clock.advance(150);
    await m.result(m.net.lastStream(), 'inventory.movement.list', data);
  }
  async function pick(id: string, value: string, event = 'ionChange') {
    testid(id).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    await flush();
  }
  return { ...m, call, testid, table, prop, rows, onNewStream, pick, show: (data: unknown, rev?: number) => m.result(call, 'inventory.movement.list', data, rev) };
}

describe('MovementsPage', () => {
  it('is the inventory page on its Movements tab, following the ledger most recent first, 50 a page', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Inventory');
    expect(s.params('inventory.movement.list')).toEqual([{ sort: '-created_at', limit: 50, offset: 0 }]);
    expect(s.testid('inventory-movements-loading').exists()).toBe(true);
    await s.show(LEDGER);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, pageSize: 50, sort: 'created_at', sortDir: 'desc', total: 2 });
  });

  it('paints Date, Name, SKU, Type, Quantity with its sign, Balance, Reason and Reference', async () => {
    const s = await setup();
    await s.show(LEDGER);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['created_at', 'Date', true],
      ['product_name', 'Name', false],
      ['sku', 'SKU', false],
      ['movement_type', 'Type', true],
      ['qty', 'Quantity', true],
      ['stock_after', 'Balance', true],
      ['reason', 'Reason', false],
      ['reference', 'Reference', false],
    ]);
    const cells = (row: number) => s.rows()[row].text();
    expect(cells(0)).toContain(formatDateTime('2026-10-13T10:00:00Z', 'en'));
    expect(cells(0)).toMatch(/Coffee.*CAF-1.*Count.*-1\.5.*8\.5.*Broken bottle/);
    expect(cells(1)).toMatch(/Reception.*\+10.*10.*ALB-2026-0001/);
  });

  it('names every type as the old module did', async () => {
    const s = await setup();
    const types = ['initial', 'reception', 'sale', 'void', 'count', 'write_off', 'refund'];
    await s.show(page(types.map((type, i) => movement(`m${i}`, type, '1.000', '1.000'))));
    expect(s.wrapper.findAll('[data-testid="inventory-movement-type"]').map((c) => c.text())).toEqual([
      'Initial',
      'Reception',
      'Sale',
      'Void',
      'Count',
      'Decrease',
      'Refund',
    ]);
  });

  it('searches on the server, from the first page', async () => {
    const s = await setup();
    await s.show(page(LEDGER.rows, 120));
    await s.testid('inventory-movements-page-next').trigger('click');
    await flush();
    const bar = s.testid('inventory-movements-search').element as HTMLElement & { value?: string };
    bar.value = ' 20261004-0002 ';
    bar.dispatchEvent(new CustomEvent('ionInput', { detail: { value: ' 20261004-0002 ' } }));
    await flush();
    expect(s.params('inventory.movement.list')).toEqual([{ search: '20261004-0002', sort: '-created_at', limit: 50, offset: 0 }]);
  });

  it('filters by type («All types» drops it) and by reference', async () => {
    const s = await setup();
    await s.show(LEDGER);
    const select = s.testid('inventory-movements-type-filter');
    expect(select.attributes('aria-label')).toBe('Filter by type');
    expect(select.findAll('ion-select-option').map((o) => o.text())).toEqual([
      'All types',
      'Initial',
      'Reception',
      'Sale',
      'Void',
      'Count',
      'Decrease',
      'Refund',
    ]);
    await s.pick('inventory-movements-type-filter', 'count');
    expect(s.params('inventory.movement.list')).toEqual([{ movement_type: 'count', sort: '-created_at', limit: 50, offset: 0 }]);
    await s.pick('inventory-movements-reference-filter', ' ALB ', 'ionInput');
    expect(s.params('inventory.movement.list')).toEqual([{ movement_type: 'count', reference: 'ALB', sort: '-created_at', limit: 50, offset: 0 }]);
    await s.pick('inventory-movements-type-filter', 'all');
    expect(s.params('inventory.movement.list')).toEqual([{ reference: 'ALB', sort: '-created_at', limit: 50, offset: 0 }]);
  });

  it('sorts on the server by the column picked', async () => {
    const s = await setup();
    await s.show(LEDGER);
    s.table().vm.$emit('sortChange', { sort: 'qty', dir: 'asc' });
    await flush();
    expect(s.params('inventory.movement.list')).toEqual([{ sort: 'qty', limit: 50, offset: 0 }]);
  });

  it('an empty ledger says where movements come from; an empty search says how a sale is found', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.prop('emptyMessage')).toBe(
      'No movements yet. They appear when you use Receive stock or Count stock on a product in Products, and with every sale.',
    );
    await s.pick('inventory-movements-type-filter', 'sale');
    await s.onNewStream(page([]));
    expect(s.prop('emptyMessage')).toBe(
      'No movement matches the search or the filters. A sale is found by the number of its ticket, invoice or sale.',
    );
  });

  it('a new movement arrives through the stream (a reception elsewhere)', async () => {
    const s = await setup();
    await s.show(LEDGER);
    await s.show(page([movement('m3', 'reception', '5.000', '13.500'), ...LEDGER.rows]), 2);
    expect(s.rows()).toHaveLength(3);
  });

  it('a failed load says so with Retry', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'inventory.movement.list'), 'inventory.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg inventory.boom');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.testid('inventory-movements-retry').trigger('click');
    expect(reconnect).toHaveBeenCalled();
  });

  it('when the app is not active says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'inventory.movement.list'), 'app_inactive'));
    await flush();
    expect(s.testid('inventory-movements-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
  });

  it('is read only for everyone: no create, no row actions; an employee reads it too', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(LEDGER);
    expect(s.prop('addable')).toBe(false);
    expect(s.prop('actions')).toEqual([]);
    expect(s.rows()).toHaveLength(2);
  });

  it('formats nothing by hand and has no OutfitKit tag', () => {
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(LEDGER);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual([
      'Fecha',
      'Nombre',
      'SKU',
      'Tipo',
      'Cantidad',
      'Saldo',
      'Motivo',
      'Referencia',
    ]);
    expect(s.rows()[0].text()).toMatch(/Recuento.*-1,5.*8,5/);
  });
});
