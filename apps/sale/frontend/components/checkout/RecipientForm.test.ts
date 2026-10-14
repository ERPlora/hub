// SALE-F04 steps 2–4: the recipient of an invoice — «Name or company name», «Country», «Tax ID»,
// «Address» and, only outside Spain, «Kind of document» (EU → «EU VAT number», elsewhere → «Tax ID of
// their country»). Amber while something is missing, with what is asked and why («An invoice needs the
// customer's details», or «This sale cannot be a ticket» over the limit); green once complete: «This
// sale goes out as a complete invoice». Outlined boxes (mode md, so they paint in iOS mode too).
import { HubIcon } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { ionValue, mountSale } from '../../__tests__/mount-sale';
import type { Recipient } from '../../lib/checkout/recipient';
import { plain } from '../../lib/format';
import RecipientForm from './RecipientForm.vue';

type Control = HTMLElement & { label?: string; value?: unknown; fill?: string; labelPlacement?: string; interface?: string };

const BLANK: Recipient = { name: '', taxId: '', address: '', country: 'ES', idType: '' };
const FULL: Recipient = { name: 'Bar Pepe SL', taxId: 'B12345678', address: 'Calle Mayor 1, Madrid', country: 'ES', idType: '' };

async function setup(props: { modelValue?: Recipient; reason?: 'limit' | 'invoice'; max?: number } = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(RecipientForm, { props: { modelValue: BLANK, reason: 'invoice', max: 300000, ...props }, locale });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (modelValue: Recipient) => m.wrapper.setProps({ modelValue }) });
  const field = (name: string) => m.inDoc(`sale-checkout-recipient-${name}`) as Control | null;
  const box = () => m.find('sale-checkout-recipient');
  const heading = () => [box().find('strong').text(), plain(box().find('p').text())];
  const value = () => m.wrapper.props('modelValue') as Recipient;
  return { ...m, field, box, heading, value };
}

describe('RecipientForm', () => {
  it('asks for an invoice’s details in outlined boxes, prefilled from what it has', async () => {
    const s = await setup({ modelValue: { ...FULL, taxId: '' } });
    expect(['name', 'country', 'tax-id', 'address'].map((f) => [s.field(f)?.label, s.field(f)?.fill, s.field(f)?.getAttribute('mode'), s.field(f)?.labelPlacement])).toEqual([
      ['Name or company name', 'outline', 'md', 'stacked'],
      ['Country', 'outline', 'md', 'stacked'],
      ['Tax ID', 'outline', 'md', 'stacked'],
      ['Address', 'outline', 'md', 'stacked'],
    ]);
    expect([s.field('name')?.value, s.field('country')?.value, s.field('tax-id')?.value, s.field('address')?.value]).toEqual([
      'Bar Pepe SL',
      'ES',
      '',
      'Calle Mayor 1, Madrid',
    ]);
    expect(s.field('country')?.interface).toBe('popover');
  });

  it('says what an invoice needs while something is missing, in amber', async () => {
    const s = await setup();
    expect(s.heading()).toEqual([
      "An invoice needs the customer's details",
      'Fill in the name, tax ID and address. If the customer does not need an invoice, choose Receipt.',
    ]);
    expect([s.box().attributes('data-reason'), s.box().attributes('data-done')]).toEqual(['invoice', undefined]);
    expect(s.box().findComponent(HubIcon).props('name')).toBe('ion:alert-circle-outline');
  });

  it('over the ticket limit, says this sale cannot be a ticket, with the limit', async () => {
    const s = await setup({ reason: 'limit' });
    expect(s.heading()).toEqual([
      'This sale cannot be a ticket',
      "Over €3,000.00 the law requires a complete invoice. Fill in the customer's details and charge as usual.",
    ]);
    expect(s.box().attributes('data-reason')).toBe('limit');
  });

  it('turns green once the three are there: the sale goes out as a complete invoice', async () => {
    const s = await setup({ modelValue: { ...FULL, taxId: '' } });
    await ionValue(s.field('tax-id'), 'B12345678', 'ionInput');
    expect(s.value()).toEqual(FULL);
    expect(s.heading()).toEqual([
      'This sale goes out as a complete invoice',
      'The customer is identified, so the document is a full invoice instead of a ticket.',
    ]);
    expect(s.box().attributes('data-done')).toBe('true');
    expect(s.box().findComponent(HubIcon).props('name')).toBe('ion:receipt-outline');
  });

  it('types the name and the address', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Smith Ltd', 'ionInput');
    await ionValue(s.field('address'), '1 High St', 'ionInput');
    expect(s.value()).toMatchObject({ name: 'Smith Ltd', address: '1 High St' });
  });

  it('asks no kind of document in Spain; abroad, it asks, starting on the usual one there', async () => {
    const s = await setup();
    expect(s.field('id-type')).toBeNull();
    await ionValue(s.field('country'), 'PT');
    expect(s.value()).toMatchObject({ country: 'PT', idType: '02' });
    expect([s.field('id-type')?.label, s.field('id-type')?.value, s.field('id-type')?.fill, s.field('id-type')?.getAttribute('mode')]).toEqual([
      'Kind of document',
      '02',
      'outline',
      'md',
    ]);
    const options = () => [...(s.field('id-type')?.querySelectorAll('ion-select-option') ?? [])].map((o) => [(o as Control).value, o.textContent?.trim()]);
    expect(options()).toEqual([
      ['02', 'EU VAT number'],
      ['04', 'Tax ID of their country'],
      ['03', 'Passport'],
      ['06', 'Other document'],
    ]);
    await ionValue(s.field('country'), 'US');
    expect(s.value()).toMatchObject({ country: 'US', idType: '04' });
    await ionValue(s.field('id-type'), '03');
    expect(s.value()).toMatchObject({ country: 'US', idType: '03' });
    await ionValue(s.field('country'), 'ES');
    expect(s.value()).toMatchObject({ country: 'ES', idType: '' });
    expect(s.field('id-type')).toBeNull();
  });

  it('offers every country by its name, Spain first', async () => {
    const s = await setup();
    const options = [...(s.field('country')?.querySelectorAll('ion-select-option') ?? [])];
    expect(options.length).toBeGreaterThan(200);
    expect([(options[0] as Control).value, options[0].textContent?.trim()]).toEqual(['ES', 'Spain']);
  });

  it('speaks Spanish: the old words', async () => {
    const s = await setup({ reason: 'limit' }, 'es');
    expect(['name', 'country', 'tax-id', 'address'].map((f) => s.field(f)?.label)).toEqual(['Nombre o razón social', 'País', 'NIF', 'Domicilio']);
    expect(s.heading()).toEqual([
      'Esta venta no puede ser un tique',
      'Por encima de 3000,00 € la ley obliga a factura completa. Rellena los datos del cliente y cobra como siempre.',
    ]);
    await ionValue(s.field('country'), 'FR');
    expect(s.field('id-type')?.label).toBe('Tipo de documento');
  });
});
