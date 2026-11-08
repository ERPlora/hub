// «Full invoice» of a ticket (INVOICE-F05: the customer comes back with their ticket and asks for the
// invoice in their name): «Full invoice of ticket <number>», what will happen, the recipient (a card of
// Customers or typed) and «Issue full invoice», grey until name, tax ID and address are there. It runs
// `invoice.invoice.substitute` by the ticket's id, says so, closes and hands the new F3 to the page. A
// refusal is read inside the window; one of a field, under it.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { click, ionValue, mountInvoice, settle } from '../__tests__/mount-invoice';
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
    s.answer(422, { error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { customer_tax_id: 'That tax ID is not valid.' } } });
    await click(s.submitButton());
    expect(s.inDoc('invoice-substitute-error')?.textContent).toContain('Check the highlighted details.');
    expect(s.wrapper.findComponent(RecipientFields).props('fieldErrors')).toEqual({ customer_tax_id: 'That tax ID is not valid.' });
    expect(s.wrapper.emitted('substituted')).toBeUndefined();
  });

  it('correcting the refused tax ID takes away the notice and the message under it; the next refusal says them again (hub#461)', async () => {
    const s = await setup();
    await s.fill({ ...COMPLETE, taxId: 'B12345678' });
    const refused = { error: { code: 'invalid_payload', message: 'Check the highlighted details.', fields: { customer_tax_id: 'That tax ID is not valid.' } } };
    s.answer(422, refused);
    await click(s.submitButton());
    const taxId = s.inDoc('invoice-recipient-tax-id') as HTMLElement & { errorText?: string };
    expect(taxId.errorText).toBe('That tax ID is not valid.');

    // A person types: the native `input` bubbles out of the field, then Ionic's own event carries the value.
    taxId.dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(taxId, 'B12345670', 'ionInput');

    expect(s.inDoc('invoice-substitute-error')).toBeNull();
    expect(taxId.errorText).toBeFalsy();
    expect(taxId.classList.contains('ion-invalid')).toBe(false);

    s.answer(422, refused);
    await click(s.submitButton());
    expect(s.inDoc('invoice-substitute-error')?.textContent).toContain('Check the highlighted details.');
    expect(taxId.errorText).toBe('That tax ID is not valid.');
  });

  describe('what fills a field with no keystroke takes its message away too (hub#461)', () => {
    const REFUSED = {
      error: {
        code: 'invalid_payload',
        message: 'Check the highlighted details.',
        fields: { customer_tax_id: 'That tax ID is not valid.', customer_address: 'Write the whole address.' },
      },
    };
    const CARD = { customer_id: 'c1', customer_name: 'Estudio Ana SL', customer_tax_id: 'B12345674', customer_address: 'Calle Sol 5, Madrid', customer_country: 'ES' };
    const said = (s: Awaited<ReturnType<typeof setup>>, key: string) =>
      (s.inDoc(`invoice-recipient-${key}`) as (HTMLElement & { errorText?: string }) | null)?.errorText;
    const red = (s: Awaited<ReturnType<typeof setup>>, key: string) => !!s.inDoc(`invoice-recipient-${key}`)?.classList.contains('ion-invalid');

    async function refused() {
      const s = await setup();
      await s.fill({ ...COMPLETE, taxId: 'B12345678', address: 'Calle' });
      s.answer(422, REFUSED);
      await click(s.submitButton());
      expect([said(s, 'tax-id'), said(s, 'address')]).toEqual(['That tax ID is not valid.', 'Write the whole address.']);
      return s;
    }

    it('a picked customer card quiets the fields it fills, and the notice on top', async () => {
      const s = await refused();
      s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', CARD);
      await settle();
      expect(said(s, 'tax-id')).toBeFalsy();
      expect(said(s, 'address')).toBeFalsy();
      expect([red(s, 'tax-id'), red(s, 'address')]).toEqual([false, false]);
      expect(s.inDoc('invoice-substitute-error')).toBeNull();
    });

    it('a new country quiets the tax ID, judged with its country, and keeps the address’s message', async () => {
      const s = await refused();
      await ionValue(s.inDoc('invoice-recipient-country'), 'FR');
      expect(said(s, 'tax-id')).toBeFalsy();
      expect(said(s, 'address')).toBe('Write the whole address.');
      expect([red(s, 'tax-id'), red(s, 'address')]).toEqual([false, true]);
    });
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('invoice-substitute')?.getAttribute('aria-label')).toBe('Factura completa del ticket TICKET-2026-000004');
    expect(s.submitButton()?.textContent?.trim()).toBe('Emitir factura completa');
  });
});

describe('SubstituteModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes; a recipient written asks; emptied again closes', async () => {
    const s = await setup();
    const blank = s.wrapper.findComponent(RecipientFields).props('modelValue');
    const { expectUnsavedFormOnAndroidBack } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormOnAndroidBack({
      overlay: () => s.inDoc('invoice-substitute'),
      change: () => s.fill(),
      restore: () => s.fill(blank),
    });
  });
});
