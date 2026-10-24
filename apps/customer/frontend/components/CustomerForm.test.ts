/* eslint-disable vue/one-component-per-file -- the ion-popover stub and the host of each case */
// The card's form (CUSTOMER-F01, F04, F11): one form for «Add» and «Edit». Name, phone, email, tax
// id and company in sight; the rest behind «More details» when adding; in «Edit» everything, the
// custom fields with their own control and «Active». The server's 422 lands under its field, and so does
// a number or a date the browser cannot read, which stops the save. The
// country is the shared Combo (the product's `ok-combo`, customers#72): typed to filter, stored as
// its ISO code, clearable.
import { Combo, type ComboOption } from '@erplora/ui/components';
import { IonCheckbox, IonInput, IonSelect, IonTextarea } from '@ionic/vue';
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { flush, mountCustomer } from '../__tests__/mount-customer';
import { countryOptions } from '../lib/countries';
import { blankCustomer, type CustomerFields } from '../lib/customerForm';
import type { CustomFieldValueOut } from '../operations';
import CustomerForm from './CustomerForm.vue';
import source from './CustomerForm.vue?raw';

const FIELDS: CustomFieldValueOut[] = [
  { field_id: 'f1', name: 'Allergies', field_type: 'textarea', options: [], is_required: true, sort_order: 0, value: 'Nuts' },
  { field_id: 'f2', name: 'Dye', field_type: 'select', options: ['Blonde', 'Brown'], is_required: false, sort_order: 1, value: '' },
  { field_id: 'f3', name: 'Newsletter', field_type: 'boolean', options: [], is_required: false, sort_order: 2, value: 'true' },
  { field_id: 'f4', name: 'Visits', field_type: 'number', options: [], is_required: false, sort_order: 3, value: '' },
  { field_id: 'f5', name: 'First visit', field_type: 'date', options: [], is_required: false, sort_order: 4, value: '' },
  { field_id: 'f6', name: 'Hair type', field_type: 'text', options: [], is_required: false, sort_order: 5, value: '' },
];

/** `ion-popover` presents itself only in a real browser: the stub shows the Combo's list while open. */
const PopoverStub = defineComponent({
  name: 'IonPopover',
  inheritAttrs: false,
  props: { isOpen: Boolean, event: { type: null, default: undefined } },
  emits: ['didDismiss', 'willPresent', 'didPresent'],
  setup(props, { slots, attrs }) {
    return () => (props.isOpen ? h('div', { ...attrs, 'data-stub': 'ion-popover' }, slots.default?.()) : null);
  },
});

afterEach(() => {
  document.body.replaceChildren();
});

/** What a browser does with «tres» in a number input or 31/02 in a date one: the page reads "" and the input
 *  says it could not read it (`validity.badInput`). Returns the input, to make it readable again. */
function unreadable(id: string): HTMLInputElement {
  const host = document.querySelector(`ion-input[data-testid="customer-form-${id}"]`)!;
  const native = host.querySelector('input') ?? host.appendChild(document.createElement('input'));
  Object.defineProperty(native, 'validity', { value: { badInput: true }, configurable: true });
  return native;
}

/** The message painted under a field (none: `undefined`). */
const errorText = (id: string): string | undefined =>
  document.querySelector<HTMLElement & { errorText?: string }>(`ion-input[data-testid="customer-form-${id}"]`)!.errorText;

interface Setup {
  mode?: 'create' | 'edit';
  errors?: Record<string, string>;
  form?: Partial<CustomerFields>;
  customFields?: CustomFieldValueOut[];
  locale?: 'en' | 'es';
}

