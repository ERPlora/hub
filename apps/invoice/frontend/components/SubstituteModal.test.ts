// «Full invoice» of a ticket (INVOICE-F05: the customer comes back with their ticket and asks for the
// invoice in their name): «Full invoice of ticket <number>», what will happen, the recipient (a card of
// Customers or typed) and «Issue full invoice», grey until name, tax ID and address are there. It runs
// `invoice.invoice.substitute` by the ticket's id, says so, closes and hands the new F3 to the page. A
// refusal is read inside the window; one of a field, under it.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { click, mountInvoice } from '../__tests__/mount-invoice';
import RecipientFields from './RecipientFields.vue';
import SubstituteModal from './SubstituteModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

const CustomerSearchStub = defineComponent({ name: 'CustomerSearch', setup: () => () => h('div') });
const TICKET = { id: 't1', number: 'TICKET-2026-000004' };
const COMPLETE = { customerId: null, name: 'Talleres Pérez SL', taxId: 'B12345674', address: 'Calle Luna 3', country: 'ES', idType: '' };
const ISSUED = { issued: true, already: false, invoice: { id: 'f3', number: 'FACT-2026-000007' } };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(SubstituteModal, { props: { open: true, ticket: TICKET }, locale, stubs: { CustomerSearch: CustomerSearchStub } });
  const fill = async (recipient = COMPLETE) => {
    m.wrapper.findComponent(RecipientFields).vm.$emit('update:modelValue', recipient);
    await m.wrapper.vm.$nextTick();
  };
  const submitButton = () => m.inDoc('invoice-substitute-submit');
  return { ...m, fill, submitButton };
}

describe('SubstituteModal', () => {
  it('is «Full invoice of ticket <number>», with what will happen, grey until the recipient is complete', async () => {
    const s = await setup();
    expect(s.inDoc('invoice-substitute')?.getAttribute('aria-label')).toBe('Full invoice of ticket TICKET-2026-000004');
    expect(s.inDoc('invoice-substitute-intro')?.textContent).toContain('a full invoice (F3) with the same figures replaces it');
    expect(s.submitButton()?.textContent?.trim()).toBe('Issue full invoice');
    expect((s.submitButton() as unknown as { disabled: boolean }).disabled).toBe(true);
    await s.fill();
    expect((s.submitButton() as unknown as { disabled: boolean }).disabled).toBe(false);
  });

  it('issues the full invoice of the ticket with the recipient, says so, closes and hands it over', async () => {
    const s = await setup();
    await s.fill();
    s.answer(200, ISSUED);
    await click(s.submitButton());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/invoice/invoices/substitute',
        query: {},
        body: {
          invoice_id: 't1',
          customer_name: 'Talleres Pérez SL',
          customer_tax_id: 'B12345674',
          customer_address: 'Calle Luna 3',
          customer_country: '',
          customer_id_type: '',
        },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Full invoice FACT-2026-000007 issued');
    expect(s.wrapper.emitted('substituted')?.[0]).toEqual([ISSUED.invoice]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a refusal is read inside the window; one of a field goes under it', async () => {
    const s = await setup();
    await s.fill();
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { customer_tax_id: 'That tax ID is not valid.' } } });
    await click(s.submitButton());
    expect(s.inDoc('invoice-substitute-error')?.textContent).toContain('Invalid payload');
    expect(s.wrapper.findComponent(RecipientFields).props('fieldErrors')).toEqual({ customer_tax_id: 'That tax ID is not valid.' });
    expect(s.wrapper.emitted('substituted')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('invoice-substitute')?.getAttribute('aria-label')).toBe('Factura completa del ticket TICKET-2026-000004');
    expect(s.submitButton()?.textContent?.trim()).toBe('Emitir factura completa');
  });
});
