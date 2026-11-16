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

import { expectWindowSaysMoneyUnreadable } from '../../../../base/frontend/__tests__/save-waits-for-money';
import type { Business } from '../../../../base/frontend/operations';
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

/** The window open (unless `open` is false: the page mounts it closed), its stream live and the business answered
 *  (`base.business.get`: in Spain, in euros, unless `company` says another; `null` = not answered yet). */
async function setup(locale: 'en' | 'es' = 'en', company: Partial<Business> | null = {}, open = true) {
  const m = await mountInvoice(InvoiceCreateModal, {
    props: { open },
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
  if (company) await m.result('base.business.get', business(company));
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
      const s = await setup('en', country);
      await s.choose('TICKET', 'F2');
      await s.line('Course', typed);
      s.answer(201, CREATED);
      await click(s.submit());
      expect(s.inDoc('invoice-create-error')).toBeNull();
      expect((s.sent()[0]?.body as { lines: { unit_price: number }[] }).lines[0].unit_price).toBe(cents);
      s.wrapper.unmount();
    }
  });

  it('reads no price before the business’s money answers: «Issue invoice» waits for it, then «12,50 zł» is issued in złoty (hub#907)', async () => {
    const s = await setup('en', null);
    await s.choose('TICKET', 'F2');
    await s.line('Course', '12,50 zł');
    // A click while the business has not answered: the price is not read yet (never «not an amount», never sent).
    await click(s.submit());
    expect(s.inDoc('invoice-create-error')?.textContent ?? '').not.toContain('not an amount');
    expect(s.sent()).toEqual([]);
    expect(s.submit().disabled).toBe(true);
    await s.result('base.business.get', business(POLISH));
    expect(s.submit().disabled).toBe(false);
    s.answer(201, CREATED);
    await click(s.submit());
    expect(s.inDoc('invoice-create-error')).toBeNull();
    expect((s.sent()[0]?.body as { lines: { unit_price: number }[] }).lines[0].unit_price).toBe(1250);
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

  it('correcting a refused field takes away the notice and its message; the next refusal says them again (hub#461)', async () => {
    const s = await setup();
    await s.choose('FACT', 'F1');
    await s.recipient({ ...RECIPIENT, taxId: 'B12345678' });
    await s.line('Course', '10');
    const refused = {
      error: {
        code: 'invalid_payload',
        message: 'Check the highlighted details.',
        fields: { customer_tax_id: 'That tax ID is not valid.', notes: 'Shorten the notes.' },
      },
    };
    s.answer(422, refused);
    await click(s.submit());
    const taxId = s.inDoc('invoice-recipient-tax-id') as HTMLElement & { errorText?: string };
    const notes = s.inDoc('invoice-create-notes') as HTMLElement & { errorText?: string };
    expect([taxId.errorText, notes.errorText]).toEqual(['That tax ID is not valid.', 'Shorten the notes.']);
    expect(notes.classList.contains('ion-invalid')).toBe(true);

    // A person types: the native `input` bubbles out of the field, then Ionic's own event carries the value.
    taxId.dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(taxId, 'B12345674', 'ionInput');
    expect(taxId.errorText).toBeFalsy();
    expect(notes.errorText).toBe('Shorten the notes.');
    expect(s.inDoc('invoice-create-error')).toBeNull();

    s.answer(422, refused);
    await click(s.submit());
    expect(s.inDoc('invoice-create-error')?.textContent).toContain('Check the highlighted details.');
    expect(taxId.errorText).toBe('That tax ID is not valid.');
  });

  // Every field of a line, not the rate alone: each is named by the key the server refuses it under
  // (`lines.<index>.<the command's field>`), which the guardrail cannot check for a field that paints through a function.
  it.each([
    { field: 'description', key: 'description', typed: 'Evening course' },
    { field: 'quantity', key: 'quantity', typed: '2' },
    { field: 'price', key: 'unit_price', typed: '12' },
    { field: 'tax-rate', key: 'tax_rate', typed: '21' },
  ])(
    'two lines whose $field is refused with the same words: the corrected line alone loses them (hub#888)',
    async ({ field, key, typed }) => {
      const s = await setup();
      await s.choose('TICKET', 'F2');
      s.editor().vm.$emit('update:modelValue', [
        { uid: 1, description: 'Course', quantity: '1', price: '10', taxRate: 'x' },
        { uid: 2, description: 'Dye kit', quantity: '1', price: '5', taxRate: 'x' },
      ]);
      await s.wrapper.vm.$nextTick();
      s.answer(422, {
        error: {
          code: 'invalid_payload',
          message: 'Check the highlighted details.',
          fields: { [`lines.0.${key}`]: 'Enter a number.', [`lines.1.${key}`]: 'Enter a number.' },
        },
      });
      await click(s.submit());
      const first = s.inDoc(`invoice-line-1-${field}`) as HTMLElement & { errorText?: string; name?: string };
      const second = s.inDoc(`invoice-line-2-${field}`) as HTMLElement & { errorText?: string; name?: string };
      expect([first.errorText, second.errorText]).toEqual(['Enter a number.', 'Enter a number.']);
      expect([first.name, second.name]).toEqual([`lines.0.${key}`, `lines.1.${key}`]);

      first.dispatchEvent(new Event('input', { bubbles: true }));
      await ionValue(first, typed, 'ionInput');
      expect(first.errorText).toBeFalsy();
      expect(first.classList.contains('ion-invalid')).toBe(false);
      expect(second.errorText).toBe('Enter a number.');
      expect(second.classList.contains('ion-invalid')).toBe(true);
    },
  );

  it('the refused notes lose their message when corrected, though a line says the same words (hub#888)', async () => {
    const s = await setup();
    await s.choose('TICKET', 'F2');
    await s.line('Course', '10');
    s.answer(422, {
      error: {
        code: 'invalid_payload',
        message: 'Check the highlighted details.',
        fields: { notes: 'Enter a valid text.', 'lines.0.description': 'Enter a valid text.' },
      },
    });
    await click(s.submit());
    const notes = s.inDoc('invoice-create-notes') as HTMLElement & { errorText?: string };
    const description = s.inDoc('invoice-line-1-description') as HTMLElement & { errorText?: string };
    expect([notes.errorText, description.errorText]).toEqual(['Enter a valid text.', 'Enter a valid text.']);

    notes.dispatchEvent(new Event('input', { bubbles: true }));
    await ionValue(notes, 'Paid in cash', 'ionInput');
    expect(notes.errorText).toBeFalsy();
    expect(description.errorText).toBe('Enter a valid text.');
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

// hub#938 (INVOICE-F03): if the business's money cannot be read, «New manual invoice» says so with «Retry» instead of
// waiting in grey without a word, also when it opens after the read had failed (the page read the money on loading).
describe('InvoiceCreateModal: a business whose money cannot be read (hub#938)', () => {
  it.each([false, true])('says so with «Retry»; once the yen arrives «Issue invoice» lights up (opened after the failure: %s)', async (late) => {
    const s = await setup('en', null, !late);
    // Each opening starts from blank lines: they are written once open.
    async function fill() {
      await s.choose('TICKET', 'F2');
      await s.line('Course', '1500');
    }
    async function opens() {
      await s.wrapper.setProps({ open: true });
      await fill();
    }
    if (!late) await fill();
    await expectWindowSaysMoneyUnreadable(s, 'invoice-create-submit', s.sent, late ? opens : undefined);
  });
});

describe('InvoiceCreateModal: Android Back with unsaved changes (hub#1020, BASE-F05)', () => {
  it('as opened closes, also once the default rate arrives; notes or a line written ask; restored as opened closes again', async () => {
    const s = await setup();
    await s.territory('vat', '21.00');
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('invoice-create'),
      change: () => ionValue(s.inDoc('invoice-create-notes'), 'Paid by transfer', 'ionInput'),
      restore: () => ionValue(s.inDoc('invoice-create-notes'), '', 'ionInput'),
    });
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('invoice-create'),
      change: () => s.line('Course', '100', '1', '21'),
      restore: () => s.line('', '', '1', '21'),
    });
  });

  it('the series the select picks on opening is no change; another series chosen asks', async () => {
    const s = await setup();
    await s.choose('FACT', 'F1');
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    await expectUnsavedFormAsksBeforeClosing({
      overlay: () => s.inDoc('invoice-create'),
      change: () => s.choose('TICKET', 'F2'),
      restore: () => s.choose('FACT', 'F1'),
    });
  });
});
