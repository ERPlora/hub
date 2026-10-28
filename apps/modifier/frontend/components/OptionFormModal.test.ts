// MODIFIER-F04: «Add option» asks for Name, «Kitchen ticket name», «Supplement (PLN)» (in the business's
// currency, its country's: the code says which; negative is a discount; empty or 0, free), «Own tax category» (searched in Taxes; empty = the dish's), «Chosen by
// default» and Order, with «Create»; Edit opens «Editing option — {name}» with «Save», which sends only
// what changed (an emptied tax category gives the dish's back). A supplement that is not an amount is
// never sent; the server's refusals go under their field.
import { Combo } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import type { Business } from '../../../../base/frontend/operations';
import type { GroupOut, OptionOut } from '../operations';
import { business, click, ionChecked, ionValue, JAPANESE, KUWAITI, mountModifier, POLISH, settle } from '../__tests__/mount-modifier';
import OptionFormModal from './OptionFormModal.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

type Control = HTMLElement & { label?: string; value?: unknown; checked?: boolean; errorText?: string; helperText?: string; disabled?: boolean };

const DRINKS = { id: 'g1', name: 'Drinks' } as GroupOut;
const SODA: OptionOut = {
  id: 'o1',
  group_id: 'g1',
  group_name: 'Drinks',
  name: 'Soda',
  kitchen_name: 'SODA',
  price_delta: 250,
  tax_category_key: 'product.generic',
  tax_category_name: 'Product — generic',
  is_default: false,
  sort_order: 1,
  created_at: '2026-10-15T10:00:00Z',
  updated_at: '2026-10-15T10:00:00Z',
};

/** The form, opened; with `owner`, once the business (`base.business.get`) has answered. */
async function setup(option: OptionOut | null = null, locale: 'en' | 'es' = 'en', owner?: Business) {
  const m = await mountModifier(OptionFormModal, { props: { open: false, group: DRINKS, option }, locale });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  if (owner) {
    await m.live();
    await m.result('base.business.get', owner);
  }
  await m.wrapper.setProps({ open: true });
  await settle();
  const field = (name: string) => m.inDoc(`modifier-option-form-${name}`) as Control;
  const save = () => m.inDoc('modifier-option-form-submit') as Control;
  const tax = () => m.wrapper.findComponent(Combo);
  return { ...m, field, save, tax };
}

