// «Send by email» (INVOICE-F26): the address proposed, editable, and one email per press.
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountInvoice, settle } from '../__tests__/mount-invoice';
import SendEmailModal from './SendEmailModal.vue';

const INVOICE = { id: 'i1', number: 'FACT-2026-000001' };
const QUEUED = { id: 'e1', to: 'ana@example.com', status: 'queued', requested_at: '2026-11-24T11:00:00Z', sent_at: null, reason: '' };

async function setup(options: { proposed?: string; locale?: 'en' | 'es' } = {}) {
  const m = await mountInvoice(SendEmailModal, {
    props: { open: true, invoice: INVOICE, proposed: options.proposed ?? 'ana@example.com' },
    locale: options.locale ?? 'en',
  });
  const address = () => m.inDoc('invoice-email-to') as HTMLElement & { value?: string; errorText?: string; label?: string; helperText?: string };
  const submit = () => m.inDoc('invoice-email-submit') as (HTMLElement & { disabled?: boolean }) | null;
  const type = async (value: string) => {
    address().dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(address(), value, 'ionInput');
  };
  return { ...m, address, submit, type };
}

describe('SendEmailModal', () => {
  it('names the invoice and proposes the customer’s email', async () => {
    const s = await setup();
    expect(s.inDoc('invoice-email')?.getAttribute('aria-label')).toBe('Email invoice FACT-2026-000001');
    expect(s.address().value).toBe('ana@example.com');
    expect(s.address().label).toBe('Customer’s email');
    expect(s.submit()?.textContent?.trim()).toBe('Send');
    expect(s.submit()?.disabled).toBe(false);
  });

  it('says what goes and where the replies arrive', async () => {
    const s = await setup();
    expect(s.address().helperText).toBe('The invoice goes attached as a PDF. Replies reach the business owner’s email.');
  });

  it('without an address to propose it waits for one', async () => {
    const s = await setup({ proposed: '' });
    expect(s.submit()?.disabled).toBe(true);
    await s.type('   ');
    expect(s.submit()?.disabled).toBe(true);
    await s.type('luis@example.com');
    expect(s.submit()?.disabled).toBe(false);
  });

  it('sends it to the written address, says so and closes', async () => {
    const s = await setup();
    await s.type(' facturas@example.com ');
    s.answer(200, { ...QUEUED, to: 'facturas@example.com' });
    await click(s.submit());
    const [request] = s.sent();
    expect(request).toMatchObject({ method: 'POST', path: '/api/invoice/emails/send' });
    expect(request.body).toEqual({ invoice_id: 'i1', to: 'facturas@example.com', attempt_key: expect.stringMatching(/^invoice-email-[\w-]{36}$/) });
    expect(toastSuccess).toHaveBeenCalledWith('Sending the invoice to facturas@example.com…');
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a retry of the same email goes with its key; another email, with its own', async () => {
    const s = await setup();
    s.answer(503, { error: { code: 'database_unavailable', message: 'Try again' } });
    await click(s.submit());
    s.answer(200, QUEUED);
    await click(s.submit());
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    await settle();
    s.answer(200, QUEUED);
    await click(s.submit());
    const [first, retry, another] = s.sent().map((request) => (request.body as { attempt_key: string }).attempt_key);
    expect(retry).toBe(first);
    expect(another).not.toBe(first);
  });

  it('a refused address is said under its field and the window stays', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { to: 'This is not an email.' } } });
    await click(s.submit());
    expect(s.address().errorText).toBe('This is not an email.');
    expect(s.address().classList.contains('ion-invalid')).toBe(true);
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('a refusal of the whole email is read inside the window', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'invoice.email_demo', message: 'A demo does not send emails.' } });
    await click(s.submit());
    expect(s.inDoc('invoice-email-error')?.textContent).toContain('A demo does not send emails.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a failure nobody worded says the screen’s own sentence', async () => {
    const s = await setup();
    s.answer(500, { error: { code: 'internal_error', message: 'boom' } });
    await click(s.submit());
    expect(s.inDoc('invoice-email-error')?.textContent).toContain('The invoice could not be sent');
  });

  it('opened again it proposes the customer’s email again', async () => {
    const s = await setup();
    await s.type('other@example.com');
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    await settle();
    expect(s.address().value).toBe('ana@example.com');
  });

  it('takes the customer’s email when it comes after opening, never over what was written', async () => {
    const s = await setup({ proposed: '' });
    await s.wrapper.setProps({ proposed: 'ana@example.com' });
    await settle();
    expect(s.address().value).toBe('ana@example.com');
    await s.type('other@example.com');
    await s.wrapper.setProps({ proposed: 'new@example.com' });
    await settle();
    expect(s.address().value).toBe('other@example.com');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(s.inDoc('invoice-email')?.getAttribute('aria-label')).toBe('Enviar la factura FACT-2026-000001 por correo');
    expect(s.address().label).toBe('Correo del cliente');
    expect(s.address().helperText).toBe('La factura va adjunta en PDF. Las respuestas llegan al correo del propietario del negocio.');
    expect(s.submit()?.textContent?.trim()).toBe('Enviar');
  });
});
