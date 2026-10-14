// Inventory → Products (WORKBOOK «Productos», INVENTORY-F01–F05, F08, F09, F11, F13–F15, F20): the
// live `inventory.product.list` — Name, SKU, Price, Stock («—» without stock control) and Status (a
// switch, «Yes»/«No» for whoever cannot change products, or «Not configured · Missing tax category»)
// —, «Search product…», sort by column, filters (status, name, SKU, price and stock ranges), 50 a page.
// «+», import and export CSV, each for whoever may; per row «Details», «Receive stock», «Count stock»,
// «Write off stock» (physical products, with the permission to move stock), «Edit» and «Delete». A
// row opens its sheet. A refused row action is said above the table.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonToggle } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { type ApiCall, EMPLOYEE, errorFrame, flush, type MountOptions, mountInventory, ok, page, product, refusal, subId, UNITS } from '../__tests__/mount-inventory';
import CsvButtons from '../components/CsvButtons.vue';
import ImportPreviewModal from '../components/ImportPreviewModal.vue';
import ProductDetailModal from '../components/ProductDetailModal.vue';
import ProductFilters from '../components/ProductFilters.vue';
import ProductFormModal from '../components/ProductFormModal.vue';
import StockModal from '../components/StockModal.vue';
import { formatMoney } from '../lib/format';
import ProductsPage from './ProductsPage.vue';
import source from './ProductsPage.vue?raw';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), save: vi.fn() }));
vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  useConfirm: () => ({ confirm: mocks.confirm }),
}));
vi.mock('../lib/download', () => ({ saveTextFile: mocks.save }));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  mocks.confirm.mockReset();
  mocks.save.mockReset();
  document.body.innerHTML = '';
});

const COFFEE = product();
const MASSAGE = product({ id: 'p2', name: 'Massage', sku: 'SRV-1', product_type: 'service', tracks_stock: false, stock: '0.000', price: 3000 });
const OLD = product({ id: 'p3', name: 'Old wine', sku: 'OLD-1', needs_tax_setup: true, tax_category_key: null, is_active: true });
const LIST = page([COFFEE, MASSAGE, OLD], 3);

/** The API of the page: units, the hub's stock setting; anything else answers `answer`. */
function api(answer: (call: ApiCall) => Response = () => ok({})) {
  return (call: ApiCall): Response => {
    const path = call.url.split('?')[0];
    if (path === '/api/inventory/units') return ok(UNITS);
    if (path === '/api/inventory/config') return ok({ allow_sell_without_stock: false, low_stock_threshold: 10, track_stock: true });
    return answer(call);
  };
}

async function setup(options: MountOptions = {}, answer?: (call: ApiCall) => Response) {
  const m = await mountInventory(ProductsPage, { path: '/inventory/products', api: api(answer), ...options });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="inventory-products-row"]');
  async function act(actionId: string, row: unknown = COFFEE) {
    table().vm.$emit('action', { actionId, row });
    await flush();
  }
  async function onNewStream(data: unknown) {
    await m.clock.advance(150);
    await m.result(m.net.lastStream(), 'inventory.product.list', data);
  }
  return { ...m, call, testid, table, prop, rows, act, onNewStream, show: (data: unknown, rev?: number) => m.result(call, 'inventory.product.list', data, rev) };
}