describe('OptionFormModal: New option', () => {
  it('asks for name, kitchen name, supplement, own tax category, default and order', async () => {
    const s = await setup();
    expect(s.inDoc('modifier-option-form')?.getAttribute('aria-label')).toBe('New option');
    expect(['name', 'kitchen_name', 'price_delta', 'sort_order'].map((name) => s.field(name).label)).toEqual([
      'Name',
      'Kitchen ticket name',
      'Supplement',
      'Order',
    ]);
    expect(s.field('price_delta').helperText).toBe('Negative is a discount; empty or 0, free.');
    expect([s.tax().props('label'), s.tax().props('placeholder'), s.tax().props('helperText')]).toEqual([
      'Own tax category',
      "The dish's",
      "Only if it taxes differently from the dish; empty = the dish's.",
    ]);
    expect(s.field('is_default').textContent).toContain('Chosen by default');
    expect(s.save().disabled).toBe(true);
  });

  it('sends modifier.option.create in its group, the supplement in signed cents, and closes', async () => {
    const s = await setup();
    s.answer(201, SODA);
    await ionValue(s.field('name'), 'No bread', 'ionInput');
    await ionValue(s.field('price_delta'), '-0,50', 'ionInput');
    await ionChecked(s.field('is_default'), true);
    await click(s.save());
    expect(s.sent()).toEqual([
      {
        method: 'POST',
        path: '/api/modifier/options',
        query: {},
        body: { group_id: 'g1', name: 'No bread', kitchen_name: '', price_delta: -50, tax_category_key: '', is_default: true, sort_order: 0 },
      },
    ]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });

  it('its own tax category is the key picked in Taxes; an empty supplement is free', async () => {
    const s = await setup();
    s.answer(201, SODA);
    await ionValue(s.field('name'), 'Soda', 'ionInput');
    s.tax().vm.$emit('update:modelValue', { id: 'product.generic', label: 'Product — generic · 21%' });
    await settle();
    await click(s.save());
    expect((s.sent()[0].body as Record<string, unknown>).tax_category_key).toBe('product.generic');
    expect((s.sent()[0].body as Record<string, unknown>).price_delta).toBe(0);
  });

  it('a supplement that is not an amount says so and is never sent', async () => {
    const s = await setup();
    await ionValue(s.field('name'), 'Soda', 'ionInput');
    await ionValue(s.field('price_delta'), 'abc', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price_delta').errorText).toBe('This is not an amount. Type a figure, for example 1.50, or -0.50 for a discount.');
  });

  it('the server’s refusal goes under its field', async () => {
    const s = await setup();
    const message = 'An option with its own tax category is billed on a line of its own: its supplement must be more than zero.';
    s.answer(422, { error: { code: 'invalid_field', message, fields: { price_delta: message } } });
    await ionValue(s.field('name'), 'Soda', 'ionInput');
    s.tax().vm.$emit('update:modelValue', { id: 'product.generic', label: 'Product — generic' });
    await settle();
    await click(s.save());
    expect(s.field('price_delta').errorText).toBe(message);
  });
  it('more defaults than the group’s maximum is said under «Chosen by default»', async () => {
    const s = await setup();
    const message = 'This group has more options chosen by default than its maximum.';
    s.answer(409, { error: { code: 'modifier.too_many_defaults', message, fields: { is_default: message } } });
    await ionValue(s.field('name'), 'Mustard', 'ionInput');
    await ionChecked(s.field('is_default'), true);
    await click(s.save());
    expect(s.inDoc('modifier-option-form-is_default-error')?.textContent).toContain(message);
  });
});

describe('OptionFormModal: in the business’s currency', () => {
  it('in Poland the supplement is in złoty: the field says PLN, «2,50 zł» is 250 grosze and a euro amount is never sent', async () => {
    const s = await setup(null, 'en', business(POLISH));
    expect(s.field('price_delta').label).toBe('Supplement (PLN)');
    s.answer(201, SODA);
    await ionValue(s.field('name'), 'Cheese', 'ionInput');
    await ionValue(s.field('price_delta'), '2,50 €', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price_delta').errorText).toBe('This is not an amount. Type a figure, for example 1.50, or -0.50 for a discount.');
    await ionValue(s.field('price_delta'), '+2,50 zł', 'ionInput');
    // Leaving the field rewrites it in the page format: the field reads złoty too, not only the save.
    s.field('price_delta').dispatchEvent(new CustomEvent('ionBlur'));
    await settle();
    expect(s.field('price_delta').value).toBe('2.50');
    await click(s.save());
    expect((s.sent()[0].body as Record<string, unknown>).price_delta).toBe(250);
  });

  it('in Spain the field says EUR', async () => {
    const s = await setup(null, 'es', business());
    expect(s.field('price_delta').label).toBe('Suplemento (EUR)');
  });

  it('in yen, without minor units: 150 yen reads «150» and «200» sends 200', async () => {
    const s = await setup({ ...SODA, price_delta: 150 }, 'es', business(JAPANESE));
    expect(s.field('price_delta').value).toBe('150');
    s.answer(200, { ...SODA, price_delta: 200 });
    await ionValue(s.field('price_delta'), '200', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/options/update', query: {}, body: { id: 'o1', price_delta: 200 } }]);
  });
});

describe('OptionFormModal: the business answers after the form opened', () => {
  const NOT_AMOUNT = 'This is not an amount. Type a figure, for example 1.50, or -0.50 for a discount.';

  it('an untouched supplement is rewritten from the option with the yen’s decimals, and «Save» keeps its scale', async () => {
    const s = await setup({ ...SODA, price_delta: 150 });
    expect(s.field('price_delta').value).toBe('1.50');
    await s.live();
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('price_delta').value).toBe('150');
    expect(s.field('price_delta').label).toBe('Supplement (JPY)');
    s.answer(200, { ...SODA, name: 'Cola', price_delta: 150 });
    await ionValue(s.field('name'), 'Cola', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/options/update', query: {}, body: { id: 'o1', name: 'Cola' } }]);
  });

  it('with three decimals an untouched supplement is rewritten in that scale, never saved ten times bigger', async () => {
    const s = await setup({ ...SODA, price_delta: 1500 });
    expect(s.field('price_delta').value).toBe('15.00');
    await s.live();
    await s.result('base.business.get', business(KUWAITI));
    expect(s.field('price_delta').value).toBe('1.500');
    s.answer(200, { ...SODA, name: 'Cola', price_delta: 1500 });
    await ionValue(s.field('name'), 'Cola', 'ionInput');
    await click(s.save());
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/modifier/options/update', query: {}, body: { id: 'o1', name: 'Cola' } }]);
  });

  it('what the person already typed stays and is read in the business’s currency: «2,50» in Poland is 250 grosze', async () => {
    const s = await setup();
    s.answer(201, SODA);
    await ionValue(s.field('name'), 'Bacon', 'ionInput');
    await ionValue(s.field('price_delta'), '2,50', 'ionInput');
    await s.live();
    await s.result('base.business.get', business(POLISH));
    expect(s.field('price_delta').value).toBe('2,50');
    await click(s.save());
    expect((s.sent()[0].body as Record<string, unknown>).price_delta).toBe(250);
  });

  it('what the person typed that the yen cannot read stays as typed: the field says so and nothing is sent', async () => {
    const s = await setup({ ...SODA, price_delta: 150 });
    await ionValue(s.field('price_delta'), '1,75', 'ionInput');
    await s.live();
    await s.result('base.business.get', business(JAPANESE));
    expect(s.field('price_delta').value).toBe('1,75');
    await click(s.save());
    expect(s.sent()).toEqual([]);
    expect(s.field('price_delta').errorText).toBe(NOT_AMOUNT);
  });
});

describe('OptionFormModal: Editing option — {name}', () => {
  it('is loaded and sends only what changed; an emptied tax category gives the dish’s back', async () => {
    const s = await setup(SODA);
    expect(s.inDoc('modifier-option-form')?.getAttribute('aria-label')).toBe('Editing option — Soda');
    expect([s.field('name').value, s.field('kitchen_name').value, s.field('price_delta').value]).toEqual(['Soda', 'SODA', '2.50']);
    expect(s.tax().props('modelValue')).toEqual({ id: 'product.generic', label: 'Product — generic' });
    s.answer(200, { ...SODA, tax_category_key: null, price_delta: 0 });
    await ionValue(s.field('price_delta'), '0', 'ionInput');
    s.tax().vm.$emit('update:modelValue', null);
    await settle();
    await click(s.save());
    expect(s.sent()).toEqual([
      { method: 'POST', path: '/api/modifier/options/update', query: {}, body: { id: 'o1', price_delta: 0, tax_category_key: '' } },
    ]);
  });

  it('speaks Spanish', async () => {
    const s = await setup(SODA, 'es');
    expect(s.inDoc('modifier-option-form')?.getAttribute('aria-label')).toBe('Editando opción — Soda');
    expect(s.field('price_delta').value).toBe('2,50');
    expect(s.field('is_default').textContent).toContain('Elegida por defecto');
  });
});
