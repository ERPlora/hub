// The «Price lists» table of Price Lists (PRICING-F01 to F05): the live `pricing.price_list.list` in a
// server-side DataTable — Code (with «General»), Name, Currency, Customer group, Tax, Validity, Prices and
// Status —, «Search code or name…», column filters, 50 a page by name. A row and its «Open» open the list;
// whoever manages gets «+», Edit, Make general, Deactivate and Activate, each where it applies.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { priceList } from '../__tests__/fixtures';
import { EMPLOYEE, flush, mountPricing, type MountOptions, page } from '../__tests__/mount-pricing';
import ListConfirm from './ListConfirm.vue';
import PriceListFormModal from './PriceListFormModal.vue';
import PriceListsTable from './PriceListsTable.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'pricing.price_list.list';
const GENERAL = priceList({ id: 'l0', code: 'GEN', name: 'General', customer_group_id: null, customer_group_name: null, is_default: true, item_count: 5 });
const VIP = priceList({ tax_included: true, valid_from: '2026-07-01', valid_until: '2026-08-31' });
const OLD = priceList({ id: 'l2', code: 'OLD', name: 'Old', customer_group_id: null, customer_group_name: null, is_active: false, currency: 'USD', tax_included: false, item_count: 0 });

type Action = { id: string; label: string; hidden?: (row: unknown) => boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountPricing(PriceListsTable, options);
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="pricing-lists-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const shownFor = (row: unknown) => prop<Action[]>('actions').filter((a) => !a.hidden?.(row)).map((a) => a.id);
  return { ...m, table, prop, rows, cells, shownFor, show: (data: unknown) => m.result(OP, data) };
}

describe('PriceListsTable', () => {
  it('follows the price lists by name, 50 from the first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
    await s.show(page([GENERAL, VIP]));
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, testid: 'pricing-lists', total: 2 });
    expect(s.prop('searchPlaceholder')).toBe('Search code or name…');
    expect(s.prop<{ add: string }>('labels').add).toBe('New price list');
  });

  it('paints Code with «General», Name, Currency, Customer group, Tax, Validity, Prices and Status', async () => {
    const s = await setup();
    await s.show(page([GENERAL, VIP, OLD]));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['code', 'Code'],
      ['name', 'Name'],
      ['currency', 'Currency'],
      ['customer_group_name', 'Customer group'],
      ['tax_included', 'Tax'],
      ['validity', 'Validity'],
      ['item_count', 'Prices'],
      ['status', 'Status'],
    ]);
    expect(s.cells(0).slice(0, 8)).toEqual(['GEN General', 'General', 'EUR', 'Everybody', 'Business default', 'Always', '5', 'Active']);
    expect(s.cells(1).slice(3, 6)).toEqual(['VIP', 'Tax included', 'Jul 1, 2026 – Aug 31, 2026']);
    expect(s.cells(2).slice(2, 8)).toEqual(['USD', '—', 'Tax excluded', 'Always', '0', 'Inactive']);
  });

  it('a list whose group was deleted in Customers says so, and offers no «Make general» until it is edited', async () => {
    const s = await setup();
    const orphan = priceList({ customer_group_id: 'g9', customer_group_name: null });
    await s.show(page([orphan]));
    expect(s.cells(0)[3]).toBe('Deleted group');
    expect(s.shownFor(orphan)).toEqual(['open', 'edit', 'deactivate']);
  });

  it('filters by column and searches and sorts on the server', async () => {
    const s = await setup();
    s.table().vm.$emit('filtersChange', { code: 'vi', currency: 'eu', customer_group_id: 'g1', tax_basis: 'business', status: 'all' });
    s.table().vm.$emit('sortChange', { sort: 'code', dir: 'desc' });
    s.table().vm.$emit('update:search', 'vip');
    await flush();
    expect(s.params(OP)).toEqual([
      { code: 'vi', currency: 'eu', customer_group_id: 'g1', tax_basis: 'business', status: 'all', search: 'vip', sort: 'code', dir: 'desc', limit: 50, offset: 0 },
    ]);
  });

  it('no list at all says «No price lists.»', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No price lists.');
  });

  it('offers each action where it applies, and opens a list by its row or «Open»', async () => {
    const s = await setup();
    await s.show(page([GENERAL, VIP, OLD]));
    expect(s.shownFor(GENERAL)).toEqual(['open', 'edit']);
    expect(s.shownFor(priceList({ customer_group_id: null }))).toEqual(['open', 'edit', 'makeDefault', 'deactivate']);
    expect(s.shownFor(VIP)).toEqual(['open', 'edit', 'deactivate']);
    expect(s.shownFor(OLD)).toEqual(['open', 'edit', 'activate']);
    // A list in another currency cannot be the general one (the till sells in euros).
    expect(s.shownFor(priceList({ customer_group_id: null, currency: 'USD' }))).toEqual(['open', 'edit', 'deactivate']);
    s.table().vm.$emit('rowClick', VIP);
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/pricing/lists/l1');
    s.table().vm.$emit('action', { actionId: 'open', row: GENERAL });
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/pricing/lists/l0');
  });

  it('«+» and Edit open the form; Make general and Deactivate ask first; Activate runs at once', async () => {
    const s = await setup();
    await s.show(page([GENERAL, VIP, OLD]));
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(PriceListFormModal).props()).toMatchObject({ open: true, priceList: null });
    s.table().vm.$emit('action', { actionId: 'edit', row: VIP });
    await flush();
    expect(s.wrapper.findComponent(PriceListFormModal).props('priceList')).toEqual(VIP);
    s.table().vm.$emit('action', { actionId: 'deactivate', row: VIP });
    await flush();
    expect(s.wrapper.findComponent(ListConfirm).props()).toMatchObject({ action: 'deactivate', list: VIP });
    s.answer(200, { ...OLD, is_active: true });
    s.table().vm.$emit('action', { actionId: 'activate', row: OLD });
    await flush();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/price_lists/activate', query: {}, body: { id: 'l2' } }]);
  });

  it('an employee reads the lists and only opens them', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page([VIP]));
    expect(s.prop('addable')).toBe(false);
    expect(s.shownFor(VIP)).toEqual(['open']);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page([GENERAL]));
    expect(s.cells(0).slice(3, 8)).toEqual(['Todos', 'Según el negocio', 'Siempre', '5', 'Activa']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar código o nombre…');
  });
});