describe('ProductsPage: the list', () => {
  it('is the inventory page on its Products tab, following the products by name, 50 a page', async () => {
    const s = await setup();
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Inventory');
    expect(s.params('inventory.product.list')).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    await s.show(LIST);
    expect(s.table().props()).toMatchObject({ serverSide: true, searchable: true, rowClickable: true, pageSize: 50, total: 3, addable: true });
    expect(s.prop('searchPlaceholder')).toBe('Search product…');
  });

  it('paints Name, SKU, Price, Stock («—» without stock control) and Status, sortable but Status', async () => {
    const s = await setup();
    await s.show(LIST);
    expect(s.prop<Array<{ key: string; label: string; sortable?: boolean }>>('columns').map((c) => [c.key, c.label, !!c.sortable])).toEqual([
      ['name', 'Name', true],
      ['sku', 'SKU', true],
      ['price', 'Price', true],
      ['stock', 'Stock', true],
      ['status', 'Status', false],
    ]);
    expect(s.rows()[0].text()).toContain(formatMoney(220, 'en'));
    // The stock has its own hook, exact: a SKU may contain the same figure.
    expect(s.wrapper.findAll('[data-testid="inventory-product-stock"]').map((c) => c.text())).toEqual(['5', '—', '5']);
  });

  it('Status: a switch for whoever can change products; «Not configured» opens the edit form', async () => {
    const s = await setup();
    await s.show(LIST);
    const toggles = s.wrapper.findAllComponents(IonToggle);
    expect(toggles.map((t) => [t.attributes('data-testid'), t.props('modelValue')])).toEqual([
      ['inventory-products-active-p1', true],
      ['inventory-products-active-p2', true],
    ]);
    const chip = s.testid('inventory-products-unconfigured-p3');
    expect(chip.find('span').text()).toBe('Not configured · Missing tax category');
    await chip.trigger('click');
    await flush();
    const form = s.wrapper.findComponent(ProductFormModal);
    expect([form.props('open'), (form.props('product') as { id: string }).id]).toEqual([true, 'p3']);
  });

  it('the switch activates or deactivates the product; a refusal is said above the table', async () => {
    const s = await setup({}, () => ok(COFFEE));
    await s.show(LIST);
    await s.wrapper.findAllComponents(IonToggle)[0].setValue(false);
    await flush();
    expect(s.body(s.calls('/api/inventory/products/update')[0])).toEqual({ id: 'p1', is_active: false });
    s.net.onApi(api(() => refusal(403, 'permission_denied', 'You do not have permission.')));
    await s.wrapper.findAllComponents(IonToggle)[0].setValue(true);
    await flush();
    expect(s.testid('inventory-products-page-error').text()).toContain('You do not have permission.');
  });

  it('a switch the server refuses goes back to where it was', async () => {
    const s = await setup({}, () => refusal(403, 'permission_denied', 'You do not have permission.'));
    await s.show(LIST);
    const element = () => s.testid('inventory-products-active-p1').element as HTMLElement & { checked?: boolean };
    // What a tap does: the switch flips, then Ionic says so.
    element().checked = false;
    element().dispatchEvent(new CustomEvent('ionChange', { detail: { checked: false } }));
    await flush();
    await flush();
    expect(s.calls('/api/inventory/products/update')).toHaveLength(1);
    expect(s.testid('inventory-products-page-error').text()).toContain('You do not have permission.');
    expect(element().checked).toBe(true);
  });

  it('searches, sorts and filters on the server, from the first page', async () => {
    const s = await setup();
    await s.show(page(LIST.rows, 120));
    await s.testid('inventory-products-page-next').trigger('click');
    await flush();
    s.table().vm.$emit('sortChange', { sort: 'price', dir: 'desc' });
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ sort: '-price', limit: 50, offset: 0 }]);
    s.wrapper.findComponent(ProductFilters).vm.$emit('update:modelValue', { name: 'caf', priceMin: '2,20' });
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ name: 'caf', price_min: 220, sort: '-price', limit: 50, offset: 0 }]);
  });

  it('the status filter: All, Yes, No and Not configured', async () => {
    const s = await setup();
    await s.show(LIST);
    const select = s.testid('inventory-products-status-filter');
    expect(select.attributes('aria-label')).toBe('Filter by status');
    expect(select.findAll('ion-select-option').map((o) => o.text())).toEqual(['All', 'Yes', 'No', 'Not configured']);
    select.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'needs_tax_setup' } }));
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ status: 'needs_tax_setup', sort: 'name', limit: 50, offset: 0 }]);
  });

  it('opened from the till\'s warning (?status=unconfigured) lists only what lacks a tax category', async () => {
    const s = await setup({ path: '/inventory/products?status=unconfigured' });
    expect(s.params('inventory.product.list')).toEqual([{ status: 'needs_tax_setup', sort: 'name', limit: 50, offset: 0 }]);
  });

  it('a new ?status= while the page is open applies its filter from the first page', async () => {
    const s = await setup();
    await s.show(page(LIST.rows, 120));
    await s.testid('inventory-products-page-next').trigger('click');
    await flush();
    await s.router.push('/inventory/products?status=unconfigured');
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ status: 'needs_tax_setup', sort: 'name', limit: 50, offset: 0 }]);
    expect((s.testid('inventory-products-status-filter').element as HTMLElement & { value?: unknown }).value).toBe('needs_tax_setup');
    await s.router.push('/inventory/products');
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
  });

  it('empty says «No products»; filtered and empty says nothing matches', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No products');
    s.wrapper.findComponent(ProductFilters).vm.$emit('update:modelValue', { sku: 'zzz' });
    await flush();
    await s.onNewStream(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No product matches the search or the filters.');
  });

  it('a failed load says so with Retry; an inactive app says so instead of the table', async () => {
    const s = await setup();
    s.call.push(errorFrame(subId(s.client, 'inventory.product.list'), 'inventory.boom'));
    await flush();
    expect(s.prop('error')).toBe('msg inventory.boom');
    const t = await setup();
    t.call.push(errorFrame(subId(t.client, 'inventory.product.list'), 'app_inactive'));
    await flush();
    expect(t.testid('inventory-products-inactive').exists()).toBe(true);
    expect(t.table().exists()).toBe(false);
  });
});

