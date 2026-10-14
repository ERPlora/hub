// The stock dialogs of a product (WORKBOOK «Recepción», «Recuento», INVENTORY-F13/F14/F15):
//   - «Goods receipt — <product>»: «Current stock», «Quantity received», «Unit cost (EUR)» and
//     «Record receipt» (off without a quantity);
//   - «Stock count — <product>»: «Current stock», «Difference» once there is a figure, «Counted stock»
//     (the total, not the difference), «Reason (required)» and «Apply count», with the note of what
//     is missing;
//   - «Write-off — <product>»: the quantity and its reason (waste, breakage, own consumption).
// Quantities in the product's unit and its step; a refusal stays in the dialog under its field.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { flush, mountInventory, ok, product, refusal, UNITS } from '../__tests__/mount-inventory';
import StockModal from './StockModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

afterEach(() => {
  document.body.innerHTML = '';
});

type Control = HTMLElement & { value?: unknown; errorText?: string; disabled?: boolean; label?: string; helperText?: string };

async function setup(kind: 'receive' | 'count' | 'write_off', props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(StockModal, {
    props: { open: true, kind, product: product({ stock: '5.000' }), units: UNITS.rows, ...props },
    locale,
    attach: true,
  });
  await flush();
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  async function type(id: string, value: string) {
    const field = el(id)!;
    field.value = value;
    field.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
    await flush();
  }
  async function submit() {
    el('inventory-stock-form-submit')!.click();
    await flush();
  }
  const sent = (path: string) => m.body(m.calls(path).at(-1)!);
  return { ...m, el, type, submit, sent };
}

