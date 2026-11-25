/* eslint-disable vue/one-component-per-file -- the stubs of the children the test drives */
// «New manual invoice» mounted for its tests (INVOICE-F03): its series select and its customer search are stubs the test
// drives, and the business has answered.
import { defineComponent, h } from 'vue';

import type { Business } from '../../../../base/frontend/operations/business';
import InvoiceCreateModal from '../components/InvoiceCreateModal.vue';
import InvoiceLinesEditor from '../components/InvoiceLinesEditor.vue';
import RecipientFields from '../components/RecipientFields.vue';
import { business, mountInvoice } from './mount-invoice';

/** The series select, as a stub the test drives (its own test follows the live list). */
const SeriesSelectStub = defineComponent({
  name: 'SeriesSelect',
  props: { modelValue: { type: String, default: '' }, invoiceType: { type: String, default: undefined } },
  emits: ['update:modelValue', 'update:invoiceType'],
  setup: () => () => h('div', { 'data-testid': 'series-select-stub' }),
});
const CustomerSearchStub = defineComponent({ name: 'CustomerSearch', setup: () => () => h('div') });

export const DEFAULTS = 'invoice.invoice.line_defaults';
export const SETTINGS = 'tax.settings.get';
const REGIONS: Record<string, string | null> = { vat: null, igic: 'ES-CN', ipsi: 'ES-CE' };
/** Taxes' settings of a business whose territory declares `tax`. */
export const settingsOf = (tax: string) => ({ country_code: 'ES', region_code: REGIONS[tax], regions: ['ES-CN', 'ES-CE', 'ES-ML'], tax_kind: tax, updated_at: null });
export const RECIPIENT = { customerId: null, name: 'Talleres Pérez SL', taxId: 'B12345674', address: 'Calle Luna 3', country: 'ES', idType: '' };
export const CREATED = { id: 'i9', number: 'FACT-2026-000009' };

/** The window open (unless `open` is false: the page mounts it closed), its stream live and the business answered
 *  (`base.business.get`: in Spain, in euros, unless `company` says another; `null` = not answered yet). */
export async function setup(locale: 'en' | 'es' = 'en', company: Partial<Business> | null = {}, open = true) {
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