describe('ProductsPage: actions', () => {
  it('per row: Details, Receive, Count, Write off (not for a service), Edit, Delete', async () => {
    const s = await setup();
    await s.show(LIST);
    const actions = s.prop<Array<{ id: string; label: string; hidden?: (row: unknown) => boolean; menuOnly?: boolean }>>('actions');
    expect(actions.map((a) => [a.id, a.label, !!a.menuOnly])).toEqual([
      ['detail', 'Details', false],
      ['receive', 'Receive stock', false],
      ['count', 'Count stock', false],
      ['write_off', 'Write off stock', true],
      ['edit', 'Edit', false],
      ['delete', 'Delete', true],
    ]);
    const stock = actions.filter((a) => ['receive', 'count', 'write_off'].includes(a.id));
    expect(stock.map((a) => [a.hidden?.(COFFEE), a.hidden?.(MASSAGE)])).toEqual([
      [false, true],
      [false, true],
      [false, true],
    ]);
    // Nothing to write off from an article that does not track its stock (WORKBOOK INVENTORY-F15).
    const untracked = product({ id: 'p4', tracks_stock: false, track_stock: false });
    expect(stock.map((a) => [a.id, a.hidden?.(untracked)])).toEqual([
      ['receive', false],
      ['count', false],
      ['write_off', true],
    ]);
  });

  it('a row and «Details» open the sheet; its stock buttons open their dialog', async () => {
    const s = await setup();
    await s.show(LIST);
    await s.rows()[0].trigger('click');
    await flush();
    const detail = s.wrapper.findComponent(ProductDetailModal);
    expect([detail.props('open'), (detail.props('product') as { id: string }).id]).toEqual([true, 'p1']);
    detail.vm.$emit('stock', 'count');
    await flush();
    const stock = s.wrapper.findComponent(StockModal);
    expect([detail.props('open'), stock.props('open'), stock.props('kind'), (stock.props('product') as { id: string }).id]).toEqual([
      false,
      true,
      'count',
      'p1',
    ]);
  });

  it('«Receive stock», «Count stock» and «Write off stock» open their dialog with the live product', async () => {
    const s = await setup();
    await s.show(LIST);
    for (const kind of ['receive', 'count', 'write_off']) {
      await s.act(kind);
      const stock = s.wrapper.findComponent(StockModal);
      expect([stock.props('open'), stock.props('kind')]).toEqual([true, kind]);
    }
    await s.show(page([product({ stock: '9.000' }), MASSAGE, OLD], 3), 2);
    expect((s.wrapper.findComponent(StockModal).props('product') as { stock: string }).stock).toBe('9.000');
  });

  it('«+» opens «New product»; «Edit» opens it with the product; the units and the hub setting go along', async () => {
    const s = await setup();
    await s.show(LIST);
    await s.testid('inventory-products-add').trigger('click');
    await flush();
    const form = s.wrapper.findComponent(ProductFormModal);
    expect([form.props('open'), form.props('product'), (form.props('units') as unknown[]).length, form.props('hubTracksStock')]).toEqual([
      true,
      null,
      8,
      true,
    ]);
    await s.act('edit');
    expect((s.wrapper.findComponent(ProductFormModal).props('product') as { id: string }).id).toBe('p1');
  });

  it('«Delete» confirms «Delete product» and deletes; a refusal is said above the table', async () => {
    const s = await setup({}, () => ok({ id: 'p1' }));
    await s.show(LIST);
    mocks.confirm.mockResolvedValue(true);
    await s.act('delete');
    expect(mocks.confirm).toHaveBeenCalledWith({
      title: 'Delete product',
      message: 'Coffee (CAF-1) — will be removed from the catalog (soft delete; its stock movements are kept)',
      confirmLabel: 'Delete',
      tone: 'danger',
    });
    expect(s.body(s.calls('/api/inventory/products/delete')[0])).toEqual({ id: 'p1' });
    s.net.onApi(api(() => refusal(404, 'not_found', 'Not found')));
    await s.act('delete');
    expect(s.testid('inventory-products-page-error').text()).toContain('Not found');
  });

  it('whoever only views: no «+», no CSV, only «Details», «Yes»/«No» instead of the switch', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(LIST);
    expect(s.prop('addable')).toBe(false);
    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).toEqual(['detail']);
    expect(s.wrapper.findComponent(CsvButtons).props()).toMatchObject({ importable: false, exportable: false });
    expect(s.wrapper.findAllComponents(IonToggle)).toHaveLength(0);
    expect(s.testid('inventory-products-active-text-p1').text()).toBe('Yes');
    expect(s.calls('/api/inventory/config')).toHaveLength(0);
  });
});

