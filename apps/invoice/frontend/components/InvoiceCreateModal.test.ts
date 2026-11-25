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
import { DateField } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { pick, picked } from '../../../../base/frontend/__tests__/date-time-fields';
import { expectWindowSaysMoneyUnreadable } from '../../../../base/frontend/__tests__/save-waits-for-money';
import type { Business } from '../../../../base/frontend/operations/business';
import { CREATED, DEFAULTS, RECIPIENT, SETTINGS, settingsOf, setup } from '../__tests__/invoice-create';
import { business, click, errorFrame, flush, ionValue, JAPANESE, POLISH } from '../__tests__/mount-invoice';
import InvoiceLinesEditor from './InvoiceLinesEditor.vue';
import RecipientFields from './RecipientFields.vue';

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
    await s.line('Course', '12,50', { quantity: '2' });
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
    await s.line('Course', '10', { taxRate: '3' });
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    expect(s.editor().props('modelValue')).toEqual([{ uid: 1, description: '', quantity: '1', price: '', taxRate: '7' }]);
  });

  it('a territory without a rule of its own tax starts with no rate, and «Issue invoice» waits for one', async () => {
    const s = await setup();
    await s.territory('ipsi', null);
    expect(s.editor().props('modelValue')[0].taxRate).toBe('');
    await s.choose('TICKET', 'F2');
    await s.line('Coffee', '1,50', { taxRate: '' });
    expect(s.submit().disabled).toBe(true);
    await s.line('Coffee', '1,50', { taxRate: '4' });
    expect(s.submit().disabled).toBe(false);
  });

  it('a rate already typed is kept when the territory’s answer arrives or changes', async () => {
    const s = await setup();
    await s.line('Course', '10', { taxRate: '3' });
    await s.territory('igic', '7.00');
    expect(s.editor().props('modelValue')[0].taxRate).toBe('3');
    await s.line('Course', '10', { taxRate: '7' });
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
    await s.line('Coffee', '1,50', { taxRate: '7' });
    expect(s.submit().disabled).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('invoice-create')?.getAttribute('aria-label')).toBe('Nueva factura manual');
    expect(s.submit().textContent?.trim()).toBe('Emitir factura');
  });
});

describe('InvoiceCreateModal: the day it is dated and the day it falls due', () => {
  // 23:30 of the 24th in the Canary Islands, 00:30 of the 25th in Madrid.
  beforeEach(() => vi.useFakeTimers({ now: new Date('2026-11-24T23:30:00Z'), toFake: ['Date'] }));
  afterEach(() => vi.useRealTimers());

  type Field = HTMLElement & { label?: string; errorText?: string };
  async function dates(company: Partial<Business> = { timezone: 'Atlantic/Canary' }, locale: 'en' | 'es' = 'en') {
    const s = await setup(locale, company);
    await s.choose('TICKET', 'F2');
    await s.line('Course', '10');
    const issued = () => s.inDoc('invoice-create-issue-date') as Field;
    const due = () => s.inDoc('invoice-create-due-date') as Field;
    /** What the window sends of the two dates. */
    async function sent() {
      s.answer(201, CREATED);
      await click(s.submit());
      const { issue_date, due_date } = s.sent().at(-1)?.body as { issue_date?: string; due_date?: string };
      return { issue_date, due_date };
    }
    return { ...s, issued, due, sent };
  }

  it('is dated today on the business’s clock and has no due date, and the server is told neither', async () => {
    const s = await dates();
    expect([s.issued().label, picked(s.issued()), s.due().label, picked(s.due())]).toEqual(['Date', '2026-11-24', 'Due date', '']);
    expect(await s.sent()).toEqual({ issue_date: undefined, due_date: undefined });
    expect(picked((await dates({ timezone: 'Europe/Madrid' })).issued())).toBe('2026-11-25');
  });

  it('sends the day and the due date chosen', async () => {
    const s = await dates();
    await pick(s.issued(), '2026-11-23');
    await pick(s.due(), '2026-12-23');
    expect(await s.sent()).toEqual({ issue_date: '2026-11-23', due_date: '2026-12-23' });
  });

  it('today chosen again, or a due date cleared, is as if nobody had', async () => {
    const s = await dates();
    await pick(s.issued(), '2026-11-23');
    await pick(s.issued(), '2026-11-24');
    await pick(s.due(), '2026-12-23');
    await pick(s.due(), '');
    expect(await s.sent()).toEqual({ issue_date: undefined, due_date: undefined });
  });

  it('offers no day after today, nor a due date before the day it is dated', async () => {
    const s = await dates();
    const limits = () => s.wrapper.findAllComponents(DateField).map((field) => [field.props('min'), field.props('max'), field.props('required')]);
    expect(limits()).toEqual([
      [undefined, '2026-11-24', true],
      ['2026-11-24', undefined, false],
    ]);
    await pick(s.issued(), '2026-11-20');
    expect(limits()[1][0]).toBe('2026-11-20');
  });

  it('a refusal of a date goes under it, and goes away when another is chosen', async () => {
    const s = await dates();
    const fields = { issue_date: 'Before the last invoice.', due_date: 'Before its date.' };
    s.answer(409, { error: { code: 'invoice.issue_date_before_last', message: 'Before the last invoice.', fields } });
    await click(s.submit());
    expect([s.issued().errorText, s.due().errorText]).toEqual(['Before the last invoice.', 'Before its date.']);
    await pick(s.issued(), '2026-11-24');
    expect([s.issued().errorText || null, s.due().errorText]).toEqual([null, 'Before its date.']);
  });

  it('opened again, starts on today and without a due date', async () => {
    const s = await dates();
    await pick(s.issued(), '2026-11-20');
    await pick(s.due(), '2026-12-20');
    await s.wrapper.setProps({ open: false });
    vi.setSystemTime(new Date('2026-11-26T10:00:00Z'));
    await s.wrapper.setProps({ open: true });
    expect([picked(s.issued()), picked(s.due())]).toEqual(['2026-11-26', '']);
  });

  it('Android Back asks once a date is chosen, and no more once it is as it was', async () => {
    const s = await dates();
    await s.line('', '', { taxRate: '' });
    const { expectUnsavedFormAsksBeforeClosing } = await import('../../../../base/frontend/__tests__/unsaved-form');
    const overlay = () => s.inDoc('invoice-create');
    await expectUnsavedFormAsksBeforeClosing({ overlay, change: () => pick(s.issued(), '2026-11-23'), restore: () => pick(s.issued(), '2026-11-24') });
    await expectUnsavedFormAsksBeforeClosing({ overlay, change: () => pick(s.due(), '2026-12-23'), restore: () => pick(s.due(), '') });
  });

  it('speaks Spanish', async () => {
    const s = await dates({}, 'es');
    expect([s.issued().label, s.due().label]).toEqual(['Fecha', 'Vencimiento']);
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
      change: () => s.line('Course', '100'),
      restore: () => s.line('', ''),
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