describe('StockModal: goods receipt', () => {
  it('«Goods receipt — Coffee» with the current stock; «Record receipt» off without a quantity', async () => {
    const s = await setup('receive');
    expect(s.el('inventory-stock-form')?.getAttribute('aria-label')).toBe('Goods receipt — Coffee');
    expect(s.el('inventory-stock-current')?.textContent).toMatch(/Current stock\s*5/);
    expect([s.el('inventory-stock-qty')?.label, s.el('inventory-stock-cost')?.label]).toEqual(['Quantity received', 'Unit cost (EUR)']);
    expect(s.el('inventory-stock-qty')?.helperText).toBe('In ud, in steps of 1');
    expect(s.el('inventory-stock-form-submit')?.textContent?.trim()).toBe('Record receipt');
    expect(s.el('inventory-stock-form-submit')?.disabled).toBe(true);
  });

  it('records it: the quantity exact, the cost in cents (none when empty), and closes', async () => {
    const s = await setup('receive');
    s.net.onApi(() => ok({ rows: [product({ stock: '8.000' })] }));
    await s.type('inventory-stock-qty', '3');
    await s.type('inventory-stock-cost', '0,75');
    await s.submit();
    expect(s.sent('/api/inventory/stock/receive')).toEqual({ items: [{ product_id: 'p1', qty: '3', unit_cost: 75 }] });
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    const t = await setup('receive');
    t.net.onApi(() => ok({ rows: [product()] }));
    await t.type('inventory-stock-qty', '2,5');
    await t.submit();
    expect(t.sent('/api/inventory/stock/receive')).toEqual({ items: [{ product_id: 'p1', qty: '2.5', unit_cost: null }] });
  });

  it("a quantity off the unit's step says so under the quantity and stays", async () => {
    const s = await setup('receive', { product: product({ unit: 'kg' }) });
    const message = 'The quantity does not respect the step allowed for this unit: use multiples of 0,001 kg.';
    s.net.onApi(() => refusal(409, 'inventory.off_grid_quantity', message, { 'items.0.qty': message }));
    await s.type('inventory-stock-qty', '0,0005');
    await s.submit();
    expect(s.calls('/api/inventory/stock/receive')).toHaveLength(0);
    expect(s.el('inventory-stock-qty')?.errorText).toBe('This is not a quantity. Type a figure with up to three decimals, for example 2.5.');
    await s.type('inventory-stock-qty', '1,0005');
    await s.type('inventory-stock-qty', '1.250');
    await s.submit();
    expect(s.el('inventory-stock-qty')?.errorText).toBe(message);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});

describe('StockModal: stock count', () => {
  it('says what is missing, then the difference against the current stock', async () => {
    const s = await setup('count');
    expect(s.el('inventory-stock-form')?.getAttribute('aria-label')).toBe('Stock count — Coffee');
    expect(s.el('inventory-stock-needs')?.textContent?.trim()).toBe('Enter the counted stock to continue.');
    expect(s.el('inventory-stock-diff')).toBeNull();
    await s.type('inventory-stock-qty', '7');
    expect(s.el('inventory-stock-diff')?.textContent).toMatch(/Difference\s*\+2/);
    expect(s.el('inventory-stock-needs')?.textContent?.trim()).toBe('A reason is required to apply the count.');
    expect(s.el('inventory-stock-form-submit')?.disabled).toBe(true);
    await s.type('inventory-stock-qty', '4,5');
    expect(s.el('inventory-stock-diff')?.textContent).toMatch(/Difference\s*-0\.5/);
  });

  it('applies it with the total counted and the reason', async () => {
    const s = await setup('count');
    s.net.onApi(() => ok(product({ stock: '7.000' })));
    await s.type('inventory-stock-qty', '7');
    await s.type('inventory-stock-reason', ' Monthly count ');
    expect(s.el('inventory-stock-needs')).toBeNull();
    await s.submit();
    expect(s.sent('/api/inventory/stock/count')).toEqual({ product_id: 'p1', stock: '7', reason: 'Monthly count' });
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('a short reason is refused under the reason', async () => {
    const s = await setup('count');
    s.net.onApi(() => refusal(422, 'invalid_payload', 'Invalid payload', { reason: 'String should have at least 3 characters' }));
    await s.type('inventory-stock-qty', '7');
    await s.type('inventory-stock-reason', 'ab');
    await s.submit();
    expect(s.el('inventory-stock-reason')?.errorText).toBe('String should have at least 3 characters');
  });
});

describe('StockModal: write-off', () => {
  it('writes off the quantity with its reason; not enough stock is said under the quantity', async () => {
    const s = await setup('write_off');
    expect(s.el('inventory-stock-form')?.getAttribute('aria-label')).toBe('Write-off — Coffee');
    expect(s.el('inventory-stock-form-submit')?.textContent?.trim()).toBe('Write off');
    const message = 'There is not enough stock to complete the operation.';
    s.net.onApi(() => refusal(409, 'inventory.insufficient_stock', message, { qty: message }));
    await s.type('inventory-stock-qty', '9');
    await s.type('inventory-stock-reason', 'Broken bottle');
    await s.submit();
    expect(s.sent('/api/inventory/stock/write_off')).toEqual({ product_id: 'p1', qty: '9', reason: 'Broken bottle' });
    expect(s.el('inventory-stock-qty')?.errorText).toBe(message);
  });
});

describe('StockModal: a write-off the server refuses', () => {
  it('an article without stock control: the reason under the quantity, the dialog open', async () => {
    const s = await setup('write_off');
    const message = 'This article does not track its stock: there is nothing to write off.';
    s.net.onApi(() => refusal(409, 'inventory.stock_not_tracked', message, { qty: message }));
    await s.type('inventory-stock-qty', '1');
    await s.type('inventory-stock-reason', 'Broken bottle');
    await s.submit();
    expect(s.el('inventory-stock-qty')?.errorText).toBe(message);
    expect(s.el('inventory-stock-form-error')?.textContent).toContain(message);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });
});

describe('StockModal', () => {
  it('speaks Spanish', async () => {
    const s = await setup('count', {}, 'es');
    expect(s.el('inventory-stock-form')?.getAttribute('aria-label')).toBe('Recuento — Coffee');
    expect(s.el('inventory-stock-reason')?.label).toBe('Motivo (obligatorio)');
    expect(s.el('inventory-stock-form-submit')?.textContent?.trim()).toBe('Aplicar recuento');
  });
});
