// «Void» a charged sale (SALE-F30; the old `erp-sale-void`): the window «Void sale <number>» with the
// explanation, «Reason (required)» and «Void» / «Cancel». Without a reason it says so and sends nothing;
// with one it sends `sale.sale.void`, says «Sale voided» and closes. A refusal (a full invoice, refunds,
// already voided elsewhere) is read inside the window, in the server's words, and the window stays open. The cashier,
// who may not void, is asked for a manager's approval (BASE-F84): approved with the manager's PIN, the very same void
// goes once; «Cancel» on the approval leaves its refusal inside the window, which stays open.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { approvalDialog, approvalSettled, asksApproval, CANCELLED } from '../../__tests__/approval-dialog';
import { click, EMPLOYEE, ionValue, mountSale } from '../../__tests__/mount-sale';
import type { SaleRow } from '../../operations';
import VoidSaleModal from './VoidSaleModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  const { modalControllerStub } = await import('../../__tests__/approval-dialog');
  const ionic = await importOriginal<typeof import('@ionic/vue')>();
  return { ...ionic, IonModal: IonModalStub, modalController: modalControllerStub(ionic.modalController) };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  vi.mocked(toastSuccess).mockClear();
  approvalDialog.reset();
});

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const SALE = { id: 's1', number: '20261014-0007' } as SaleRow;

async function setup(locale: 'en' | 'es' = 'en', session = undefined as typeof EMPLOYEE | undefined) {
  const m = await mountSale(VoidSaleModal, { props: { open: true, sale: SALE }, locale, session });
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

  it('a failure the server did not word says «The sale could not be voided», never the SDK’s English', async () => {
    const s = await setup();
    s.net.onApi(() => {
      throw new TypeError('offline');
    });
    await s.type('Mistake');
    await s.submit();
    expect(s.inDoc('sale-void-error')?.textContent?.trim()).toBe('The sale could not be voided');
    const es = await setup('es');
    es.answer(502, 'Bad gateway');
    await es.type('Error');
    await es.submit();
    expect(es.inDoc('sale-void-error')?.textContent?.trim()).toBe('No se ha podido anular la venta');
  });

  it('the cashier is asked for a manager’s approval, and the manager’s PIN voids the very same sale once', async () => {
    const s = await setup('en', EMPLOYEE);
    let calls = 0;
    s.net.onApi(() => (calls++ === 0 ? Response.json(asksApproval('sale.sale.void', 'Void a sale'), { status: 403 }) : Response.json({ id: 's1', status: 'voided' })));
    await s.type('Wrong table');
    await s.submit();
    await approvalSettled();
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Void a sale']);
    const voids = s.sent().filter((call) => call.path === '/api/sale/sales/void');
    expect(voids.map((call) => call.body)).toEqual([
      { sale_id: 's1', reason: 'Wrong table' },
      { sale_id: 's1', reason: 'Wrong table' },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Sale voided');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
    expect(s.wrapper.emitted('voided')).toHaveLength(1);
  });

  it('«Cancel» on the approval leaves its refusal inside the window, which stays open', async () => {
    const s = await setup('es', EMPLOYEE);
    approvalDialog.answer = CANCELLED;
    s.answer(403, { error: { ...asksApproval('sale.sale.void', 'Anular una venta').error, message: 'Esto necesita la aprobación de un encargado.' } });
    await s.type('Mesa equivocada');
    await s.submit();
    await approvalSettled();
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Anular una venta']);
    expect(s.sent().filter((call) => call.path === '/api/sale/sales/void')).toHaveLength(1);
    expect(s.inDoc('sale-void-error')?.textContent).toContain('Esto necesita la aprobación de un encargado.');
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
