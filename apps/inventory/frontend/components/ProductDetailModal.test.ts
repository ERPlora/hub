// The product sheet (WORKBOOK «Ficha del producto»): a dialog with the product's name and its SKU,
// Price, Stock («—» for an article without stock control) and Status («Yes», «No» or «Not configured ·
// Missing tax category»), and, with the permission to move stock and on a physical product, «Receive
// stock», «Count stock» and «Write off stock». (The barcode and its label, INVENTORY-F25, wait for
// the Printing app.)
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, flush, mountInventory, product } from '../__tests__/mount-inventory';
import { formatMoney } from '../lib/format';
import ProductDetailModal from './ProductDetailModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(props: Record<string, unknown> = {}, options: Parameters<typeof mountInventory>[1] = {}) {
  const m = await mountInventory(ProductDetailModal, { props: { open: true, product: product(), ...props }, attach: true, ...options });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const value = (id: string) => el(`inventory-product-detail-${id}`)?.querySelector('ion-note')?.textContent?.trim();
  return { ...m, el, value };
}

describe('ProductDetailModal', () => {
  it('shows SKU, Price, Stock and Status under the product name', async () => {
    const s = await setup();
    expect(s.el('inventory-product-detail')?.getAttribute('aria-label')).toBe('Coffee');
    expect([s.value('sku'), s.value('price'), s.value('stock'), s.value('status')]).toEqual(['CAF-1', formatMoney(220, 'en'), '5', 'Yes']);
  });

  it('an article without stock control shows «—»; one without tax category says why it is not sold', async () => {
    const s = await setup({ product: product({ tracks_stock: false, track_stock: false, needs_tax_setup: true, tax_category_key: null }) });
    expect([s.value('stock'), s.value('status')]).toEqual(['—', 'Not configured · Missing tax category']);
  });

  it('offers receive, count and write off, each asking the page for its dialog', async () => {
    const s = await setup();
    expect(['receive', 'count', 'write-off'].map((id) => s.el(`inventory-product-detail-${id}`)?.textContent?.trim())).toEqual([
      'Receive stock',
      'Count stock',
      'Write off stock',
    ]);
    s.el('inventory-product-detail-count')!.click();
    await flush();
    expect(s.wrapper.emitted('stock')).toEqual([['count']]);
  });

  it('an article without stock control is received and counted, but has nothing to write off', async () => {
    const s = await setup({ product: product({ tracks_stock: false, track_stock: false }) });
    expect(s.el('inventory-product-detail-receive')).not.toBeNull();
    expect(s.el('inventory-product-detail-write-off')).toBeNull();
  });

  it('a service, or whoever cannot move stock, gets no stock buttons', async () => {
    const service = await setup({ product: product({ product_type: 'service', tracks_stock: false }) });
    expect(service.el('inventory-product-detail-receive')).toBeNull();
    const employee = await setup({}, { session: EMPLOYEE });
    expect(employee.el('inventory-product-detail-receive')).toBeNull();
    expect(employee.value('status')).toBe('Yes');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ product: product({ is_active: false }) }, { locale: 'es' });
    expect(s.value('status')).toBe('No');
    expect(s.el('inventory-product-detail-receive')?.textContent?.trim()).toBe('Recibir stock');
  });
});
