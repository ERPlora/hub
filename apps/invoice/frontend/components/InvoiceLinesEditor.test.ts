// The lines of a manual invoice (INVOICE-F03; the old form's rows): «Description», «Qty» (1 to begin
// with), «Price» (VAT not included, euros as typed) and the rate, named by the tax of the business's
// territory («VAT %», «IGIC %», «IPSI %»; «Tax %» while it is not known); «+ Line» adds one at the
// territory's general rate and the cross removes one (never the last). Each line names its hooks by its own id, so removing the first
// never renames the others. What the server refused on a line is said under its field.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountInvoice } from '../__tests__/mount-invoice';
import InvoiceLinesEditor from './InvoiceLinesEditor.vue';
import { blankLine, type DraftLine } from './lines';

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

async function setup(modelValue: DraftLine[] = [blankLine(1)], extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(InvoiceLinesEditor, { props: { modelValue, ...extra }, locale });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value as DraftLine[]);
  const field = (uid: number, key: string) => m.find(`invoice-line-${uid}-${key}`).element;
  return { ...m, emitted, field };
}

describe('InvoiceLinesEditor', () => {
  it('paints each line with its four fields, one unit at the rate it starts with, and no cross on the last one', async () => {
    const s = await setup([blankLine(1, '21')], { tax: 'vat' });
    expect(['description', 'quantity', 'price', 'tax-rate'].map((key) => prop(s.field(1, key), 'label'))).toEqual(['Description', 'Qty', 'Price', 'VAT %']);
    expect([prop(s.field(1, 'quantity'), 'value'), prop(s.field(1, 'tax-rate'), 'value')]).toEqual(['1', '21']);
    expect(prop(s.field(1, 'price'), 'inputmode')).toBe('decimal');
    expect(s.find('invoice-line-1-remove').exists()).toBe(false);
  });

  it('names the rate by the tax of the business’s territory: IGIC in the Canary Islands, IPSI in Ceuta and Melilla', async () => {
    expect(prop((await setup([blankLine(1)], { tax: 'igic' })).field(1, 'tax-rate'), 'label')).toBe('IGIC %');
    expect(prop((await setup([blankLine(1)], { tax: 'ipsi' })).field(1, 'tax-rate'), 'label')).toBe('IPSI %');
    expect(prop((await setup([blankLine(1)])).field(1, 'tax-rate'), 'label')).toBe('Tax %');
  });

  it('«+ Line» starts the new line at the territory’s general rate', async () => {
    const s = await setup([blankLine(1, '7')], { tax: 'igic', defaultRate: '7' });
    await click(s.find('invoice-lines-add').element);
    expect(s.emitted().at(-1)).toEqual([blankLine(1, '7'), blankLine(2, '7')]);
  });

  it('what is typed travels as a new list', async () => {
    const s = await setup();
    await ionValue(s.field(1, 'description'), 'Course', 'ionInput');
    expect(s.emitted().at(-1)).toEqual([{ ...blankLine(1), description: 'Course' }]);
  });

  it('«+ Line» adds one with a new id; the cross removes that one, never renaming the others', async () => {
    const s = await setup([{ ...blankLine(1), description: 'A' }, { ...blankLine(2), description: 'B' }]);
    await click(s.find('invoice-lines-add').element);
    expect(s.emitted().at(-1)?.map((line) => line.uid)).toEqual([1, 2, 3]);
    await s.wrapper.setProps({ modelValue: s.emitted().at(-1) });
    expect(s.find('invoice-line-1-remove').attributes('aria-label')).toBe('Remove line');
    await click(s.find('invoice-line-1-remove').element);
    expect(s.emitted().at(-1)).toEqual([{ ...blankLine(2), description: 'B' }, blankLine(3)]);
  });

  it('says what the server refused on a line under its field', async () => {
    const s = await setup([blankLine(1), blankLine(2)], { fieldErrors: { 'lines.1.quantity': 'Line 2: 0.001 at that price comes to 0.00.' } });
    expect(prop(s.field(2, 'quantity'), 'errorText')).toBe('Line 2: 0.001 at that price comes to 0.00.');
    expect(s.find('invoice-line-2-quantity').classes()).toContain('ion-invalid');
  });

  it('speaks Spanish', async () => {
    const s = await setup([blankLine(1)], { tax: 'vat' }, 'es');
    expect(['description', 'quantity', 'price', 'tax-rate'].map((key) => prop(s.field(1, key), 'label'))).toEqual(['Descripción', 'Cant.', 'Precio', 'IVA %']);
    expect(prop((await setup([blankLine(1)], { tax: 'igic' }, 'es')).field(1, 'tax-rate'), 'label')).toBe('IGIC %');
    expect(prop((await setup([blankLine(1)], {}, 'es')).field(1, 'tax-rate'), 'label')).toBe('Imp. %');
    expect(s.find('invoice-lines-add').text()).toBe('+ Línea');
  });
});
