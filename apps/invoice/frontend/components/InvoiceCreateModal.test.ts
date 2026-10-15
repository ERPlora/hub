/* eslint-disable vue/one-component-per-file -- the stubs of the children the test drives */
// «New manual invoice» (INVOICE-F03; the old create panel): the series, the recipient (a card of Customers
// or typed), «Notes» and the lines. «Issue invoice» stays grey until every line has a description, a
// quantity and a price and, for an invoice series (F1), until the recipient has name, tax ID and address;
// a price that is not an amount is said with its line before anything is sent. It runs
// `invoice.invoice.create` with the prices in cents (VAT not included), says «Invoice <number> issued» and
// closes; the list paints the new row by itself. A refusal stays in the window, under its field when it is
// one, and what was written is kept.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { click, ionValue, mountInvoice } from '../__tests__/mount-invoice';
import InvoiceCreateModal from './InvoiceCreateModal.vue';
import InvoiceLinesEditor from './InvoiceLinesEditor.vue';
import RecipientFields from './RecipientFields.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toastSuccess).mockClear());

/** The series select, as a stub the test drives (its own test follows the live list). */
const SeriesSelectStub = defineComponent({
  name: 'SeriesSelect',
  props: { modelValue: { type: String, default: '' }, invoiceType: { type: String, default: undefined } },
  emits: ['update:modelValue', 'update:invoiceType'],
  setup: () => () => h('div', { 'data-testid': 'series-select-stub' }),
});
const CustomerSearchStub = defineComponent({ name: 'CustomerSearch', setup: () => () => h('div') });

const RECIPIENT = { customerId: null, name: 'Talleres Pérez SL', taxId: 'B12345674', address: 'Calle Luna 3', country: 'ES', idType: '' };
const CREATED = { id: 'i9', number: 'FACT-2026-000009' };

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(InvoiceCreateModal, {
    props: { open: true },
    locale,
    stubs: { SeriesSelect: SeriesSelectStub, CustomerSearch: CustomerSearchStub },
  });
  const series = () => m.wrapper.findComponent(SeriesSelectStub);
  async function choose(code: string, type: string) {
    series().vm.$emit('update:modelValue', code);
    series().vm.$emit('update:invoiceType', type);
    await m.wrapper.vm.$nextTick();
  }
  async function recipient(value = RECIPIENT) {
    m.wrapper.findComponent(RecipientFields).vm.$emit('update:modelValue', value);
    await m.wrapper.vm.$nextTick();
  }
  async function line(description: string, price: string, quantity = '1', taxRate = '21') {
    m.wrapper.findComponent(InvoiceLinesEditor).vm.$emit('update:modelValue', [{ uid: 1, description, quantity, price, taxRate }]);
    await m.wrapper.vm.$nextTick();
  }
  const submit = () => m.inDoc('invoice-create-submit') as HTMLElement & { disabled: boolean };
  return { ...m, choose, recipient, line, submit };
}

describe('InvoiceCreateModal', () => {
  it('is «New manual invoice», with the series, the recipient, the notes and one blank line', async () => {
    const s = await setup();
    expect(s.inDoc('invoice-create')?.getAttribute('aria-label')).toBe('New manual invoice');
    expect(s.find('series-select-stub').exists()).toBe(true);
    expect(s.wrapper.findComponent(InvoiceLinesEditor).props('modelValue')).toEqual([{ uid: 1, description: '', quantity: '1', price: '', taxRate: '21' }]);
    expect((s.inDoc('invoice-create-notes') as unknown as { label: string }).label).toBe('Notes');
    expect(s.submit().textContent?.trim()).toBe('Issue invoice');
  });

  it('an invoice series waits for the whole recipient; a ticket series only for the lines', async () => {
    const s = await setup();
    await s.choose('FACT', 'F1');
    await s.line('Course', '100');
    expect(s.submit().disabled).toBe(true);
    await s.recipient();
    expect(s.submit().disabled).toBe(false);
    await s.choose('TICKET', 'F2');
    await s.recipient({ ...RECIPIENT, taxId: '', address: '' });
    expect(s.submit().disabled).toBe(false);
  });

  it('issues the invoice with the prices in cents, says so and closes', async () => {
    const s = await setup();
    await s.choose('FACT', 'F1');
    await s.recipient();
    await s.line('Course', '12,50', '2', '21');
    await ionValue(s.inDoc('invoice-create-notes'), ' Thanks ', 'ionInput');
    s.answer(201, CREATED);
    await click(s.submit());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/invoice/invoices',
        query: {},
        body: {
          series_code: 'FACT',
          customer_name: 'Talleres Pérez SL',
          customer_tax_id: 'B12345674',
          customer_address: 'Calle Luna 3',
          customer_country: '',
          customer_id_type: '',
          notes: 'Thanks',
          lines: [{ description: 'Course', quantity: '2', unit_price: 1250, tax_rate: '21' }],
        },
      },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Invoice FACT-2026-000009 issued');
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('a price that is not an amount is said with its line, and nothing is sent', async () => {
    const s = await setup();
    await s.choose('TICKET', 'F2');
    await s.line('Coffee', '1.2.3');
    await click(s.submit());
    expect(s.sent()).toEqual([]);
    expect(s.inDoc('invoice-create-error')?.textContent).toContain('Line 1: the price is not an amount.');
  });

  it('a refusal stays in the window; a field’s goes under it, and what was written is kept', async () => {
    const s = await setup();
    await s.choose('FACT', 'F1');
    await s.recipient();
    await s.line('Course', '10');
    s.answer(409, { error: { code: 'invoice.recipient_incomplete', message: 'A full invoice needs the customer’s name, tax ID and address.', fields: { customer_tax_id: 'This field is required.' } } });
    await click(s.submit());
    expect(s.inDoc('invoice-create-error')?.textContent).toContain('A full invoice needs');
    expect(s.wrapper.findComponent(RecipientFields).props('fieldErrors')).toEqual({ customer_tax_id: 'This field is required.' });
    expect(s.wrapper.findComponent(InvoiceLinesEditor).props('modelValue')[0].description).toBe('Course');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('invoice-create')?.getAttribute('aria-label')).toBe('Nueva factura manual');
    expect(s.submit().textContent?.trim()).toBe('Emitir factura');
  });
});
