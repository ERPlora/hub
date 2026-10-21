// The product sheet (WORKBOOK «Ficha del producto»): a dialog with the product's name and its SKU,
// Price, Stock («—» for an article without stock control) and Status («Yes», «No» or «Not configured ·
// Missing tax category»), and, with the permission to move stock and on a physical product, «Receive
// stock», «Count stock» and «Write off stock». For whoever can change products, «Mark sold out» or «Put
// back on sale» (INVENTORY-F29), whose refusal is said inside the sheet. The SKU's barcode on its white
// plate and «Print barcode» (INVENTORY-F25): the label goes to Printing's queue; without the queue, the
// browser's print dialog.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, flush, mountInventory, ok, product, refusal } from '../__tests__/mount-inventory';
import { formatMoney } from '../lib/format';
import ProductDetailModal from './ProductDetailModal.vue';

const browser = vi.hoisted(() => ({ printInBrowser: vi.fn() }));
vi.mock('../lib/print-label', () => browser);

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
  browser.printInBrowser.mockReset();
});

async function setup(props: Record<string, unknown> = {}, options: Parameters<typeof mountInventory>[1] = {}) {
  const m = await mountInventory(ProductDetailModal, { props: { open: true, product: product(), ...props }, attach: true, ...options });
  await flush();
  const el = (id: string) => document.querySelector<HTMLElement>(`[data-testid="${id}"]`);
  const value = (id: string) => el(`inventory-product-detail-${id}`)?.querySelector('ion-note')?.textContent?.trim();
  return { ...m, el, value };
}

/** A second sheet in the same test: the first one leaves the page (its elements would answer the queries). */
function unmount(s: Awaited<ReturnType<typeof setup>>): void {
  s.wrapper.unmount();
  document.body.innerHTML = '';
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

  it('INVENTORY-F29: a sold-out article says so beside its status', async () => {
    const s = await setup({ product: product({ is_sold_out: true }) });
    expect(s.value('status')).toBe('Yes · Sold out');
  });

  it('INVENTORY-F29: «Mark sold out» marks it, «Put back on sale» unmarks it; the sheet stays open', async () => {
    const s = await setup({}, { api: () => ok(product({ is_sold_out: true })) });
    expect(s.el('inventory-product-detail-back-on-sale')).toBeNull();
    s.el('inventory-product-detail-sold-out')!.click();
    await flush();
    expect(s.body(s.calls('/api/inventory/products/sold_out')[0])).toEqual({ id: 'p1', sold_out: true });
    expect(s.el('inventory-product-detail')).not.toBeNull();

    unmount(s);
    const sold = await setup({ product: product({ is_sold_out: true }) }, { api: () => ok(product()) });
    expect(sold.el('inventory-product-detail-sold-out')).toBeNull();
    sold.el('inventory-product-detail-back-on-sale')!.click();
    await flush();
    expect(sold.body(sold.calls('/api/inventory/products/sold_out')[0])).toEqual({ id: 'p1', sold_out: false });
  });

  it('INVENTORY-F29: a refusal is said inside the sheet; whoever cannot change products has neither button', async () => {
    const s = await setup({}, { api: () => refusal(404, 'not_found', 'This product does not exist in this hub.') });
    s.el('inventory-product-detail-sold-out')!.click();
    await flush();
    expect(s.el('inventory-product-detail-error')?.textContent).toContain('This product does not exist in this hub.');
    unmount(s);
    const employee = await setup({}, { session: EMPLOYEE });
    expect(employee.el('inventory-product-detail-sold-out')).toBeNull();
    expect(employee.el('inventory-product-detail-back-on-sale')).toBeNull();
  });

  it('INVENTORY-F25: the SKU\'s barcode is on the sheet, for whoever sees products', async () => {
    const s = await setup({}, { session: EMPLOYEE });
    expect(s.el('inventory-barcode')?.querySelector('svg')?.getAttribute('aria-label')).toBe('Barcode CAF-1');
    expect(s.el('inventory-product-detail-print-label')?.textContent?.trim()).toBe('Print barcode');
  });

  it('INVENTORY-F25: «Print barcode» sends one label per press and says which printer takes it', async () => {
    const s = await setup({}, { api: () => ok({ job_id: 'j1', printer_name: 'Labels' }) });
    s.el('inventory-product-detail-print-label')!.click();
    await flush();
    s.el('inventory-product-detail-print-label')!.click();
    await flush();
    expect(s.calls('/api/inventory/products/print_label').map((call) => s.body(call))).toEqual([{ id: 'p1' }, { id: 'p1' }]);
    expect(s.el('inventory-product-detail-label')?.textContent?.trim()).toBe('The label went to the printer «Labels».');
    expect(browser.printInBrowser).not.toHaveBeenCalled();
  });

  it('INVENTORY-F25: with no «Label» printer the label waits in the queue, and the sheet says what to do', async () => {
    const s = await setup({}, { api: () => ok({ job_id: 'j1', printer_name: null }) });
    s.el('inventory-product-detail-print-label')!.click();
    await flush();
    expect(s.el('inventory-product-detail-label')?.textContent?.trim()).toBe(
      'The label is waiting in the print queue: no printer has the «Label» function. Give it to one in Printing.',
    );
  });

  it('INVENTORY-F25: without the print queue it opens the browser\'s print dialog with the code, the SKU and the name', async () => {
    const s = await setup({}, { api: () => refusal(409, 'inventory.label_queue_unavailable', 'The print queue is not available here.') });
    s.el('inventory-product-detail-print-label')!.click();
    await flush();
    expect(browser.printInBrowser).toHaveBeenCalledOnce();
    const [svg, label] = browser.printInBrowser.mock.calls[0];
    expect((svg as SVGSVGElement).getAttribute('aria-label')).toBe('Barcode CAF-1');
    expect(label).toEqual({ sku: 'CAF-1', name: 'Coffee' });
    expect(s.el('inventory-product-detail-error')).toBeNull();
  });

  it('INVENTORY-F25: any other refusal is said inside the sheet with its reason', async () => {
    const s = await setup({}, { api: () => refusal(404, 'not_found', 'This product does not exist in this hub.') });
    s.el('inventory-product-detail-print-label')!.click();
    await flush();
    expect(s.el('inventory-product-detail-error')?.textContent?.trim()).toBe(
      'Could not print the barcode label: This product does not exist in this hub.',
    );
    expect(browser.printInBrowser).not.toHaveBeenCalled();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ product: product({ is_active: false }) }, { locale: 'es' });
    expect(s.value('status')).toBe('No');
    expect(s.el('inventory-product-detail-receive')?.textContent?.trim()).toBe('Recibir stock');
    expect(s.el('inventory-product-detail-sold-out')?.textContent?.trim()).toBe('Marcar agotado');
    unmount(s);
    const sold = await setup({ product: product({ is_sold_out: true }) }, { locale: 'es' });
    expect(sold.value('status')).toBe('Sí · Agotado');
    expect(sold.el('inventory-product-detail-back-on-sale')?.textContent?.trim()).toBe('Volver a poner a la venta');
    expect(sold.el('inventory-product-detail-print-label')?.textContent?.trim()).toBe('Imprimir código de barras');
  });
});
