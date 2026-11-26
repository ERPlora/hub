// «Send by email» of the open invoice (INVOICE-F26): for whoever issues invoices, and what became of each email.
import { describe, expect, it } from 'vitest';

import SendEmailModal from '../components/SendEmailModal.vue';
import { INVOICE, setup } from '../__tests__/invoice-detail';
import { ACCOUNTANT, EMPLOYEE, MANAGER, redNotices } from '../__tests__/mount-invoice';
import { plain } from '../lib/format';
import type { InvoiceEmailOut } from '../operations/emails';
import { accessibleName } from '../../../../base/frontend/__tests__/mount-base';

const LIST = 'invoice.email.list';
const SENT: InvoiceEmailOut = {
  id: 'e1',
  to: 'ana@example.com',
  status: 'sent',
  requested_at: '2026-11-24T11:00:00Z',
  sent_at: '2026-11-24T11:00:05Z',
  reason: '',
};
const FAILED: InvoiceEmailOut = { ...SENT, id: 'e2', status: 'failed', sent_at: null, reason: 'That address does not accept the email.' };

async function opened(emails: InvoiceEmailOut[] = [], options: Parameters<typeof setup>[0] = {}, customer_email: string | null = 'ana@example.com') {
  const s = await setup(options);
  await s.show(INVOICE);
  await s.result(LIST, { customer_email, emails });
  const said = () => s.wrapper.findAll('[data-testid="invoice-detail-emailed"]').map((line) => plain(line.text()));
  const window = () => s.wrapper.findComponent(SendEmailModal);
  return { ...s, said, window };
}

describe('InvoiceDetailPage: «Send by email»', () => {
  it('asks for the emails of this invoice', async () => {
    const s = await opened();
    expect(s.client.stream.subscriptions(LIST).map((call) => call.params)).toEqual([{ invoice_id: 'i1' }]);
  });

  it.each([['the manager', MANAGER], ['an employee', EMPLOYEE]])('is offered to %s', async (_who, session) => {
    const s = await opened([], { session });
    expect(accessibleName(s.find('invoice-detail-email').element)).toBe('Send by email');
  });

  it('is not offered to whoever only reads, who sees what was sent', async () => {
    const s = await opened([SENT], { session: ACCOUNTANT });
    expect(s.find('invoice-detail-email').exists()).toBe(false);
    expect(s.window().exists()).toBe(false);
    expect(s.said()).toHaveLength(1);
  });

  it('opens the window of this invoice with the customer’s email', async () => {
    const s = await opened();
    expect(s.window().props()).toMatchObject({ open: false, proposed: 'ana@example.com', invoice: { id: 'i1', number: 'FACT-2026-000001' } });
    await s.find('invoice-detail-email').trigger('click');
    expect(s.window().props('open')).toBe(true);
  });

  it('proposes nothing to whoever does not see the customers’ contact details', async () => {
    const s = await opened([], {}, null);
    expect(s.window().props('proposed')).toBe('');
  });

  it('can be pressed before the emails came', async () => {
    const s = await setup();
    await s.show(INVOICE);
    await s.find('invoice-detail-email').trigger('click');
    expect(s.wrapper.findComponent(SendEmailModal).props()).toMatchObject({ open: true, proposed: '' });
  });

  it('one never sent says nothing of emails', async () => {
    const s = await opened();
    expect(s.said()).toEqual([]);
    expect(s.find('invoice-detail-email-failed').exists()).toBe(false);
  });

  it('says to whom and when each email was sent', async () => {
    const s = await opened([{ ...SENT, id: 'e3', to: 'luis@example.com', sent_at: '2026-11-25T09:30:00Z' }, SENT]);
    expect(s.said()[0]).toMatch(/^Sent to luis@example\.com on .*2026/);
    expect(s.said()[1]).toMatch(/^Sent to ana@example\.com on .*2026/);
  });

  it('follows an email on its way until it is sent', async () => {
    const s = await opened([{ ...SENT, status: 'queued', sent_at: null }]);
    expect(s.said()).toEqual(['Sending to ana@example.com…']);
    await s.result(LIST, { customer_email: '', emails: [SENT] }, {}, 2);
    expect(s.said()[0]).toMatch(/^Sent to ana@example\.com on /);
  });

  it('says why the last one did not leave, until another does', async () => {
    const s = await opened([FAILED, SENT]);
    const notice = s.find('invoice-detail-email-failed');
    expect(notice.text()).toContain('The invoice was not sent by email');
    // A long address would not fit in the notice of a phone: the row below says it.
    expect(notice.text()).not.toContain('ana@example.com');
    expect(s.said()[0]).toBe('Not sent to ana@example.com');
    expect(notice.text()).toContain('That address does not accept the email.');
    expect(redNotices(s)).toBe(1);
    await s.result(LIST, { customer_email: '', emails: [SENT, FAILED] }, {}, 2);
    expect(s.find('invoice-detail-email-failed').exists()).toBe(false);
  });

  it('leaves the other buttons where they were', async () => {
    const s = await opened();
    for (const other of ['print', 'pdf', 'back']) expect(s.find(`invoice-detail-${other}`).exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await opened([FAILED, SENT], { locale: 'es' });
    expect(accessibleName(s.find('invoice-detail-email').element)).toBe('Enviar por correo');
    expect(s.said()[0]).toBe('No enviada a ana@example.com');
    expect(s.said()[1]).toMatch(/^Enviada a ana@example\.com el /);
    expect(s.find('invoice-detail-email-failed').text()).toContain('La factura no se ha enviado por correo');
  });
});
