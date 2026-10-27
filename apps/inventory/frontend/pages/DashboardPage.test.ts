// Inventory → Dashboard (WORKBOOK «Panel», INVENTORY-F17): the figures of `inventory.stock.get_summary`
// («Tracked products», «In stock», «Out of stock», «Low stock» — each a link to Products — and
// «Inventory value» at cost), the partial-value note when articles have no cost, and «Low stock
// products» (Name, SKU, Stock, Threshold), five a page, from the one with less. Everything live:
// a movement anywhere re-runs both queries on the server. Every state: loading, error with Retry,
// empty, app inactive, reconnecting; the footer tabbar of the inventory's sections.
import { DataTable, InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { BYE, EMPLOYEE, errorFrame, flush, type MountOptions, mountInventory, page, subId } from '../__tests__/mount-inventory';
import KpiTile from '../components/KpiTile.vue';
import { formatMoney } from '../lib/format';
import DashboardPage from './DashboardPage.vue';
import source from './DashboardPage.vue?raw';

const SUMMARY = {
  products_tracked: 12,
  products_in_stock: 9,
  products_out_of_stock: 3,
  products_low_stock: 4,
  products_without_cost: 0,
  stock_value: 123456,
  active_products: 14,
};

const low = (id: string, name: string, stock: string, threshold: string) => ({
  id,
  name,
  sku: `SKU-${id}`,
  stock,
  low_stock_threshold: threshold,
  unit: 'ud',
  price_quantity: '1.000',
  pricing_unit: 'ud',
});
const LOW = page([low('p1', 'Milk', '0.000', '10.000'), low('p2', 'Flour', '2.500', '5.000')], 2, 5);

async function setup(options: MountOptions = {}) {
  const m = await mountInventory(DashboardPage, options);
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const kpis = () => m.wrapper.findAllComponents(KpiTile).map((k) => [k.props('label'), k.props('value'), k.props('to') ?? null]);
  return {
    ...m,
    call,
    testid,
    table,
    prop,
    kpis,
    summary: (data: unknown, rev?: number) => m.result(call, 'inventory.stock.get_summary', data, rev),
    lowStock: (data: unknown, rev?: number) => m.result(call, 'inventory.product.list_low_stock', data, rev),
  };
}

describe('DashboardPage', () => {
  it('is the inventory page with its sections in the footer, the dashboard tab first', async () => {
    const s = await setup();
    const app = s.wrapper.findComponent(AppPage);
    expect(app.props('title')).toBe('Inventory');
    expect(app.props('tabsLabel')).toBe('Inventory sections');
    expect((app.props('tabs') as Array<{ id: string; to: string }>).map((t) => [t.id, t.to])).toEqual([
      ['dashboard', '/inventory/dashboard'],
      ['products', '/inventory/products'],
      ['movements', '/inventory/movements'],
      ['categories', '/inventory/categories'],
      ['settings', '/inventory/settings'],
    ]);
  });

  it('follows the summary and the low stock list (five, from the one with less), loading until they arrive', async () => {
    const s = await setup();
    expect(s.params('inventory.stock.get_summary')).toEqual([{}]);
    expect(s.params('inventory.product.list_low_stock')).toEqual([{ sort: 'stock', limit: 5, offset: 0 }]);
    expect(s.testid('inventory-dashboard-loading').text()).toBe('Loading…');
    await s.summary(SUMMARY);
    expect(s.testid('inventory-dashboard-loading').exists()).toBe(false);
  });

  it('paints the five figures; the first four lead to Products, the value is money at cost', async () => {
    const s = await setup();
    await s.summary(SUMMARY);
    expect(s.kpis()).toEqual([
      ['Tracked products', '12', '/inventory/products'],
      ['In stock', '9', '/inventory/products'],
      ['Out of stock', '3', '/inventory/products'],
      ['Low stock', '4', '/inventory/products'],
      ['Inventory value', formatMoney(123456, 'en', { currency: 'EUR', decimals: 2 }), null],
    ]);
    expect(s.wrapper.findAllComponents(KpiTile).at(-1)!.props('note')).toBe('at cost');
    expect(s.testid('inventory-dashboard-without-cost').exists()).toBe(false);
  });

  it('a figure that needs attention is painted in its tone; zero is neutral', async () => {
    const s = await setup();
    await s.summary({ ...SUMMARY, products_out_of_stock: 0 });
    const tones = s.wrapper.findAllComponents(KpiTile).map((k) => k.props('tone'));
    expect(tones).toEqual(['neutral', 'neutral', 'neutral', 'warning', 'neutral']);
  });

  it('warns that the value is partial when tracked articles have no cost', async () => {
    const s = await setup();
    await s.summary({ ...SUMMARY, products_without_cost: 2 });
    expect(s.testid('inventory-dashboard-without-cost').text()).toBe('2 products without recorded cost: the value shown is partial');
    await s.summary({ ...SUMMARY, products_without_cost: 1 }, 2);
    expect(s.testid('inventory-dashboard-without-cost').text()).toBe('1 product without recorded cost: the value shown is partial');
  });

  it('a new result replaces the figures without reloading (a sale elsewhere)', async () => {
    const s = await setup();
    await s.summary(SUMMARY);
    await s.summary({ ...SUMMARY, products_low_stock: 5 }, 2);
    expect(s.kpis()[3]).toEqual(['Low stock', '5', '/inventory/products']);
  });

  it('lists the products in low stock: Name, SKU, Stock and Threshold, exact quantities', async () => {
    const s = await setup();
    await s.summary(SUMMARY);
    await s.lowStock(LOW);
    expect(s.wrapper.get('.inventory-dashboard__low h2').text()).toBe('Low stock products');
    expect(s.prop<Array<{ key: string; label: string }>>('columns').map((c) => [c.key, c.label])).toEqual([
      ['name', 'Name'],
      ['sku', 'SKU'],
      ['stock', 'Stock'],
      ['low_stock_threshold', 'Threshold'],
    ]);
    expect(s.table().props()).toMatchObject({ serverSide: true, pageSize: 5, pageSizeChooser: false, total: 2, testid: 'inventory-dashboard-low-stock' });
    const cells = (id: string) => s.wrapper.findAll(`[data-testid="${id}"]`).map((c) => c.text());
    expect(cells('inventory-low-stock-name')).toEqual(['Milk', 'Flour']);
    expect(cells('inventory-low-stock-stock')).toEqual(['0', '2.5']);
    expect(cells('inventory-low-stock-threshold')).toEqual(['10', '5']);
  });

  it('pages the low stock list on the server', async () => {
    const s = await setup();
    await s.lowStock(page(LOW.rows, 12, 5));
    await s.testid('inventory-dashboard-low-stock-page-next').trigger('click');
    await flush();
    expect(s.params('inventory.product.list_low_stock')).toEqual([{ sort: 'stock', limit: 5, offset: 5 }]);
  });

  it('without products in low stock says so', async () => {
    const s = await setup();
    await s.lowStock(page([], 0, 5));
    expect(s.prop('emptyMessage')).toBe('No products in low stock.');
  });

  it('when the figures fail says so, and the table offers Retry, which asks again', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'inventory.stock.get_summary'), 'inventory.boom'));
    s.call.push(errorFrame(subId(s.client, 'inventory.product.list_low_stock'), 'inventory.boom'));
    await flush();
    const banner = s.wrapper.findAllComponents(InlineFeedback).find((b) => b.attributes('data-testid') === 'inventory-dashboard-stats-error')!;
    expect([banner.props('tone'), banner.text()]).toEqual(['danger', 'Inventory metrics could not be loaded.']);
    expect(s.prop('error')).toBe('msg inventory.boom');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.testid('inventory-dashboard-low-stock-retry').trigger('click');
    expect(reconnect).toHaveBeenCalled();
  });

  it('when the app is not active says so instead of the figures and the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'inventory.stock.get_summary'), 'app_inactive'));
    await flush();
    expect(s.testid('inventory-dashboard-inactive').exists()).toBe(true);
    expect(s.table().exists()).toBe(false);
    expect(s.wrapper.findAllComponents(KpiTile)).toHaveLength(0);
  });

  it('while the stream reconnects keeps the figures and shows «Reconnecting…»', async () => {
    const s = await setup();
    await s.summary(SUMMARY);
    s.call.push(BYE);
    await flush();
    expect(s.testid('inventory-dashboard-reconnecting').text()).toBe('Reconnecting…');
    expect(s.kpis()).toHaveLength(5);
  });

  it('an employee sees the same dashboard, without the Settings tab', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.summary(SUMMARY);
    expect((s.wrapper.findComponent(AppPage).props('tabs') as Array<{ id: string }>).map((t) => t.id)).not.toContain('settings');
    expect(s.kpis()).toHaveLength(5);
  });

  it('formats nothing by hand and has no OutfitKit tag', () => {
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.summary({ ...SUMMARY, products_without_cost: 3 });
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Inventario');
    expect(s.kpis().map((k) => k[0])).toEqual(['Productos seguidos', 'En stock', 'Agotados', 'Stock bajo', 'Valor de existencias']);
    expect(s.kpis()[4][1]).toBe(formatMoney(123456, 'es', { currency: 'EUR', decimals: 2 }));
    expect(s.testid('inventory-dashboard-without-cost').text()).toBe('3 productos sin coste registrado: el valor mostrado es parcial');
    await s.lowStock(page([], 0, 5));
    expect(s.prop('emptyMessage')).toBe('Sin productos en stock bajo.');
  });
});
