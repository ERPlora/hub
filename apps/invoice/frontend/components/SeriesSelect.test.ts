// The «Series» of a manual invoice (INVOICE-F03): the active series of the latest year that issue invoices
// (F1) or tickets (F2), by code and name, followed live; the default one of the year to begin with, else
// FACT. Without any yet, FACT and TICKET (the server opens them on first use). It tells the form the type
// of the chosen series (an invoice needs the whole recipient; a ticket does not).
import { describe, expect, it } from 'vitest';

import { flush, ionValue, mountInvoice } from '../__tests__/mount-invoice';
import type { SeriesOut } from '../operations';
import SeriesSelect from './SeriesSelect.vue';

const OP = 'invoice.series.list';
const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

const series = (code: string, over: Partial<SeriesOut> = {}): SeriesOut => ({
  id: code,
  code,
  name: code,
  display_name: code,
  invoice_type: 'F1',
  year: 2026,
  prefix: code,
  format: '',
  current_number: 0,
  next_number: `${code}-2026-000001`,
  format_locked: false,
  is_active: true,
  is_default: false,
  ...over,
});
const page = (rows: SeriesOut[]) => ({ rows, total: rows.length, limit: 100, offset: 0 });

async function setup(modelValue = '', locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(SeriesSelect, { props: { modelValue }, locale });
  await m.live();
  const emitted = (name: string) => (m.wrapper.emitted(name) ?? []).map(([value]) => value);
  const options = () => [...m.find('invoice-create-series').element.querySelectorAll('ion-select-option')].map((o) => [prop(o, 'value'), o.textContent?.trim()]);
  return { ...m, emitted, options };
}

describe('SeriesSelect', () => {
  it('follows the active series, the latest year first, up to a hundred', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ is_active: true, sort: 'year', dir: 'desc', limit: 100, offset: 0 }]);
    expect(prop(s.find('invoice-create-series').element, 'label')).toBe('Series');
  });

  it('offers the latest year’s invoice and ticket series, and starts on the default one', async () => {
    const s = await setup();
    await s.result(OP, page([
      series('FACT', { display_name: 'Invoices' }),
      series('WEB', { is_default: true, display_name: 'Web shop' }),
      series('TICKET', { invoice_type: 'F2', display_name: 'POS tickets' }),
      series('RECT', { invoice_type: 'R1' }),
      series('OLD', { year: 2025 }),
    ]));
    expect(s.options()).toEqual([
      ['FACT', 'FACT — Invoices (F1)'],
      ['WEB', 'WEB — Web shop (F1)'],
      ['TICKET', 'TICKET — POS tickets (F2)'],
    ]);
    expect(s.emitted('update:modelValue').at(-1)).toBe('WEB');
    expect(s.emitted('update:invoiceType').at(-1)).toBe('F1');
  });

  it('without a default it starts on FACT; without any series it offers FACT and TICKET', async () => {
    const s = await setup();
    await s.result(OP, page([series('TICKET', { invoice_type: 'F2' }), series('FACT')]));
    expect(s.emitted('update:modelValue').at(-1)).toBe('FACT');
    const empty = await setup();
    await empty.result(OP, page([]));
    expect(empty.options().map(([value]) => value)).toEqual(['FACT', 'TICKET']);
    expect(empty.emitted('update:modelValue').at(-1)).toBe('FACT');
  });

  it('always offers the factory FACT and TICKET the year does not have yet, and starts on FACT', async () => {
    // A till that already numbered tickets this year has no FACT yet: an invoice by hand is still possible
    // (the server opens FACT on first use), and it is where the form starts.
    const s = await setup();
    await s.result(OP, page([series('TICKET', { invoice_type: 'F2', display_name: 'POS tickets' }), series('RECT', { invoice_type: 'R1' })]));
    expect(s.options()).toEqual([
      ['TICKET', 'TICKET — POS tickets (F2)'],
      ['FACT', 'FACT — Invoice (F1)'],
    ]);
    expect(s.emitted('update:modelValue').at(-1)).toBe('FACT');
    expect(s.emitted('update:invoiceType').at(-1)).toBe('F1');
  });

  it('picking one says its type', async () => {
    const s = await setup('FACT');
    await s.result(OP, page([series('FACT'), series('TICKET', { invoice_type: 'F2' })]));
    await ionValue(s.find('invoice-create-series').element, 'TICKET');
    expect(s.emitted('update:modelValue').at(-1)).toBe('TICKET');
    await s.wrapper.setProps({ modelValue: 'TICKET' });
    await flush();
    expect(s.emitted('update:invoiceType').at(-1)).toBe('F2');
  });
});
