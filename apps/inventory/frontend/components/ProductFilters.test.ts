// The column filters of Products (WORKBOOK «Productos»: by name, SKU, price from/to and stock
// from/to; the status filter is its own select next to the search): the old table's funnel with the
// count of filters in use, opening a dialog. «Apply filters» narrows the list (amounts and quantities
// read as typed: «2,20» is 220 cents), «Clear filters» drops them. Until DataTable has column filters
// (UI-REQUESTS.md) it goes in the table's `filters` slot.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import ProductFilters, { filterParams } from './ProductFilters.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; label?: string; errorText?: string };

async function setup(modelValue: Record<string, string> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(ProductFilters, { props: { modelValue }, locale, attach: true });
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  async function type(id: string, value: string) {
    const field = el(id)!;
    field.value = value;
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function openPanel() {
    el('inventory-products-filters')!.click();
    await flush();
  }
  return { ...m, el, type, openPanel };
}

describe('ProductFilters', () => {
  it('a «Filters» button that counts the filters in use (a range once)', async () => {
    const s = await setup({ name: 'caf', priceMin: '1', priceMax: '3' });
    expect(s.el('inventory-products-filters')?.textContent).toContain('Filters');
    expect(s.el('inventory-products-filters-count')?.textContent?.trim()).toBe('2');
    const none = await setup();
    // Both mounts share the document: the second one is read inside its own wrapper.
    expect(none.wrapper.find('[data-testid="inventory-products-filters-count"]').exists()).toBe(false);
  });

  it('opens «Filter products» with name, SKU, price and stock ranges; «Apply filters» hands them over', async () => {
    const s = await setup();
    await s.openPanel();
    expect(s.el('inventory-products-filters-panel')?.getAttribute('aria-label')).toBe('Filter products');
    expect(['name', 'sku', 'price-min', 'price-max', 'stock-min', 'stock-max'].map((id) => s.el(`inventory-products-filter-${id}`)?.label)).toEqual([
      'Name',
      'SKU',
      'Price from',
      'Price to',
      'Stock from',
      'Stock to',
    ]);
    await s.type('inventory-products-filter-name', ' caf ');
    await s.type('inventory-products-filter-price-min', '2,20');
    s.el('inventory-products-filters-panel-submit')!.click();
    await flush();
    expect(s.wrapper.emitted('update:modelValue')).toEqual([[{ name: 'caf', priceMin: '2,20' }]]);
  });

  it('an amount that cannot be read is not applied', async () => {
    const s = await setup();
    await s.openPanel();
    await s.type('inventory-products-filter-price-max', 'abc');
    s.el('inventory-products-filters-panel-submit')!.click();
    await flush();
    expect(s.wrapper.emitted('update:modelValue')).toBeUndefined();
    expect(s.el('inventory-products-filter-price-max')?.errorText).toBe('This is not an amount. Type a figure, for example 12.50.');
  });

  it('«Clear filters» drops them all', async () => {
    const s = await setup({ sku: 'X' });
    await s.openPanel();
    s.el('inventory-products-filters-clear')!.click();
    await flush();
    expect(s.wrapper.emitted('update:modelValue')).toEqual([[{}]]);
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, 'es');
    expect(s.el('inventory-products-filters')?.textContent).toContain('Filtros');
  });
});

describe('filterParams', () => {
  it('reads the filters as the list query takes them: cents and exact quantities', () => {
    expect(filterParams({ name: 'caf', sku: 'C', priceMin: '2,20', priceMax: '10', stockMin: '0,5', stockMax: '3' })).toEqual({
      name: 'caf',
      sku: 'C',
      price_min: 220,
      price_max: 1000,
      stock_min: '0.5',
      stock_max: '3',
    });
    expect(filterParams({})).toEqual({});
  });
});
