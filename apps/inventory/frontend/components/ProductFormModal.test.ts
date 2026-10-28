// The product form (WORKBOOK «Productos», INVENTORY-F01/F02/F05/F08/F20/F26), the old side panel as a
// dialog: Name, SKU (locked when editing), Price, «Cost (<currency>)», «Initial stock» (create only), «Low
// stock threshold» (empty = 10), EAN-13, Description, «Type» (create only), «Track stock for this
// item» with its note, «Unit of measure», «Tax category» (required, none chosen in advance) and
// «Categories» (when there are any). «Save» / «Save changes» is off while Name, SKU or the tax
// category are missing; amounts and quantities are read as typed; an edit sends only what changed;
// a refusal stays in the dialog under its field. «Tax category» and «Categories» are `Combo` fields of
// @erplora/ui that search the server (TaxCategorySelect, ProductCategoriesField).
import { Combo, type ComboOption } from '@erplora/ui/components';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Business } from '../../../../base/frontend/operations';
import { business, category, flush, mountInventory, ok, page, POLISH, product, refusal, TAX_CATEGORIES, UNITS, type ApiCall } from '../__tests__/mount-inventory';
import ProductFormModal from './ProductFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; errorText?: string; disabled?: boolean; label?: string; helperText?: string; checked?: boolean };

const CATEGORIES = page([category(), category({ id: 'c2', name: 'Food', slug: 'food' })], 2, 100);

/** What the server answers the Combo searches: the tax categories and the product categories. */
const searches = (categories: unknown) => (call: ApiCall) =>
  ok(call.url.startsWith('/api/tax/categories') ? TAX_CATEGORIES : categories);

