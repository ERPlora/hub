// A price list's detail (WORKBOOK «Pantallas · Tarifa (detalle)»; PRICING-F03 to F08): the live list —
// Code with «General», Customer group, Currency, Tax, Validity and Status, with Edit, Make general and
// Deactivate / Activate for whoever manages — and its «Prices» in a server-side DataTable: Item, Type,
// SKU, From (with its unit), Price and Catalog price, «Search product or service…», 50 a page by item.
// «+» adds a price, a row is edited or removed (asking first). A list that does not exist says so.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { priceItem, priceList } from '../__tests__/fixtures';
import { click, EMPLOYEE, errorFrame, flush, mountPricing, type MountOptions, page, settle } from '../__tests__/mount-pricing';
import ListConfirm from '../components/ListConfirm.vue';
import PriceItemFormModal from '../components/PriceItemFormModal.vue';
import PriceListFormModal from '../components/PriceListFormModal.vue';
import ListDetailPage from './ListDetailPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const LIST = 'pricing.price_list.get';
const ITEMS = 'pricing.price_item.list';
const VIP = priceList({ tax_included: true, valid_from: '2026-07-01' });
const SHAMPOO = priceItem();
const BULK = priceItem({ id: 'i2', min_quantity: '10.000', price: 1000 });
const HAIRCUT = priceItem({ id: 'i3', kind: 'service', product_id: null, service_id: 's1', name: 'Haircut', sku: null, unit: null, base_price: null, price: 1500 });

async function setup(options: MountOptions = {}) {
  const m = await mountPricing(ListDetailPage, { path: '/pricing/lists/l1', props: { id: 'l1' }, ...options });
  await m.live();
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="pricing-items-row"]');
  const cells = (i: number) => rows()[i].findAll('[role="cell"]').map((c) => c.text().trim());
  const summary = () => m.find('pricing-detail-summary').findAll('dd').map((d) => d.text().trim());
  return { ...m, table, prop, rows, cells, summary };
}

