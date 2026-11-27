// «New product» and «Edit product» (INVENTORY-F01, INVENTORY-F02): the SKU may be left empty, and while «Save» is off
// the dialog says what is missing, one thing at a time, as the count and the write-off do.
import { afterEach, describe, expect, it } from 'vitest';

import { ok, product } from '../__tests__/mount-inventory';
import { setup } from '../__tests__/product-form';

afterEach(() => {
  document.body.innerHTML = '';
});

const hint = (s: Awaited<ReturnType<typeof setup>>) => s.el('inventory-product-form-hint')?.textContent?.trim() ?? null;

describe('ProductFormModal: what is missing to save', () => {
  it('a new product is saved without a SKU, and the field says it is numbered on its own', async () => {
    const s = await setup();
    expect(s.el('inventory-product-sku')?.helperText).toBe('Leave it empty to number it automatically (10000, 10001…).');
    await s.type('inventory-product-name', 'Cheesecake');
    await s.type('inventory-product-price', '4,50');
    await s.choose('inventory-product-tax', 'product.generic');
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(false);
    s.net.onApi(() => ok(product({ sku: '10000' }), 201));
    await s.submit();
    expect(s.sent('/api/inventory/products')).toMatchObject({ name: 'Cheesecake', sku: '', price: 450 });
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('«Save» off says what is missing, one thing at a time, and nothing once it is on', async () => {
    const s = await setup();
    expect(hint(s)).toBe('Enter the name to continue.');
    await s.type('inventory-product-name', 'Cheesecake');
    expect(hint(s)).toBe('Choose the tax category to continue.');
    await s.choose('inventory-product-tax', 'product.generic');
    expect(hint(s)).toBeNull();
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(false);
  });

  it('editing: an emptied name and a tax category Taxes no longer offers say so too', async () => {
    const s = await setup({ product: product({ needs_tax_setup: true, tax_category_key: null }) });
    expect(hint(s)).toBe('Choose the tax category to continue.');
    await s.type('inventory-product-name', '');
    expect(hint(s)).toBe('Enter the name to continue.');
  });

  it('while the business has not said its currency, «Save» waits without blaming a field', async () => {
    const s = await setup({}, { business: null });
    await s.type('inventory-product-name', 'Cheesecake');
    await s.choose('inventory-product-tax', 'product.generic');
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(true);
    expect(hint(s)).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup({}, { locale: 'es' });
    expect(s.el('inventory-product-sku')?.helperText).toBe('Déjalo vacío para numerarlo solo (10000, 10001…).');
    expect(hint(s)).toBe('Escribe el nombre para continuar.');
    await s.type('inventory-product-name', 'Tarta de queso');
    expect(hint(s)).toBe('Elige la categoría fiscal para continuar.');
  });
});