async function setup(
  props: Record<string, unknown> = {},
  options: { locale?: 'en' | 'es'; categories?: unknown; taxes?: unknown; api?: (call: ApiCall) => Response; business?: Business | null } = {},
) {
  const m = await mountInventory(ProductFormModal, {
    props: { open: true, product: null, units: UNITS.rows, ...props },
    locale: options.locale,
    attach: true,
    business: options.business,
    api: options.api ?? searches(options.categories ?? CATEGORIES),
  });
  const call = await m.live();
  await m.result(call, 'tax.category.list', options.taxes ?? TAX_CATEGORIES);
  await m.result(call, 'inventory.category.list', options.categories ?? CATEGORIES);
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  async function type(id: string, value: string) {
    const field = el(id)!;
    field.value = value;
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function pick(id: string, value: unknown) {
    const field = el(id)!;
    field.value = value;
    field.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  /** Picks, in the Combo `id`, the option of `key` it offers on opening. */
  async function choose(id: string, key: string) {
    const combo = m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === id);
    if (!combo) throw new Error(`${id} is not a Combo`);
    const option = (await (combo.props('search') as (q: string) => Promise<ComboOption[]>)('')).find((o) => o.id === key);
    if (!option) throw new Error(`${id} offers no ${key}`);
    combo.vm.$emit('update:modelValue', option);
    await flush();
  }
  async function check(id: string, checked: boolean) {
    const field = el(id)!;
    field.checked = checked;
    field.dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
    await flush();
  }
  async function submit() {
    el('inventory-product-form-submit')!.click();
    await flush();
  }
  async function fillRequired() {
    await type('inventory-product-name', 'Coffee');
    await type('inventory-product-sku', 'CAF-1');
    await type('inventory-product-price', '2,20');
    await choose('inventory-product-tax', 'product.generic');
  }
  const sent = (path: string) => m.body(m.calls(path).at(-1)!) as Record<string, unknown>;
  const chips = () => [...document.querySelectorAll('[data-testid^="inventory-product-categories-chip-"]')].map((c) => c.textContent?.trim());
  /** `base.business.get` answers now (the form opened with `business: null`, before it did); `rev` 2+ is a change. */
  const answer = (fields: Partial<Business>, rev = 1) => m.result(call, 'base.business.get', business(fields), rev);
  return { ...m, el, type, pick, choose, check, submit, fillRequired, sent, chips, answer };
}

const JAPANESE: Partial<Business> = { country: 'JP', country_name: 'Japan', currency: 'JPY', currency_label: 'JPY · Japanese Yen', currency_decimals: 0 };
const KUWAITI: Partial<Business> = { country: 'KW', country_name: 'Kuwait', currency: 'KWD', currency_label: 'KWD · Kuwaiti Dinar', currency_decimals: 3 };

describe('ProductFormModal: new product', () => {
  it('«New product» with every field of the old panel, the tax category empty, «Save» off', async () => {
    const s = await setup();
    expect(s.el('inventory-product-form')?.getAttribute('aria-label')).toBe('New product');
    const labels = [
      'name',
      'sku',
      'price',
      'cost',
      'initial-stock',
      'threshold',
      'ean13',
      'description',
      'type',
      'unit',
      'tax',
      'categories',
    ].map((id) => s.el(`inventory-product-${id}`)?.label);
    expect(labels).toEqual([
      'Name',
      'SKU',
      'Price',
      'Cost (EUR)',
      'Initial stock',
      'Low stock threshold',
      'EAN-13',
      'Description',
      'Type',
      'Unit of measure',
      'Tax category',
      'Categories',
    ]);
    expect(s.el('inventory-product-tax')?.value).toBe('');
    expect(s.el('inventory-product-unit')?.value).toBe('ud');
    // Each unit by the name the API gives it, which already carries its code («Unit (ud)», once).
    expect([...s.el('inventory-product-unit')!.querySelectorAll('ion-select-option')].map((o) => o.textContent?.trim())).toEqual(
      UNITS.rows.map((unit) => unit.name),
    );
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(true);
  });

  it('«Track stock» follows the hub setting until touched, with its note', async () => {
    const s = await setup({ hubTracksStock: false });
    expect(s.el('inventory-product-track-stock')?.checked).toBe(false);
    expect(s.el('inventory-product-track-note')?.textContent?.trim()).toBe('Following the hub setting');
    await s.check('inventory-product-track-stock', false);
    expect(s.el('inventory-product-track-note')?.textContent?.trim()).toBe('Catalog only: sales do not move its stock');
  });

  it('a service has no stock control', async () => {
    const s = await setup();
    await s.pick('inventory-product-type', 'service');
    expect(s.el('inventory-product-track-stock')).toBeNull();
  });

  it('creates it in one go: cents, exact quantities, threshold 10 when empty, categories, the hub deciding stock control', async () => {
    const s = await setup();
    await s.fillRequired();
    await s.type('inventory-product-cost', '0,80');
    await s.type('inventory-product-initial-stock', '2,5');
    await s.pick('inventory-product-unit', 'kg');
    await s.choose('inventory-product-categories', 'c2');
    expect(s.chips()).toEqual(['Food']);
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(false);
    s.net.onApi(() => ok(product(), 201));
    await s.submit();
    expect(s.sent('/api/inventory/products')).toEqual({
      name: 'Coffee',
      sku: 'CAF-1',
      price: 220,
      cost: 80,
      tax_category_key: 'product.generic',
      initial_stock: '2.5',
      low_stock_threshold: '10',
      ean13: null,
      description: '',
      product_type: 'physical',
      unit: 'kg',
      track_stock: null,
      category_ids: ['c2'],
    });
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('an amount that cannot be read stops the save and says why under its field', async () => {
    const s = await setup();
    await s.fillRequired();
    await s.type('inventory-product-price', '1.250');
    await s.submit();
    expect(s.calls('/api/inventory/products')).toHaveLength(0);
    expect(s.el('inventory-product-price')?.errorText).toMatch(/^This amount can be read in two ways/);
  });

  it('a refusal stays in the dialog: SKU taken under the SKU, the message on top', async () => {
    const s = await setup();
    await s.fillRequired();
    s.net.onApi(() => refusal(409, 'inventory.sku_taken', 'That SKU already exists in the catalog.', { sku: 'That SKU already exists in the catalog.' }));
    await s.submit();
    expect(s.el('inventory-product-sku')?.errorText).toBe('That SKU already exists in the catalog.');
    expect(s.el('inventory-product-form-error')?.textContent).toContain('That SKU already exists in the catalog.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('Enter on the open «Categories» list adds the category and does not save the product', async () => {
    const s = await setup({}, { categories: page([category()], 140, 100) });
    await s.fillRequired();
    // Enter on the field while its list is open: what FormModal reads as «submit» if it reaches the form.
    const field = s.el('inventory-product-categories')!;
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value: 'Dri' } }));
    await new Promise((resolve) => setTimeout(resolve, 200));
    await flush();
    field.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
    await flush();
    expect(s.calls('/api/inventory/products')).toHaveLength(0);
    expect(s.chips()).toEqual(['Drinks']);
  });

  it('without categories the «Categories» field is not there', async () => {
    const s = await setup({}, { categories: page([], 0, 100) });
    expect(s.el('inventory-product-categories')).toBeNull();
  });
});

