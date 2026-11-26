// The product form (WORKBOOK «Productos», INVENTORY-F01/F02/F05/F08/F20/F26), the old side panel as a
// dialog: Name, SKU (locked when editing), Price, «Cost (<currency>)», «Initial stock» (create only), «Low
// stock threshold» (empty = 10), EAN-13, Description, «Type» (create only), «Track stock for this
// item» with its note, «Unit of measure», «Tax category» (required, none chosen in advance) and
// «Categories» (when there are any). «Save» / «Save changes» is off while the name or the tax
// category are missing (ProductFormModal.needs.test.ts); amounts and quantities are read as typed; an edit sends only what changed;
// a refusal stays in the dialog under its field. «Tax category» and «Categories» are `Combo` fields of
// @erplora/ui that search the server (TaxCategorySelect, ProductCategoriesField).
import { afterEach, describe, expect, it } from 'vitest';

import {
  expectAmountLeftWaitsForMoney,
  expectSaveWaitsForMoney,
  expectWindowSaysMoneyUnreadable,
} from '../../../../base/frontend/__tests__/save-waits-for-money';
import type { Business } from '../../../../base/frontend/operations/business';
import {
  business,
  category,
  flush,
  mountInventory,
  ok,
  page,
  POLISH,
  product,
  refusal,
  TAX_CATEGORIES,
  UNITS,
} from '../__tests__/mount-inventory';
import ProductFormModal from './ProductFormModal.vue';
import { CATEGORIES, JAPANESE, searches, setup } from '../__tests__/product-form';

afterEach(() => {
  document.body.innerHTML = '';
});

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
      allergens: [],
      show_on_website: true,
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

    // hub#924: the cost is judged in the business's money, like the price: a euro one is no złoty amount in Poland.
    it('in Poland a cost «13,50 €» says it is not an amount, and nothing is saved', async () => {
      const s = await setup({}, { business: business(POLISH) });
      await s.fillRequired();
      await s.type('inventory-product-cost', '13,50 €');
      await s.submit();
      expect([s.el('inventory-product-cost')?.errorText, s.calls('/api/inventory/products')]).toEqual(['This is not an amount. Type a figure, for example 12.50.', []]);
    });

    it('while the business is not read, «Cost» without a currency, never the euro', async () => {
      const s = await setup({}, { business: null });
      expect(s.el('inventory-product-cost')?.label).toBe('Cost');
    });
  });

  describe('the business answers after the form opened (flow INVENTORY-F02)', () => {
    /** What the money field says in yen, with its example in yen. */
    const NOT_AMOUNT_IN_YEN = 'This is not an amount. Type a figure, for example 12.';

    it('a new product: the name and SKU typed before keep, and «Save» lights up once its tax category is chosen', async () => {
      const s = await setup({}, { business: null });
      await s.type('inventory-product-name', 'Coffee');
      await s.type('inventory-product-sku', 'CAF-1');
      await s.answer(JAPANESE);
      expect([s.el('inventory-product-name')?.value, s.el('inventory-product-sku')?.value]).toEqual(['Coffee', 'CAF-1']);
      expect(s.el('inventory-product-form-submit')?.disabled).toBe(true);
      await s.choose('inventory-product-tax', 'product.generic');
      expect(s.el('inventory-product-form-submit')?.disabled).toBe(false);
    });

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
      // hub#918: until the yen arrives «Save changes» waits in grey and nothing reads the price (never 300 as 30000).
      s.net.onApi(() => ok(product({ price: 300 })));
      const window = {
        wrapper: s.wrapper,
        save: () => s.el('inventory-product-form-submit'),
        amount: () => s.el('inventory-product-price'),
        sent: () => s.calls('/api/inventory/products/update'),
        settle: flush,
      };
      await expectSaveWaitsForMoney(window, () => s.answer(JAPANESE));
      expect([s.el('inventory-product-price')?.value, s.el('inventory-product-cost')?.value]).toEqual(['300', '80']);
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
      expect(s.el('inventory-product-price')?.errorText).toBe(NOT_AMOUNT_IN_YEN);
    });

    // hub#945 (INVENTORY-F01): a price or a cost typed with its currency's sign and left before the business answers is
    // neither rewritten nor called «not an amount»; once it answers, it is read in its money.
    it.each([
      ['price', '¥1500', JAPANESE, 1500],
      ['cost', '12,50 zł', POLISH, 1250],
    ] as const)('the %s «%s» left before the business says its currency stays as typed and unmarked, then is read in it (hub#945)', async (name, typed, money, cents) => {
      const s = await setup({ product: product({ price: 220, cost: 80 }) }, { business: null });
      await expectAmountLeftWaitsForMoney({ amount: () => s.el(`inventory-product-${name}`), settle: flush }, typed, () => s.answer(money));
      s.net.onApi(() => ok(product({ [name]: cents })));
      await s.submit();
      expect(s.sent('/api/inventory/products/update')).toEqual({ id: 'p1', [name]: cents });
    });
  });

  // INVENTORY-F01, hub#924: a price is never negative, and the field says that, not that «-2» is no amount.
  it('a negative price says it cannot be negative, and nothing is sent', async () => {
    const s = await setup();
    await s.fillRequired();
    await s.type('inventory-product-price', '-2');
    s.el('inventory-product-price')!.dispatchEvent(new CustomEvent('ionBlur'));
    await flush();
    await s.submit();
    expect([s.el('inventory-product-price')?.errorText, s.calls('/api/inventory/products')]).toEqual(['This amount cannot be negative.', []]);
  });
});

// hub#938 (INVENTORY-F01, F02): if the business's money cannot be read, the form says so with «Retry» instead of waiting in
// grey without a word, also when it opens after the read had failed (the page read the money on loading).
describe('ProductFormModal: a business whose money cannot be read (hub#938)', () => {
  it.each([false, true])('says so with «Retry»; once the yen arrives «Save changes» lights up (opened after the failure: %s)', async (late) => {
    const props = { open: !late, product: product(), units: UNITS.rows };
    const m = await mountInventory(ProductFormModal, { props, attach: true, business: null, api: searches(CATEGORIES) });
    await m.live();
    const inDoc = (testid: string) => document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);
    const opens = late ? () => m.wrapper.setProps({ open: true }) : undefined;
    await expectWindowSaysMoneyUnreadable({ ...m, inDoc }, 'inventory-product-form-submit', () => m.calls('/api/inventory/products/update'), opens);
  });
});
