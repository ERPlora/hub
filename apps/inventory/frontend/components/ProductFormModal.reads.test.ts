// What the product form shows when a read it makes on opening fails (INVENTORY-F02): the business's money, the tax
// categories and the product categories each come from the tab's live stream. When the stream cannot open (a proxy's
// 502 page while the Hub restarts) every read hears the failure and the stream keeps trying by itself; each field then
// says its own read failed, with the reason, instead of looking empty as if the product had no tax category and no
// categories. What the product has saved is not lost: saving sends only what the person changed.
import { afterEach, describe, expect, it } from 'vitest';

import { typeText } from '../__tests__/ionic-controls';
import { flush, mountInventory, ok, product, UNITS } from '../__tests__/mount-inventory';
import { CATEGORIES, searches } from '../__tests__/product-form';
import ProductFormModal from './ProductFormModal.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

const UNEXPECTED = 'The operation could not be completed. Try again in a few seconds, and tell an administrator if it keeps happening.';
const COFFEE = product({ tax_category_key: 'product.generic', category_ids: ['c1'] });

async function mountEditing() {
  const m = await mountInventory(ProductFormModal, {
    props: { open: true, product: COFFEE, units: UNITS.rows },
    attach: true,
    api: searches(CATEGORIES),
  });
  const inDoc = (testid: string) => document.querySelector<HTMLElement & { value?: unknown }>(`[data-testid="${testid}"]`);
  const text = (testid: string) => inDoc(testid)?.textContent?.replace(/\s+/g, ' ').trim() ?? null;
  return { ...m, inDoc, text };
}

describe('ProductFormModal: a read that fails when the panel opens (INVENTORY-F02)', () => {
  it('the stream cannot open: the currency, the tax category and the categories each say their read failed', async () => {
    const m = await mountEditing();
    await m.cannotOpen();

    expect(m.client.stream.status()).toBe('reconnecting');
    expect(m.text('base-money-error')).toContain("The business's currency could not be read");
    expect(m.text('inventory-product-tax-error')).toContain('The tax categories could not be loaded');
    expect(m.text('inventory-product-tax-error')).toContain(UNEXPECTED);
    expect(m.text('inventory-product-categories-error')).toContain('The categories could not be loaded');
    expect(m.text('inventory-product-categories-error')).toContain(UNEXPECTED);
    // Nothing claims the product lacks its tax category: the list could not be read.
    expect(m.inDoc('inventory-product-tax-unconfigured')).toBeNull();
  });

  it('the stream falls with the money already read: the lists say they failed, and saving keeps what was saved', async () => {
    const m = await mountEditing();
    await m.falls(await m.live());

    expect(m.inDoc('base-money-error')).toBeNull();
    expect(m.text('inventory-product-tax-error')).toContain('The tax categories could not be loaded');
    expect(m.text('inventory-product-categories-error')).toContain('The categories could not be loaded');

    await typeText(m.inDoc, 'inventory-product-name', 'Coffee with milk');
    m.net.onApi(() => ok(COFFEE));
    m.inDoc('inventory-product-form-submit')!.click();
    await flush();
    const sent = m.calls('/api/inventory/products/update').map((c) => m.body(c));
    expect(sent).toEqual([{ id: 'p1', name: 'Coffee with milk' }]);
  });

  it('speaks Spanish', async () => {
    const m = await mountInventory(ProductFormModal, {
      props: { open: true, product: COFFEE, units: UNITS.rows },
      attach: true,
      locale: 'es',
      api: searches(CATEGORIES),
    });
    await m.cannotOpen();
    const text = (testid: string) => document.querySelector(`[data-testid="${testid}"]`)?.textContent ?? '';
    expect(text('inventory-product-tax-error')).toContain('No se pudieron cargar las categorías fiscales');
    expect(text('inventory-product-categories-error')).toContain('No se pudieron cargar las categorías');
  });
});
