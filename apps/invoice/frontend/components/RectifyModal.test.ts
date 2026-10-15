// «Rectify» an invoice (INVOICE-F08; the old «Devolución» dialog): «Rectify <number>», the note of what will
// happen, the type of rectifying invoice (R1 by default, R2–R4 to choose; a ticket is always R5 and says
// so), «Reason» (required) and «Issue rectifying invoice». Without a reason it says so and sends nothing;
// with one it runs `invoice.invoice.rectify` (no date: the server dates it today) and shows the result in
// the same window, with «Close». A rectifying or cancelled invoice only says why; a refusal is read inside
// the window in the server's words.
import { describe, expect, it, vi } from 'vitest';

import { click, ionValue, mountInvoice } from '../__tests__/mount-invoice';
import RectifyModal from './RectifyModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const FULL = { id: 'i1', number: 'FACT-2026-000001', invoice_type: 'F1', status: 'issued' };
const ISSUED = {
  issued: true,
  already: false,
  invoice: { id: 'r1', number: 'RECT-2026-000001', rectifies: { id: 'i1', number: 'FACT-2026-000001', status: 'cancelled' } },
};

async function setup(invoice: Record<string, unknown> = FULL, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(RectifyModal, { props: { open: true, invoice }, locale });
  const reason = () => m.inDoc('invoice-rectify-reason');
  const type = () => m.inDoc('invoice-rectify-type');
  const submit = () => click(m.inDoc('invoice-rectify-submit'));
  return { ...m, reason, type, submit };
}

describe('RectifyModal', () => {
  it('is «Rectify <number>» with the note, the type (R1 by default) and the reason', async () => {
    const s = await setup();
    expect(s.inDoc('invoice-rectify')?.getAttribute('aria-label')).toBe('Rectify FACT-2026-000001');
    expect(s.inDoc('invoice-rectify-note')?.textContent).toContain('A rectifying invoice (RECT series) will be issued');
    expect(prop(s.type(), 'value')).toBe('R1');
    expect([...(s.type()?.querySelectorAll('ion-select-option') ?? [])].map((o) => prop(o, 'value'))).toEqual(['R1', 'R2', 'R3', 'R4']);
    expect([prop(s.reason(), 'label'), prop(s.reason(), 'fill'), prop(s.reason(), 'maxlength')]).toEqual(['Reason', 'outline', 500]);
    expect(s.inDoc('invoice-rectify-submit')?.textContent?.trim()).toBe('Issue rectifying invoice');
  });

  it('a ticket is always R5: no choice, it says so', async () => {
    const s = await setup({ ...FULL, number: 'TICKET-2026-000004', invoice_type: 'F2' });
    expect(s.type()).toBeNull();
    expect(s.inDoc('invoice-rectify-simplified')?.textContent).toContain('R5');
  });

  it('without a reason it says so and sends nothing', async () => {
    const s = await setup();
    await ionValue(s.reason(), '   ', 'ionInput');
    await s.submit();
    expect(s.sent()).toEqual([]);
    expect(s.inDoc('invoice-rectify-error')?.textContent).toContain('Write the reason of the rectification.');
  });

  it('issues the rectifying invoice with the reason and the type, and shows the result in the window', async () => {
    const s = await setup();
    await ionValue(s.type(), 'R4');
    await ionValue(s.reason(), ' Wrong price ', 'ionInput');
    s.answer(200, ISSUED);
    await s.submit();
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/invoice/invoices/rectify', query: {}, body: { invoice_id: 'i1', reason: 'Wrong price', rectification_type: 'R4' } },
    ]);
    expect(s.inDoc('invoice-rectify-done')?.textContent).toContain('Rectifying invoice RECT-2026-000001 issued. FACT-2026-000001 is cancelled.');
    expect(s.wrapper.emitted('rectified')?.[0]).toEqual([ISSUED.invoice]);
    expect(s.inDoc('invoice-rectify-reason')).toBeNull();
    await click(s.inDoc('invoice-rectify-close-result'));
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a ticket sends no type: the server makes it R5', async () => {
    const s = await setup({ ...FULL, invoice_type: 'F2' });
    await ionValue(s.reason(), 'x', 'ionInput');
    s.answer(200, ISSUED);
    await s.submit();
    expect(s.sent()[0].body).toEqual({ invoice_id: 'i1', reason: 'x' });
  });

  it('a rectifying or a cancelled invoice only says why', async () => {
    const rect = await setup({ ...FULL, invoice_type: 'R1' });
    expect(rect.inDoc('invoice-rectify-blocked')?.textContent).toContain('A rectifying invoice cannot be rectified.');
    expect(rect.reason()).toBeNull();
    const cancelled = await setup({ ...FULL, status: 'cancelled' });
    expect(cancelled.inDoc('invoice-rectify-blocked')?.textContent).toContain('The invoice is already cancelled.');
  });

  it('a refusal is read inside the window, in the server’s words', async () => {
    const s = await setup();
    await ionValue(s.reason(), 'x', 'ionInput');
    s.answer(409, { error: { code: 'invoice.already_cancelled', message: 'The invoice is already cancelled.' } });
    await s.submit();
    expect(s.inDoc('invoice-rectify-error')?.textContent).toContain('The invoice is already cancelled.');
    expect(s.wrapper.emitted('rectified')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup(FULL, 'es');
    expect(s.inDoc('invoice-rectify')?.getAttribute('aria-label')).toBe('Rectificar FACT-2026-000001');
    expect(prop(s.reason(), 'label')).toBe('Motivo');
    expect(s.inDoc('invoice-rectify-submit')?.textContent?.trim()).toBe('Emitir rectificativa');
  });
});