async function setup(options: Setup = {}) {
  const form = ref<CustomerFields>({ ...blankCustomer(), ...options.form });
  const values = ref<Record<string, string>>(Object.fromEntries((options.customFields ?? []).map((f) => [f.field_id, f.value])));
  const Host = defineComponent({
    setup: () => () =>
      h(CustomerForm, {
        modelValue: form.value,
        'onUpdate:modelValue': (v: CustomerFields) => (form.value = v),
        fieldValues: values.value,
        'onUpdate:fieldValues': (v: Record<string, string>) => (values.value = v),
        mode: options.mode ?? 'create',
        errors: options.errors ?? {},
        customFields: options.customFields ?? [],
      }),
  });
  const m = await mountCustomer(Host, { locale: options.locale, stubs: { IonPopover: PopoverStub }, attachTo: document.body });
  const hook = (id: string) => (c: { attributes(name: string): string | undefined }) =>
    c.attributes('data-testid') === `customer-form-${id}`;
  const input = (id: string) => m.wrapper.findAllComponents(IonInput).find(hook(id));
  const select = (id: string) => m.wrapper.findAllComponents(IonSelect).find(hook(id));
  const textarea = (id: string) => m.wrapper.findAllComponents(IonTextarea).find(hook(id));
  const checkbox = (id: string) => m.wrapper.findAllComponents(IonCheckbox).find(hook(id));
  const shownFields = () =>
    m.wrapper
      .findAll('[data-field]')
      .filter((el) => !el.element.closest('details:not([open])'))
      .map((el) => el.attributes('data-field'));
  const country = () => m.wrapper.findComponent(Combo);
  const countryField = () => m.wrapper.get('ion-input[data-testid="customer-form-country"]');
  /** The ids of the options the country's list shows. */
  const countryShown = () =>
    m.wrapper.findAll('[data-testid^="customer-form-country-option-"]').map((o) => o.attributes('data-testid')!.replace('customer-form-country-option-', ''));
  /** Types in the country field, as a person does. */
  async function typeCountry(text: string) {
    countryField().element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
    await flush();
  }
  return { ...m, form, values, input, select, textarea, checkbox, shownFields, country, countryField, countryShown, typeCountry };
}