describe('ProductFormModal: editing', () => {
  const COFFEE = product({ ean13: '8410000000001', description: 'Arabica', category_ids: ['c1'] });

  it('«Editing product — <name>» with its values; SKU locked with its reason; no initial stock nor type', async () => {
    const s = await setup({ product: COFFEE });
    expect(s.el('inventory-product-form')?.getAttribute('aria-label')).toBe('Editing product — Coffee');
    expect([s.el('inventory-product-name')?.value, s.el('inventory-product-sku')?.value, s.el('inventory-product-price')?.value]).toEqual([
      'Coffee',
      'CAF-1',
      '2.20',
    ]);
    expect(s.el('inventory-product-sku')?.disabled).toBe(true);
    expect(s.el('inventory-product-sku')?.helperText).toBe("The SKU is the product's identity: it is not edited");
    expect(s.el('inventory-product-threshold')?.value).toBe('10');
    expect([s.el('inventory-product-initial-stock'), s.el('inventory-product-type')]).toEqual([null, null]);
    expect(s.chips()).toEqual(['Drinks']);
    expect(s.el('inventory-product-form-submit')?.textContent?.trim()).toBe('Save changes');
    expect(s.el('inventory-product-form-cancel')?.textContent?.trim()).toBe('Cancel editing');
  });

  it('sends only what changed', async () => {
    const s = await setup({ product: COFFEE });
    await s.type('inventory-product-price', '2,50');
    await s.type('inventory-product-ean13', '');
    await s.choose('inventory-product-categories', 'c2');
    s.net.onApi(() => ok(COFFEE));
    await s.submit();
    expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', price: 250, ean13: '', category_ids: ['c1', 'c2'] });
  });

  it('a product without its tax category is marked «Not configured» and cannot be saved until one is picked', async () => {
    const s = await setup({ product: product({ tax_category_key: null, needs_tax_setup: true }) });
    expect(s.el('inventory-product-tax-unconfigured')).not.toBeNull();
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(true);
    await s.choose('inventory-product-tax', 'service.health');
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(false);
    s.net.onApi(() => ok(product()));
    await s.submit();
    expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', tax_category_key: 'service.health' });
  });

  it('a product whose tax category Taxes deactivated keeps «Save changes» off until another is picked', async () => {
    const s = await setup({ product: product({ tax_category_key: 'old.deactivated', needs_tax_setup: true }) });
    expect(s.el('inventory-product-tax-unconfigured')).not.toBeNull();
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(true);
    await s.choose('inventory-product-tax', 'product.generic');
    expect(s.el('inventory-product-form-submit')?.disabled).toBe(false);
  });

  it('a product whose category and tax category lie beyond the first page opens with their names, never an id or a key', async () => {
    // More than one query holds (100) of each: the first pages do not name them, so the form asks for them.
    const wine = { ...TAX_CATEGORIES.rows[0], id: 't9', key: 'drink.wine', name: 'Wine', display_name: 'Wine', rate_pct: '10.00' };
    const wines = category({ id: 'c9', name: 'Wines', slug: 'wines' });
    const s = await setup(
      { product: product({ tax_category_key: 'drink.wine', category_ids: ['c9'] }) },
      {
        taxes: { ...TAX_CATEGORIES, total: 140 },
        categories: page([category()], 140, 100),
        api: (call) => ok(call.url.startsWith('/api/tax/categories') ? page([wine]) : page([wines])),
      },
    );
    expect(s.el('inventory-product-tax')?.value).toBe('Wine · 10%');
    expect(s.chips()).toEqual(['Wines']);
    expect(s.el('inventory-product-tax-unconfigured')).toBeNull();
  });

  it('a unit that cannot change with stock says so under the unit', async () => {
    const s = await setup({ product: COFFEE });
    await s.pick('inventory-product-unit', 'kg');
    const message = 'You cannot change the unit of a product with stock. Count its stock to zero and change it then.';
    s.net.onApi(() => refusal(409, 'inventory.unit_has_stock', message, { unit: message }));
    await s.submit();
    expect(s.el('inventory-product-unit')?.errorText).toBe(message);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ product: COFFEE }, { locale: 'es' });
    expect(s.el('inventory-product-form')?.getAttribute('aria-label')).toBe('Editando producto — Coffee');
    expect(s.el('inventory-product-price')?.value).toBe('2,20');
    expect(s.el('inventory-product-cost')?.label).toBe('Coste (EUR)');
  });

  describe('the cost in the business’s currency (flow business-currency)', () => {
    it('a business in Poland reads «Cost (PLN)»', async () => {
      const s = await setup({}, { business: business(POLISH) });
      expect(s.el('inventory-product-cost')?.label).toBe('Cost (PLN)');
    });

    it('while the business is not read, «Cost» without a currency, never the euro', async () => {
      const s = await setup({}, { business: null });
      expect(s.el('inventory-product-cost')?.label).toBe('Cost');
    });
  });

  describe('the business answers after the form opened (flow INVENTORY-F02)', () => {
    const NOT_AMOUNT = 'This is not an amount. Type a figure, for example 12.50.';

    it('an untouched price and cost are rewritten from the product with the yen’s decimals, and «Save changes» sends neither', async () => {
      const s = await setup({ product: product({ price: 220, cost: 80 }) }, { business: null });
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['2.20', '0.80']);
      await s.answer(JAPANESE);
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['220', '80']);
      expect(s.el('inventory-product-cost')?.label).toBe('Cost (JPY)');
      await s.type('inventory-product-name', 'Cola');
      s.net.onApi(() => ok(product({ name: 'Cola' })));
      await s.submit();
      expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', name: 'Cola' });
    });

    it('with three decimals they are rewritten in that scale, never saved ten times bigger', async () => {
      const s = await setup({ product: product({ price: 1500, cost: 800 }) }, { business: null });
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['15.00', '8.00']);
      await s.answer(KUWAITI);
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['1.500', '0.800']);
      await s.type('inventory-product-name', 'Cola');
      s.net.onApi(() => ok(product({ name: 'Cola' })));
      await s.submit();
      expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', name: 'Cola' });
    });

    it('the currency changes again with the form open: still untouched, still rewritten from the product', async () => {
      const s = await setup({ product: product({ price: 220, cost: 80 }) }, { business: null });
      await s.answer(JAPANESE);
      await s.answer(KUWAITI, 2);
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['0.220', '0.080']);
      await s.type('inventory-product-name', 'Cola');
      s.net.onApi(() => ok(product({ name: 'Cola' })));
      await s.submit();
      expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', name: 'Cola' });
    });

    it('a new price typed before is kept as typed and read in the yen; the untouched cost is still rewritten', async () => {
      const s = await setup({ product: product({ price: 220, cost: 80 }) }, { business: null });
      await s.type('inventory-product-price', '300');
      await s.answer(JAPANESE);
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['300', '80']);
      s.net.onApi(() => ok(product({ price: 300 })));
      await s.submit();
      expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', price: 300 });
    });

    it('what was typed that the yen cannot read stays as typed: the field says so and nothing is sent', async () => {
      const s = await setup({ product: product({ price: 220, cost: 80 }) }, { business: null });
      await s.type('inventory-product-price', '1,75');
      await s.answer(JAPANESE);
      expect(s.el('inventory-product-price')?.value).toBe('1,75');
      await s.submit();
      expect(s.calls('/api/inventory/products/update')).toHaveLength(0);
      expect(s.el('inventory-product-price')?.errorText).toBe(NOT_AMOUNT);
    });
  });
});