describe('ProductsPage: import and export', () => {
  it('exports everything the search and filters find, with the file the server wrote', async () => {
    const s = await setup({}, () => ok({ filename: 'inventario-productos.csv', content_type: 'text/csv', content: '﻿Nombre;SKU\n' }));
    await s.show(LIST);
    s.wrapper.findComponent(ProductFilters).vm.$emit('update:modelValue', { sku: 'CAF' });
    await flush();
    s.wrapper.findComponent(CsvButtons).vm.$emit('export');
    await flush();
    expect(s.query(s.calls('/api/inventory/products/export')[0])).toEqual({ sku: 'CAF', sort: 'name' });
    expect(mocks.save).toHaveBeenCalledWith('inventario-productos.csv', '﻿Nombre;SKU\n', 'text/csv');
  });

  it('importing a file opens «Check the import» with its columns', async () => {
    const s = await setup({}, (call) =>
      call.url.startsWith('/api/tax/categories')
        ? ok(page([{ key: 'product.generic' }], 1, 1))
        : ok({ dry_run: true, total: 1, ready: 1, created: 0, skipped: 0, failed: 0, rows: [{ line: 2, key: 'CAF-1', status: 'ready', id: null, reason: '' }] }),
    );
    await s.show(LIST);
    s.wrapper.findComponent(CsvButtons).vm.$emit('import', 'Nombre;SKU\nCoffee;CAF-1\n');
    await flush();
    const preview = s.wrapper.findComponent(ImportPreviewModal);
    expect([preview.props('open'), preview.props('mapping'), preview.props('requiredMapped')]).toEqual([true, ['name', 'sku'], true]);
    preview.vm.$emit('cancel');
    await flush();
    expect(s.wrapper.findComponent(ImportPreviewModal).props('open')).toBe(false);
  });

  it('a file without rows says so above the table', async () => {
    const s = await setup();
    await s.show(LIST);
    s.wrapper.findComponent(CsvButtons).vm.$emit('import', 'Nombre;SKU\n');
    await flush();
    expect(s.testid('inventory-products-page-error').text()).toContain('The file has no rows to import.');
  });
});

describe('ProductsPage', () => {
  it('formats nothing by hand and has no OutfitKit tag', () => {
    expect(source).not.toMatch(/Intl\.|toLocale|new Date\(/);
    expect(source).not.toMatch(/<ok[-]/);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(LIST);
    expect(s.prop<Array<{ label: string }>>('columns').map((c) => c.label)).toEqual(['Nombre', 'SKU', 'Precio', 'Stock', 'Estado']);
    expect(s.prop('searchPlaceholder')).toBe('Buscar producto…');
    expect(s.testid('inventory-products-unconfigured-p3').find('span').text()).toBe('Sin configurar · Falta la categoría fiscal');
  });
});