describe('ListDetailPage', () => {
  it('follows the list and its prices by item, 50 from the first', async () => {
    const s = await setup();
    expect(s.params(LIST)).toEqual([{ id: 'l1' }]);
    expect(s.params(ITEMS)).toEqual([{ price_list_id: 'l1', sort: 'name', dir: 'asc', limit: 50, offset: 0 }]);
    await s.result(LIST, VIP);
    expect(s.wrapper.findComponent(AppPage).props()).toMatchObject({ title: 'VIP members', backHref: '/pricing/lists' });
    expect(s.summary()).toEqual(['VIP', 'VIP', 'EUR', 'Tax included', 'From Jul 1, 2026', 'Active']);
  });

  it('paints Item, Type, SKU, From with its unit, Price and Catalog price', async () => {
    const s = await setup();
    await s.result(LIST, VIP);
    await s.result(ITEMS, page([HAIRCUT, SHAMPOO, BULK]));
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Item'],
      ['kind', 'Type'],
      ['sku', 'SKU'],
      ['min_quantity', 'From'],
      ['price', 'Price'],
      ['base_price', 'Catalog price'],
    ]);
    expect(s.cells(0).slice(0, 6)).toEqual(['Haircut', 'Service', '—', '1', '€15.00', '—']);
    expect(s.cells(2).slice(0, 6)).toEqual(['Shampoo', 'Product', 'SH-1', '10 ud', '€10.00', '€15.00']);
    expect(s.prop('searchPlaceholder')).toBe('Search product or service…');
  });

  it('paints the prices of a list in another currency in that currency', async () => {
    const s = await setup();
    await s.result(LIST, priceList({ currency: 'USD' }));
    await s.result(ITEMS, page([SHAMPOO]));
    expect(s.cells(0)[4]).toBe('$12.00');
  });

  it('filters by type and searches and sorts on the server', async () => {
    const s = await setup();
    await s.result(LIST, VIP);
    // The Type filter waits behind the toolbar's funnel, as in the old table (PLAN-MIGRATIONS §13).
    expect(s.prop('filterable')).toBe(true);
    s.table().vm.$emit('filtersChange', { kind: 'service' });
    s.table().vm.$emit('sortChange', { sort: 'price', dir: 'desc' });
    s.table().vm.$emit('update:search', 'hair');
    await flush();
    expect(s.params(ITEMS)).toEqual([
      { price_list_id: 'l1', kind: 'service', search: 'hair', sort: 'price', dir: 'desc', limit: 50, offset: 0 },
    ]);
  });

  it('a deactivated list offers no new price nor Edit, only Remove', async () => {
    const s = await setup();
    await s.result(LIST, priceList({ is_active: false }));
    await s.result(ITEMS, page([SHAMPOO]));
    expect(s.prop('addable')).toBe(false);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['remove']);
    expect(s.prop('rowClickable')).toBe(false);
  });

  it('a list without prices says so', async () => {
    const s = await setup();
    await s.result(LIST, VIP);
    await s.result(ITEMS, page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('This price list has no prices yet.');
  });

  it('«+» adds a price, Edit changes one and Remove asks first', async () => {
    const s = await setup();
    await s.result(LIST, VIP);
    await s.result(ITEMS, page([SHAMPOO]));
    s.table().vm.$emit('add');
    await flush();
    expect(s.wrapper.findComponent(PriceItemFormModal).props()).toMatchObject({ open: true, priceListId: 'l1', item: null });
    s.table().vm.$emit('action', { actionId: 'edit', row: SHAMPOO });
    await flush();
    expect(s.wrapper.findComponent(PriceItemFormModal).props('item')).toEqual(SHAMPOO);
    s.table().vm.$emit('action', { actionId: 'remove', row: SHAMPOO });
    await settle();
    expect(s.inDoc('pricing-items-remove')?.textContent).toContain('The price of Shampoo from 1 ud will be removed.');
    s.answer(200, { id: 'i1' });
    await click(s.inDoc('pricing-items-remove-submit'));
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/price_items/remove', query: {}, body: { id: 'i1' } }]);
  });

  it('the list is edited, made general or switched from its detail', async () => {
    const s = await setup();
    const own = priceList({ customer_group_id: null, customer_group_name: null });
    await s.result(LIST, own);
    await click(s.find('pricing-detail-edit').element);
    expect(s.wrapper.findComponent(PriceListFormModal).props()).toMatchObject({ open: true, priceList: own });
    await click(s.find('pricing-detail-default').element);
    expect(s.wrapper.findComponent(ListConfirm).props()).toMatchObject({ action: 'default', list: own });
    await click(s.find('pricing-detail-deactivate').element);
    expect(s.wrapper.findComponent(ListConfirm).props('action')).toBe('deactivate');
    await s.result(LIST, { ...own, is_active: false }, {}, 2);
    expect(s.find('pricing-detail-deactivate').exists()).toBe(false);
    s.answer(200, own);
    await click(s.find('pricing-detail-activate').element);
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/pricing/price_lists/activate', query: {}, body: { id: 'l1' } }]);
  });

  it('a list in another currency cannot be made general', async () => {
    const s = await setup();
    await s.result(LIST, priceList({ customer_group_id: null, customer_group_name: null, currency: 'USD' }));
    expect(s.find('pricing-detail-default').exists()).toBe(false);
  });

  it('the general list cannot be made general again nor deactivated', async () => {
    const s = await setup();
    await s.result(LIST, priceList({ is_default: true, customer_group_id: null, customer_group_name: null }));
    expect(s.summary()[1]).toBe('Everybody');
    expect(s.find('pricing-detail-code').text()).toContain('General');
    expect([s.find('pricing-detail-default').exists(), s.find('pricing-detail-deactivate').exists()]).toEqual([false, false]);
  });

  it('a group deleted in Customers says so', async () => {
    const s = await setup();
    await s.result(LIST, priceList({ customer_group_id: 'g9', customer_group_name: null }));
    expect(s.summary()[1]).toBe('Deleted group');
  });

  it('a list that does not exist says so, with Back', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(LIST), 'pricing.price_list_not_found'));
    await flush();
    expect(s.find('pricing-detail-not-found').text()).toContain('This price list does not exist');
    expect(s.wrapper.findComponent(DataTable as unknown as Component).exists()).toBe(false);
  });

  it('an employee reads the list and its prices without acting', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.result(LIST, VIP);
    await s.result(ITEMS, page([SHAMPOO]));
    expect([s.find('pricing-detail-edit').exists(), s.prop('addable'), s.prop('actions')]).toEqual([false, false, []]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.result(LIST, VIP);
    await s.result(ITEMS, page([SHAMPOO]));
    expect(s.summary()[3]).toBe('Impuesto incluido');
    expect(s.cells(0).slice(1, 2)).toEqual(['Producto']);
  });
});