describe('CustomerForm: «Add» (F01)', () => {
  it('shows name, phone, email, tax id and company; the rest waits behind a closed «More details»', async () => {
    const s = await setup();
    expect(s.shownFields()).toEqual(['name', 'phone', 'email', 'tax_id', 'company_name']);
    const more = s.wrapper.get('[data-testid="customer-form-more"]');
    expect(more.element.tagName).toBe('DETAILS');
    expect((more.element as HTMLDetailsElement).open).toBe(false);
    expect(more.get('summary').text()).toBe('More details');
    expect(s.input('name')!.props('label')).toBe('Name');
    expect(s.wrapper.find('[data-testid="customer-form-active"]').exists()).toBe(false);
  });

  it('«More details» opens address, city, postal code, country, photo, dates, source, stage, channel and notes', async () => {
    const s = await setup();
    const more = s.wrapper.get('[data-testid="customer-form-more"]');
    (more.element as HTMLDetailsElement).open = true;
    await more.trigger('toggle');
    expect(s.shownFields()).toEqual([
      'name',
      'phone',
      'email',
      'tax_id',
      'company_name',
      'address',
      'city',
      'postal_code',
      'country',
      'avatar',
      'birthday',
      'anniversary',
      'source',
      'lifecycle_stage',
      'preferred_channel',
      'notes',
    ]);
  });

  it('every typed value goes up as a new model; the phone is a phone field with its hint', async () => {
    const s = await setup();
    await s.input('name')!.setValue('Ana');
    await s.input('phone')!.setValue('600 111 222');
    expect(s.form.value).toMatchObject({ name: 'Ana', phone: '600 111 222' });
    const phone = s.input('phone')!;
    expect([phone.props('type'), phone.props('inputmode'), phone.props('helperText')]).toEqual([
      'tel',
      'tel',
      "With no prefix it is read as a number of this business's country; for another one, write its prefix (+44…).",
    ]);
    expect(s.input('email')!.props('type')).toBe('email');
    expect(s.input('birthday')!.props('type')).toBe('date');
  });

  it('paints a 422 under its field, and opens «More details» when the field is in there', async () => {
    const s = await setup({ errors: { phone: 'Not a valid phone', country: 'Choose a country from the list.' } });
    const phone = s.input('phone')!;
    expect(phone.props('errorText')).toBe('Not a valid phone');
    expect(phone.classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
    expect((s.wrapper.get('[data-testid="customer-form-more"]').element as HTMLDetailsElement).open).toBe(true);
    expect(s.country().props('errorText')).toBe('Choose a country from the list.');
    expect(s.countryField().classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
  });

  it('a birthday the browser cannot read behind a closed «More details» opens it, so the message is seen', async () => {
    const s = await setup({ locale: 'es' });
    const more = s.wrapper.get('[data-testid="customer-form-more"]');
    expect((more.element as HTMLDetailsElement).open).toBe(false);
    unreadable('birthday');
    expect(s.wrapper.findComponent(CustomerForm).vm.readable()).toBe(false);
    await flush();
    expect((more.element as HTMLDetailsElement).open).toBe(true);
    expect(errorText('birthday')).toBe('Introduce una fecha válida.');
  });

  it('source, stage and channel are selects with their names; a card from an import keeps «Import»', async () => {
    const s = await setup({ form: { source: 'import' } });
    const texts = (id: string) => s.select(id)!.findAll('ion-select-option').map((o) => o.text());
    expect(texts('source')).toEqual(['Walk-in', 'Phone', 'WhatsApp', 'Website', 'Social media', 'Referral', 'Other', 'Import']);
    expect(texts('lifecycle_stage')).toEqual(['Lead', 'Prospect', '1st purchase', 'Active', 'At risk', 'Dormant', 'Churned', 'VIP']);
    expect(texts('preferred_channel')).toEqual(['None', 'Email', 'SMS', 'WhatsApp', 'Phone']);
    const fresh = await setup();
    expect(fresh.select('source')!.findAll('ion-select-option')).toHaveLength(7);
  });
});

describe('CustomerForm: the country (F01, F04)', () => {
  it('is the shared Combo with every country: Spain first, the rest by name, the code as id and hint', async () => {
    const s = await setup();
    const country = s.country();
    expect([country.props('label'), country.props('testid'), country.props('modelValue')]).toEqual(['Country', 'customer-form-country', null]);
    const options = country.props('options') as ComboOption[];
    expect(options).toHaveLength(countryOptions('en').length);
    expect(options.slice(0, 3)).toEqual([
      { id: 'ES', label: 'Spain', hint: 'ES' },
      { id: 'AF', label: 'Afghanistan', hint: 'AF' },
      { id: 'AX', label: 'Åland Islands', hint: 'AX' },
    ]);
  });

  it('shows the stored country by its name in the page language', async () => {
    const s = await setup({ form: { country: 'FR' } });
    expect(s.country().props('modelValue')).toEqual({ id: 'FR', label: 'France', hint: 'FR' });
    const es = await setup({ form: { country: 'FR' }, locale: 'es' });
    expect(es.country().props('modelValue')).toEqual({ id: 'FR', label: 'Francia', hint: 'FR' });
    expect((es.country().props('options') as ComboOption[])[0]).toEqual({ id: 'ES', label: 'España', hint: 'ES' });
  });

  it('finds a country while typing its name, without accents or case, or its code', async () => {
    const s = await setup({ locale: 'es' });
    await s.typeCountry('alemania');
    expect(s.countryShown()).toEqual(['DE']);
    await s.typeCountry('peru');
    expect(s.countryShown()).toEqual(['PE']);
    await s.typeCountry('gb');
    expect(s.countryShown()).toEqual(['GB']);
    await s.typeCountry('FR');
    expect(s.countryShown()).toContain('FR');
  });

  it('a pick stores its two-letter code', async () => {
    const s = await setup({ form: { country: 'FR' } });
    await s.typeCountry('germ');
    await s.wrapper.get('[data-testid="customer-form-country-option-DE"]').trigger('click');
    await flush();
    expect(s.form.value.country).toBe('DE');
    expect(s.country().props('modelValue')).toEqual({ id: 'DE', label: 'Germany', hint: 'DE' });
  });

  it('clearing the field leaves the card without a country', async () => {
    const s = await setup({ mode: 'edit', form: { country: 'FR' } });
    await s.wrapper.get('[data-testid="customer-form-country-clear"]').trigger('click');
    await flush();
    expect(s.form.value.country).toBe('');
    expect(s.country().props('modelValue')).toBeNull();
  });

  it('a stored code it does not know is shown as stored and kept until someone changes it', async () => {
    const s = await setup({ mode: 'edit', form: { country: 'XQ' } });
    expect(s.country().props('modelValue')).toEqual({ id: 'XQ', label: 'XQ' });
    await s.typeCountry('spa');
    s.countryField().element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
    await flush();
    expect(s.form.value.country).toBe('XQ');
    expect(s.country().emitted('update:modelValue')).toBeUndefined();
  });
});

describe('CustomerForm: «Edit» (F04)', () => {
  it('shows every field at once, then the custom fields, then «Active»', async () => {
    const s = await setup({ mode: 'edit', customFields: FIELDS });
    expect(s.wrapper.find('details').exists()).toBe(false);
    expect(s.shownFields().slice(0, 16)).toEqual([
      'name',
      'phone',
      'email',
      'tax_id',
      'company_name',
      'address',
      'city',
      'postal_code',
      'country',
      'avatar',
      'birthday',
      'anniversary',
      'source',
      'lifecycle_stage',
      'preferred_channel',
      'notes',
    ]);
    expect(s.wrapper.get('[data-testid="customer-form-custom-fields"] h3').text()).toBe('Custom fields');
    expect(s.wrapper.findComponent(IonCheckbox).exists()).toBe(true);
    expect(s.wrapper.get('[data-testid="customer-form-active"]').text()).toBe('Active');
  });

  it('draws each custom field by its type; a required one is marked with *', async () => {
    const s = await setup({ mode: 'edit', customFields: FIELDS });
    const allergies = s.textarea('field-f1')!;
    expect([allergies.props('label'), allergies.props('modelValue')]).toEqual(['Allergies *', 'Nuts']);
    const dye = s.select('field-f2')!;
    expect(dye.findAll('ion-select-option').map((o) => o.text())).toEqual(['Blonde', 'Brown']);
    const newsletter = s.checkbox('field-f3')!;
    expect(newsletter.props('checked')).toBe(true);
    expect(s.input('field-f4')!.props('type')).toBe('number');
    expect(s.input('field-f5')!.props('type')).toBe('date');
    expect(s.input('field-f6')!.props('type')).toBe('text');
  });

  it('a custom field\'s change goes up in the field values; a yes/no is true or false', async () => {
    const s = await setup({ mode: 'edit', customFields: FIELDS });
    await s.input('field-f6')!.setValue('Curly');
    expect(s.values.value.f6).toBe('Curly');
    s.checkbox('field-f3')!.vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    expect(s.values.value.f3).toBe('false');
  });

  it('paints the server\'s message of a custom field under it (field_values.<id>)', async () => {
    const s = await setup({ mode: 'edit', customFields: FIELDS, errors: { 'field_values.f4': 'Enter a number.' } });
    expect(s.input('field-f4')!.props('errorText')).toBe('Enter a number.');
  });

  it('a number or a date the browser cannot read is told under its field, as the server words it, and stops the save', async () => {
    const s = await setup({ mode: 'edit', customFields: FIELDS, locale: 'es', errors: { phone: 'No es un teléfono válido.' } });
    for (const id of ['field-f4', 'field-f5', 'birthday']) unreadable(id);
    expect(s.wrapper.findComponent(CustomerForm).vm.readable()).toBe(false);
    await flush();
    expect(['field-f4', 'field-f5', 'birthday', 'phone'].map((id) => s.input(id)!.props('errorText'))).toEqual([
      'Introduce un número.',
      'Introduce una fecha válida.',
      'Introduce una fecha válida.',
      'No es un teléfono válido.',
    ]);
    expect(s.input('field-f4')!.classes()).toContain('ion-invalid');
    expect(errorText('anniversary')).toBeUndefined();
  });

  it('with every number and date readable it lets the save go, and a previous «cannot read» is gone', async () => {
    const s = await setup({ mode: 'edit', customFields: FIELDS });
    const native = unreadable('field-f4');
    expect(s.wrapper.findComponent(CustomerForm).vm.readable()).toBe(false);
    Object.defineProperty(native, 'validity', { value: { badInput: false } });
    expect(s.wrapper.findComponent(CustomerForm).vm.readable()).toBe(true);
    await flush();
    expect(errorText('field-f4')).toBeUndefined();
  });

  it('«Active» unticked goes up as false', async () => {
    const s = await setup({ mode: 'edit' });
    s.wrapper.findComponent(IonCheckbox).vm.$emit('ionChange', { detail: { checked: false } });
    await flush();
    expect(s.form.value.is_active).toBe(false);
  });
});

describe('CustomerForm: language and markup', () => {
  it('speaks Spanish', async () => {
    const s = await setup({ locale: 'es' });
    expect(['name', 'phone', 'email', 'tax_id', 'company_name'].map((id) => s.input(id)!.props('label'))).toEqual([
      'Nombre',
      'Teléfono',
      'Email',
      'NIF/CIF',
      'Empresa',
    ]);
    expect(s.wrapper.get('summary').text()).toBe('Más datos');
    expect(s.country().props('label')).toBe('País');
  });

  it('has no OutfitKit tag, and every control with a fill declares mode="md"', () => {
    expect(source).not.toMatch(/<ok[-]/);
    for (const tag of source.match(/<ion-(input|select|textarea)\b[^>]*>/gs) ?? []) {
      if (/fill=/.test(tag)) expect(tag, tag).toMatch(/mode="md"/);
    }
  });
});
