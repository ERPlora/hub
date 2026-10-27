/* eslint-disable vue/one-component-per-file -- the stubs of the children the test drives */
// «New manual invoice» (INVOICE-F03; the old create panel): the series, the recipient (a card of Customers
// or typed), «Notes» and the lines. «Issue invoice» stays grey until every line has a description, a
// quantity and a price and, for an invoice series (F1), until the recipient has name, tax ID and address;
// a price that is not an amount is said with its line before anything is sent. It runs
// `invoice.invoice.create` with the prices in cents (VAT not included), says «Invoice <number> issued» and
// closes; the list paints the new row by itself. A refusal stays in the window, under its field when it is
// one, and what was written is kept. The rate of a line is named by the tax of the business's territory, as
// Taxes publishes it (`tax.settings.get`, followed live): IGIC in the Canary Islands, IPSI in Ceuta and
// Melilla, VAT elsewhere; it starts at the territory's general rate (`invoice.invoice.line_defaults`, live);
// without a rule of its own tax, the person types it.
import { toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { business, click, errorFrame, flush, ionValue, JAPANESE, mountInvoice, POLISH } from '../__tests__/mount-invoice';
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

const DEFAULTS = 'invoice.invoice.line_defaults';
const SETTINGS = 'tax.settings.get';
const REGIONS: Record<string, string | null> = { vat: null, igic: 'ES-CN', ipsi: 'ES-CE' };
/** Taxes' settings of a business whose territory declares `tax`. */
const settingsOf = (tax: string) => ({ country_code: 'ES', region_code: REGIONS[tax], regions: ['ES-CN', 'ES-CE', 'ES-ML'], tax_kind: tax, updated_at: null });
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
  const editor = () => m.wrapper.findComponent(InvoiceLinesEditor);
  const call = await m.live();
  /** The business's territory (its tax, from Taxes) and the rate a typed line starts with there. */
  async function territory(tax: string, rate: string | null) {
    await m.result(SETTINGS, settingsOf(tax));
    await m.result(DEFAULTS, { tax_rate: rate });
  }
  return { ...m, call, choose, recipient, line, submit, editor, territory };
}

describe('InvoiceCreateModal', () => {
  it('is «New manual invoice», with the series, the recipient, the notes and one blank line', async () => {
    const s = await setup();
    expect(s.inDoc('invoice-create')?.getAttribute('aria-label')).toBe('New manual invoice');
    expect(s.find('series-select-stub').exists()).toBe(true);
    await s.territory('vat', '21.00');
    expect(s.editor().props('modelValue')).toEqual([{ uid: 1, description: '', quantity: '1', price: '', taxRate: '21' }]);
    expect(s.editor().props('tax')).toBe('vat');
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

  it('reads each price in the business’s money: «12,50 zł» in Poland, «1.234» yen in Japan (flow business-currency)', async () => {
    for (const [country, typed, cents] of [[POLISH, '12,50 zł', 1250], [JAPANESE, '1.234', 1234]] as const) {
      const s = await setup();
      await s.result('base.business.get', business(country));
      await s.choose('TICKET', 'F2');
      await s.line('Course', typed);
      s.answer(201, CREATED);
      await click(s.submit());
      expect(s.inDoc('invoice-create-error')).toBeNull();
      expect((s.sent()[0]?.body as { lines: { unit_price: number }[] }).lines[0].unit_price).toBe(cents);
      s.wrapper.unmount();
    }
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

  it('follows what a typed line starts with: the territory’s tax (from Taxes) and its general rate', async () => {
    const s = await setup();
    expect(s.params(DEFAULTS)).toEqual([{}]);
    expect(s.params(SETTINGS)).toEqual([{}]);
    await s.territory('igic', '7.00');
    expect(s.editor().props('modelValue')[0].taxRate).toBe('7');
    expect([s.editor().props('tax'), s.editor().props('defaultRate')]).toEqual(['igic', '7']);
  });

  it('a change of territory renames the rate of the lines', async () => {
    const s = await setup();
    await s.territory('igic', '7.00');
    await s.result(SETTINGS, settingsOf('vat'), {}, 2);
    expect(s.editor().props('tax')).toBe('vat');
  });

  it('when the territory’s tax cannot be read the rate is a plain «Tax %», still at the general rate', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(SETTINGS), 'tax.boom'));
    await s.result(DEFAULTS, { tax_rate: '7.00' });
    expect([s.editor().props('tax'), s.editor().props('defaultRate')]).toEqual([undefined, '7']);
    expect(s.inDoc('invoice-create-error')).toBeNull();
  });

  it('opened again, a fresh line starts at the territory’s rate already known', async () => {
    const s = await setup();
    await s.territory('igic', '7.00');
    await s.line('Course', '10', '1', '3');
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    expect(s.editor().props('modelValue')).toEqual([{ uid: 1, description: '', quantity: '1', price: '', taxRate: '7' }]);
  });

  it('a territory without a rule of its own tax starts with no rate, and «Issue invoice» waits for one', async () => {
    const s = await setup();
    await s.territory('ipsi', null);
    expect(s.editor().props('modelValue')[0].taxRate).toBe('');
    await s.choose('TICKET', 'F2');
    await s.line('Coffee', '1,50', '1', '');
    expect(s.submit().disabled).toBe(true);
    await s.line('Coffee', '1,50', '1', '4');
    expect(s.submit().disabled).toBe(false);
  });

  it('a rate already typed is kept when the territory’s answer arrives or changes', async () => {
    const s = await setup();
    await s.line('Course', '10', '1', '3');
    await s.territory('igic', '7.00');
    expect(s.editor().props('modelValue')[0].taxRate).toBe('3');
    await s.line('Course', '10', '1', '7');
    await s.result(DEFAULTS, { tax_rate: '9.50' }, {}, 2);
    expect(s.editor().props('modelValue')[0].taxRate).toBe('9.5');
  });

  it('says when the territory cannot be read; the rate can still be typed', async () => {
    const s = await setup();
    s.call.push(errorFrame(s.subId(DEFAULTS), 'invoice.boom'));
    await flush();
    expect(s.inDoc('invoice-create-error')?.textContent).toContain('Could not read the business’s tax territory: type the rate of each line.');
    expect(s.editor().props('tax')).toBeUndefined();
    await s.choose('TICKET', 'F2');
    await s.line('Coffee', '1,50', '1', '7');
    expect(s.submit().disabled).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('invoice-create')?.getAttribute('aria-label')).toBe('Nueva factura manual');
    expect(s.submit().textContent?.trim()).toBe('Emitir factura');
  });
});
