// The recipient of a full invoice (INVOICE-F03, F05): the customer search of Customers (a card fills the
// fields), «Name or company name», «Country» (Spain first), «Document type» (only abroad: a new country
// resets it to the usual one there), «Tax ID» and «Address». What the server refused is said under its
// field.
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import type { CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { ionValue, mountInvoice } from '../__tests__/mount-invoice';
import { HOME_COUNTRY, type Recipient } from '../lib/recipient';
import RecipientFields from './RecipientFields.vue';

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

/** Customers' search, replaced by a button that hands over a card (its own tests are Customers'). */
const CustomerSearchStub = defineComponent({
  name: 'CustomerSearch',
  props: { modelValue: { type: Object, default: null } },
  emits: ['update:modelValue'],
  setup: () => () => h('div', { 'data-testid': 'customer-search-stub' }),
});

const BLANK: Recipient = { customerId: null, name: '', taxId: '', address: '', country: HOME_COUNTRY, idType: '' };
const CARD: CustomerSnapshot = {
  customer_id: 'c1',
  customer_name: 'Estudio Ana SL',
  customer_tax_id: 'B12345674',
  customer_address: 'Calle Sol 5, 28013 Madrid, España',
  customer_country: 'ES',
};

async function setup(modelValue: Recipient = BLANK, extra: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInvoice(RecipientFields, { props: { modelValue, ...extra }, locale, stubs: { CustomerSearch: CustomerSearchStub } });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map(([value]) => value as Recipient);
  const field = (key: string) => m.find(`invoice-recipient-${key}`).element;
  return { ...m, emitted, field };
}

describe('RecipientFields', () => {
  it('asks name, country, tax ID and address; the document type only abroad', async () => {
    const s = await setup();
    expect(['name', 'country', 'tax-id', 'address'].map((key) => prop(s.field(key), 'label'))).toEqual([
      'Name or company name',
      'Country',
      'Tax ID',
      'Address',
    ]);
    // What VeriFactu's record holds (SuministroInformacion.xsd): NombreRazon 120, IDOtro's ID 20.
    expect([prop(s.field('name'), 'maxlength'), prop(s.field('tax-id'), 'maxlength')]).toEqual([120, 20]);
    expect(s.find('invoice-recipient-id-type').exists()).toBe(false);
    expect(s.find('customer-search-stub').exists()).toBe(true);
    const abroad = await setup({ ...BLANK, country: 'FR', idType: '02' });
    expect(prop(abroad.field('id-type'), 'value')).toBe('02');
  });

  it('what is typed travels as a new value; a new country resets the document type', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Jean Dupont', 'ionInput');
    expect(s.emitted().at(-1)).toEqual({ ...BLANK, name: 'Jean Dupont' });
    await s.wrapper.setProps({ modelValue: s.emitted().at(-1) });
    await ionValue(s.field('country'), 'FR');
    expect(s.emitted().at(-1)).toMatchObject({ name: 'Jean Dupont', country: 'FR', idType: '02' });
  });

  it('a card fills the fields; removing it keeps what is written', async () => {
    const s = await setup();
    s.wrapper.findComponent(CustomerSearchStub).vm.$emit('update:modelValue', CARD);
    await s.wrapper.vm.$nextTick();
    const filled = s.emitted().at(-1)!;
    expect(filled).toEqual({ customerId: 'c1', name: 'Estudio Ana SL', taxId: 'B12345674', address: 'Calle Sol 5, 28013 Madrid, España', country: 'ES', idType: '' });
    await s.wrapper.setProps({ modelValue: filled });
    s.wrapper.findComponent(CustomerSearchStub).vm.$emit('update:modelValue', null);
    await s.wrapper.vm.$nextTick();
    expect(s.emitted().at(-1)).toEqual({ ...filled, customerId: null });
  });

  it('says what the server refused under its field', async () => {
    const s = await setup(BLANK, { fieldErrors: { customer_tax_id: 'That tax ID is not valid.', customer_address: 'This field is required.' } });
    expect(prop(s.field('tax-id'), 'errorText')).toBe('That tax ID is not valid.');
    expect(s.find('invoice-recipient-tax-id').classes()).toContain('ion-invalid');
    expect(prop(s.field('address'), 'errorText')).toBe('This field is required.');
  });

  describe('what the server refused stops being said once it is changed (hub#461)', () => {
    const WRONG: Recipient = { ...BLANK, name: 'Talleres Pérez SL', taxId: 'B12345678', address: 'Calle Luna 3' };
    const REFUSED = { customer_tax_id: 'That tax ID is not valid.', customer_address: 'Write the whole address.' };

    it('the corrected field goes quiet and loses its red; the other keeps its message', async () => {
      const s = await setup(WRONG, { fieldErrors: REFUSED });
      await s.wrapper.setProps({ modelValue: { ...WRONG, taxId: 'B12345674' } });
      expect(prop(s.field('tax-id'), 'errorText')).toBeFalsy();
      expect(s.find('invoice-recipient-tax-id').classes()).not.toContain('ion-invalid');
      expect(prop(s.field('address'), 'errorText')).toBe('Write the whole address.');
      expect(s.find('invoice-recipient-address').classes()).toContain('ion-invalid');
    });

    it('the tax ID is judged with its country and its document type: changing those quiets it too', async () => {
      const s = await setup(WRONG, { fieldErrors: REFUSED });
      await s.wrapper.setProps({ modelValue: { ...WRONG, country: 'FR', idType: '02' } });
      expect(prop(s.field('tax-id'), 'errorText')).toBeFalsy();
      expect(prop(s.field('address'), 'errorText')).toBe('Write the whole address.');
    });

    it('a document type the server refused is marked too: the notice on top promises it', async () => {
      const abroad: Recipient = { ...WRONG, country: 'FR', idType: '' };
      const s = await setup(abroad, { fieldErrors: { customer_id_type: 'Choose the kind of document.' } });
      expect(prop(s.field('id-type'), 'errorText')).toBe('Choose the kind of document.');
      expect(s.find('invoice-recipient-id-type').classes()).toContain('ion-invalid');
      await s.wrapper.setProps({ modelValue: { ...abroad, idType: '02' } });
      expect(prop(s.field('id-type'), 'errorText')).toBeFalsy();
    });

    it('a new refusal is said over whatever is written by then', async () => {
      const s = await setup(WRONG, { fieldErrors: REFUSED });
      const again = { ...WRONG, taxId: 'B00000000' };
      await s.wrapper.setProps({ modelValue: again });
      await s.wrapper.setProps({ fieldErrors: {} });
      await s.wrapper.setProps({ fieldErrors: { customer_tax_id: 'That tax ID is not valid.' } });
      expect(prop(s.field('tax-id'), 'errorText')).toBe('That tax ID is not valid.');
      expect(s.find('invoice-recipient-tax-id').classes()).toContain('ion-invalid');
    });

    it('picking a card tells the form around it, as typing does', async () => {
      const s = await setup(WRONG, { fieldErrors: REFUSED });
      const heard = vi.fn();
      s.wrapper.element.parentElement?.addEventListener('input', heard);
      s.wrapper.findComponent(CustomerSearchStub).vm.$emit('update:modelValue', CARD);
      await s.wrapper.vm.$nextTick();
      expect(heard).toHaveBeenCalledTimes(1);
      s.wrapper.element.parentElement?.removeEventListener('input', heard);
    });
  });

  it('speaks Spanish', async () => {
    const s = await setup({ ...BLANK, country: 'US', idType: '04' }, {}, 'es');
    expect(['name', 'country', 'id-type', 'tax-id', 'address'].map((key) => prop(s.field(key), 'label'))).toEqual([
      'Nombre o razón social',
      'País',
      'Tipo de documento',
      'NIF',
      'Domicilio',
    ]);
  });
});
