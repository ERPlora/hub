// Inventory → Products (WORKBOOK «Productos», INVENTORY-F01–F05, F08, F09, F11, F13–F15, F20): the
// live `inventory.product.list` — Name, SKU, Price, Stock («—» without stock control) and Status (a
// switch, «Yes»/«No» for whoever cannot change products, or «Not configured · Missing tax category»)
// —, «Search product…», sort by column, the filters behind the table's funnel (name, SKU, price and stock
// ranges, status), 50 a page.
// «+», import and export CSV, each for whoever may; per row «Details», «Receive stock», «Count stock»,
// «Write off stock» (physical products, with the permission to move stock), «Edit», «Mark sold out» or
// «Put back on sale» (INVENTORY-F29, the «Sold out» mark beside the switch) and «Delete». A row opens its
// sheet. A refused row action is said above the table.
import { DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { IonToggle } from '@ionic/vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'vue';

import { business, EMPLOYEE, errorFrame, flush, mountInventory, ok, page, POLISH, product, refusal, subId, UNITS, type ApiCall, type MountOptions } from '../__tests__/mount-inventory';
import CsvButtons from '../components/CsvButtons.vue';
import ImportPreviewModal from '../components/ImportPreviewModal.vue';
import ProductDetailModal from '../components/ProductDetailModal.vue';
import ProductFormModal from '../components/ProductFormModal.vue';
import StockModal from '../components/StockModal.vue';
import { formatMoney } from '../lib/format';
import ProductsPage from './ProductsPage.vue';
import source from './ProductsPage.vue?raw';
import { listFillProblems } from '../../../../frontend/testing/list-fill';

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
  /** What the table's funnel applies (`v-model:filters`): the filters by name, as typed. */
  async function filter(values: Record<string, string>) {
    table().vm.$emit('update:filters', values);
    await flush();
  }
  return { ...m, call, testid, table, prop, rows, act, onNewStream, filter, show: (data: unknown, rev?: number) => m.result(call, 'inventory.product.list', data, rev) };
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
    expect(s.rows()[0].text()).toContain(formatMoney(220, 'en', 'EUR'));
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
    // FIX-INVENTORY-PRODUCTS-UNCONFIGURED-CHIP-CLIPPED - Cut to «…» in a narrow column, its whole text stays on hand.
    expect(chip.attributes('title')).toBe('Not configured · Missing tax category');
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
    await s.filter({ name: 'caf', price_min: '2,20' });
    expect(s.params('inventory.product.list')).toEqual([{ name: 'caf', price_min: 220, sort: '-price', limit: 50, offset: 0 }]);
  });

  // flow: ninguno — FIX DataTable parte 2b-2 (PLAN-MIGRATIONS §13: filtros como en la vieja)
  it('filters behind the table funnel, on their columns: name, SKU, price and stock (as typed) and status', async () => {
    const s = await setup();
    await s.show(LIST);
    expect(s.prop('filterable')).toBe(true);
    type Filter = { type: string; key?: string; keys?: string[]; amount?: boolean; maxlength?: number; options?: Array<{ value: string; label: string }> };
    const columns = s.prop<Array<{ key: string; label: string; filter?: Filter }>>('columns');
    expect(columns.filter((c) => c.filter).map((c) => [c.label, c.filter?.type, c.filter?.keys, c.filter?.amount, c.filter?.maxlength])).toEqual([
      ['Name', 'text', undefined, undefined, 200],
      ['SKU', 'text', undefined, undefined, 64],
      ['Price', 'range', ['price_min', 'price_max'], true, undefined],
      ['Stock', 'range', ['stock_min', 'stock_max'], true, undefined],
      ['Status', 'select', undefined, undefined, undefined],
    ]);
    expect(columns.find((c) => c.key === 'status')?.filter?.options).toEqual([
      { value: 'active', label: 'Yes' },
      { value: 'inactive', label: 'No' },
      { value: 'needs_tax_setup', label: 'Not configured' },
      { value: 'sold_out', label: 'Sold out' },
    ]);
    // No control of its own beside the table: the status lives in the funnel, as in the old table.
    expect(s.testid('inventory-products-status-filter').exists()).toBe(false);
  });

  it('every filter of the funnel reaches the server with its own parameter, from the first page', async () => {
    const s = await setup();
    await s.show(page(LIST.rows, 120));
    await s.testid('inventory-products-page-next').trigger('click');
    await flush();
    await s.filter({ name: 'caf', sku: 'CAF', price_min: '12', price_max: '1.250,50', stock_min: '1,5', stock_max: '10', status: 'needs_tax_setup' });
    expect(s.params('inventory.product.list')).toEqual([
      { name: 'caf', sku: 'CAF', price_min: 1200, price_max: 125050, stock_min: '1.5', stock_max: '10', status: 'needs_tax_setup', sort: 'name', limit: 50, offset: 0 },
    ]);
  });

  it('the funnel panel applies on «Apply» and counts the filtered columns', async () => {
    const s = await setup();
    await s.show(LIST);
    await s.testid('inventory-products-filters-toggle').trigger('click');
    await flush();
    const panel = s.testid('inventory-products-filters-panel');
    const set = (name: string, event: string, value: string) =>
      panel.get(`[data-testid="inventory-products-filter-${name}"]`).element.dispatchEvent(new CustomEvent(event, { detail: { value } }));
    // A closed list opens as a popover: no «CANCEL»/«OK» of an alert in English (hub#1736).
    expect((panel.get('[data-testid="inventory-products-filter-status"]').element as HTMLElement & { interface?: string }).interface).toBe('popover');
    set('sku', 'ionInput', 'CAF');
    set('price_min', 'ionInput', '2,20');
    set('status', 'ionChange', 'inactive');
    await flush();
    expect(s.params('inventory.product.list'), 'the panel edits a draft: nothing is asked before «Apply»').toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    await panel.get('[data-testid="inventory-products-filters-apply"]').trigger('click');
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ sku: 'CAF', price_min: 220, status: 'inactive', sort: 'name', limit: 50, offset: 0 }]);
    expect(s.testid('inventory-products-filters-count').text()).toBe('3');
  });

  it('an amount or a quantity it cannot read is said under its end, and neither filters nor makes the list look filtered', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.prop('filterErrors')).toEqual({});
    await s.filter({ price_min: 'doce', price_max: '1.250', stock_min: 'x' });
    expect(s.prop('filterErrors')).toEqual({
      price_min: 'This is not an amount. Type a figure, for example 12.50.',
      price_max: `This amount can be read in two ways: «1.250» could be ${formatMoney(125000, 'en', 'EUR')} or ${formatMoney(125, 'en', 'EUR')}. Write the decimals so there is no doubt.`,
      stock_min: 'This is not a quantity. Type a figure with up to three decimals, for example 2.5.',
    });
    expect(s.params('inventory.product.list')).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No products');
  });

  it('a filter the server refused (a 422 of the list) is said under it, and the rows stay', async () => {
    const s = await setup();
    await s.show(LIST);
    s.call.push(`event: error\ndata: ${JSON.stringify({ id: subId(s.client, 'inventory.product.list'), error: { code: 'invalid_field', message: 'Invalid', fields: { price_max: 'Too big.' } } })}\n\n`);
    await flush();
    expect(s.prop('filterErrors')).toEqual({ price_max: 'Too big.' });
    expect(s.prop('error')).toBeUndefined();
  });

  it('opened from the till\'s warning (?status=unconfigured) lists only what lacks a tax category', async () => {
    const s = await setup({ path: '/inventory/products?status=unconfigured' });
    expect(s.params('inventory.product.list')).toEqual([{ status: 'needs_tax_setup', sort: 'name', limit: 50, offset: 0 }]);
    // The funnel shows it applied: «Status → Not configured», counted.
    expect(s.prop('filters')).toEqual({ status: 'needs_tax_setup' });
  });

  it('a new ?status= while the page is open applies its filter from the first page', async () => {
    const s = await setup();
    await s.show(page(LIST.rows, 120));
    await s.testid('inventory-products-page-next').trigger('click');
    await flush();
    await s.router.push('/inventory/products?status=unconfigured');
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ status: 'needs_tax_setup', sort: 'name', limit: 50, offset: 0 }]);
    expect(s.prop('filters')).toEqual({ status: 'needs_tax_setup' });
    await s.router.push('/inventory/products');
    await flush();
    expect(s.params('inventory.product.list')).toEqual([{ sort: 'name', limit: 50, offset: 0 }]);
  });

  it('empty says «No products»; filtered and empty says nothing matches', async () => {
    const s = await setup();
    await s.show(page([]));
    expect(s.wrapper.findComponent(EmptyState).props('heading')).toBe('No products');
    await s.filter({ sku: 'zzz' });
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
      ['sold_out', 'Mark sold out', true],
      ['back_on_sale', 'Put back on sale', true],
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

  it('INVENTORY-F29: «Mark sold out» on an article on sale, «Put back on sale» on a sold-out one', async () => {
    const s = await setup();
    await s.show(LIST);
    const actions = s.prop<Array<{ id: string; hidden?: (row: unknown) => boolean }>>('actions');
    const SOLD = product({ is_sold_out: true });
    expect(actions.filter((a) => ['sold_out', 'back_on_sale'].includes(a.id)).map((a) => [a.id, a.hidden?.(COFFEE), a.hidden?.(SOLD)])).toEqual([
      ['sold_out', false, true],
      ['back_on_sale', true, false],
    ]);
  });

  it('INVENTORY-F29: the actions mark and unmark it; the list comes back by the stream; a refusal is said above the table', async () => {
    const s = await setup({}, () => ok(product({ is_sold_out: true })));
    await s.show(LIST);
    await s.act('sold_out');
    expect(s.body(s.calls('/api/inventory/products/sold_out')[0])).toEqual({ id: 'p1', sold_out: true });
    await s.act('back_on_sale', product({ is_sold_out: true }));
    expect(s.body(s.calls('/api/inventory/products/sold_out')[1])).toEqual({ id: 'p1', sold_out: false });
    s.net.onApi(api(() => refusal(403, 'permission_denied', 'You do not have permission.')));
    await s.act('sold_out');
    expect(s.testid('inventory-products-page-error').text()).toContain('You do not have permission.');
  });

  it('INVENTORY-F29: a sold-out article keeps its switch on and shows «Sold out» beside it, also to whoever only views', async () => {
    const s = await setup();
    await s.show(page([product({ is_sold_out: true }), MASSAGE, OLD], 3));
    expect(s.testid('inventory-products-sold-out-p1').text()).toBe('Sold out');
    expect(s.testid('inventory-products-sold-out-p2').exists()).toBe(false);
    expect(s.wrapper.findAllComponents(IonToggle)[0].props('modelValue')).toBe(true);
    const viewer = await setup({ session: EMPLOYEE });
    await viewer.show(page([product({ is_sold_out: true })], 1));
    expect([viewer.testid('inventory-products-active-text-p1').text(), viewer.testid('inventory-products-sold-out-p1').text()]).toEqual(['Yes', 'Sold out']);
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
    await s.filter({ sku: 'CAF', price_min: '2' });
    s.wrapper.findComponent(CsvButtons).vm.$emit('export');
    await flush();
    expect(s.query(s.calls('/api/inventory/products/export')[0])).toEqual({ sku: 'CAF', price_min: '200', sort: 'name' });
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
    type Column = { key: string; filter?: { options?: Array<{ label: string }> } };
    expect(s.prop<Column[]>('columns').find((c) => c.key === 'status')?.filter?.options?.map((o) => o.label)).toEqual(['Sí', 'No', 'Sin configurar', 'Agotado']);
    expect(s.prop<Array<{ id: string; label: string }>>('actions').filter((a) => ['sold_out', 'back_on_sale'].includes(a.id)).map((a) => a.label)).toEqual([
      'Marcar agotado',
      'Volver a poner a la venta',
    ]);
    await s.filter({ price_min: 'doce', stock_max: 'x' });
    expect(s.prop('filterErrors')).toEqual({
      price_min: 'Esto no es un importe. Escribe una cifra, por ejemplo 12,50.',
      stock_max: 'Esto no es una cantidad. Escribe una cifra con hasta tres decimales, por ejemplo 2,5.',
    });
  });
});

describe('ProductsPage: the list fills the page (FIX-DATATABLE-HUB)', () => {
  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });

  it('a business in Poland reads its prices in zlotys (flow business-currency)', async () => {
    const s = await setup({ business: business(POLISH) });
    await s.show(LIST);
    expect(s.rows()[0].text()).toContain(formatMoney(220, 'en', 'PLN'));
    expect(s.rows()[0].text()).not.toContain('€');
  });
});
