// «Void» a charged sale (SALE-F30; the old `erp-sale-void`): the window «Void sale <number>» with the
// explanation, «Reason (required)» and «Void» / «Cancel». Without a reason it says so and sends nothing;
// with one it sends `sale.sale.void`, says «Sale voided» and closes. A refusal (a full invoice, refunds,
// already voided elsewhere) is read inside the window, in the server's words, and the window stays open.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountSale } from '../../__tests__/mount-sale';
import type { SaleRow } from '../../operations';
import VoidSaleModal from './VoidSaleModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const SALE = { id: 's1', number: '20261014-0007' } as SaleRow;

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountSale(VoidSaleModal, { props: { open: true, sale: SALE }, locale });
  const reason = () => m.inDoc('sale-void-reason');
  const type = (text: string) => ionValue(reason(), text, 'ionInput');
  const submit = () => click(m.inDoc('sale-void-submit'));
  return { ...m, reason, type, submit };
}

describe('VoidSaleModal', () => {
  it('is «Void sale <number>», with the explanation and «Reason (required)»', async () => {
    const s = await setup();
    expect(s.inDoc('sale-void')?.getAttribute('aria-label')).toBe('Void sale 20261014-0007');
    expect(s.inDoc('sale-void-explain')?.textContent).toBe('The sale stays on record as voided; cash and stock are reversed once. A reason is required.');
    const reason = s.reason();
    expect([prop(reason, 'label'), prop(reason, 'maxlength'), prop(reason, 'fill'), reason?.getAttribute('mode') ?? prop(reason, 'mode'), prop(reason, 'autoGrow')]).toEqual([
      'Reason (required)',
      500,
      'outline',
      'md',
      true,
    ]);
    expect([s.inDoc('sale-void-submit')?.textContent?.trim(), s.inDoc('sale-void-cancel')?.textContent?.trim()]).toEqual(['Void', 'Cancel']);
  });

  it('without a reason it says so and sends nothing', async () => {
    const s = await setup();
    await s.type('   ');
    await s.submit();
    expect(s.sent()).toEqual([]);
    expect(s.inDoc('sale-void-error')?.textContent).toContain('A reason is required to void a sale');
  });

  it('with a reason it voids the sale, says «Sale voided» and closes', async () => {
    const s = await setup();
    s.answer(200, { id: 's1', status: 'voided' });
    await s.type('  Wrong table ');
    await s.submit();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/sale/sales/void', query: {}, body: { sale_id: 's1', reason: 'Wrong table' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Sale voided');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(s.wrapper.emitted('voided')).toHaveLength(1);
  });

  it('a refusal is read inside the window, which stays open', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'sale.void_requires_credit_note', message: 'This sale carries a full invoice: issue a credit note instead.' } });
    await s.type('Mistake');
    await s.submit();
    expect(s.inDoc('sale-void-error')?.textContent).toContain('This sale carries a full invoice: issue a credit note instead.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('«Cancel» closes and sends nothing; opened again it starts blank', async () => {
    const s = await setup();
    await s.submit();
    await s.type('Mistake');
    await click(s.inDoc('sale-void-cancel'));
    expect(s.sent()).toEqual([]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    expect(prop(s.reason(), 'value')).toBe('');
    expect(s.inDoc('sale-void-error')).toBeNull();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('sale-void')?.getAttribute('aria-label')).toBe('Anular la venta 20261014-0007');
    expect(prop(s.reason(), 'label')).toBe('Motivo (obligatorio)');
    expect([s.inDoc('sale-void-submit')?.textContent?.trim(), s.inDoc('sale-void-cancel')?.textContent?.trim()]).toEqual(['Anular', 'Cancelar']);
    await s.submit();
    expect(s.inDoc('sale-void-error')?.textContent).toContain('Hace falta un motivo para anular una venta');
  });
});
