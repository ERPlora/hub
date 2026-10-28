// A money field of the combo forms (a menu's closed price, a choice's supplement; COMBO-F02, F06):
// an outlined md text field with the decimal keyboard. It accepts «2,20», «1.234,56» or what is pasted
// from the screen and, on leaving it, rewrites a readable amount in the page format. What is not an
// amount says so under the field («This is not an amount…», or both readings of «1.250»), after the
// person leaves it or tries to save; the server's message for the field wins. The amount is the business's currency
// (its code or sign is noise, another currency's is not; at most its decimals); until the business answers, leaving
// the field keeps what was typed (it does not invent the decimals).
import { IonInput } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import type { Business } from '../../../../base/frontend/operations';
import { business, flush, JAPANESE, mountCombo, POLISH } from '../__tests__/mount-combo';
import { formatMoney } from '../lib/format';
import MoneyInput from './MoneyInput.vue';

type Control = HTMLElement & { errorText?: string };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en', answer?: Business | null) {
  const model = { value: (props.modelValue as string) ?? '' };
  const m = await mountCombo(MoneyInput, {
    props: {
      modelValue: model.value,
      label: 'Price',
      testid: 'price',
      'onUpdate:modelValue': (value: string) => {
        model.value = value;
        void m.wrapper.setProps({ modelValue: value });
      },
      ...props,
    },
    locale,
    business: answer,
  });
  await m.live();
  const input = () => m.wrapper.findComponent(IonInput);
  async function blur() {
    input().element.dispatchEvent(new CustomEvent('ionBlur'));
    await flush();
  }
  const errorText = () => (input().element as Control).errorText;
  return { ...m, model, input, blur, errorText };
}

describe('MoneyInput', () => {
  it('is an outlined md text field with its label and the decimal keyboard', async () => {
    const s = await setup();
    const input = s.input();
    expect([input.props('label'), input.props('fill'), input.attributes('mode'), input.props('inputmode'), input.props('type')]).toEqual([
      'Price',
      'outline',
      'md',
      'decimal',
      'text',
    ]);
    expect(input.attributes('data-testid')).toBe('price');
  });

  it('hands the parent what is typed, and rewrites it in the page format on leaving', async () => {
    const s = await setup({}, 'es');
    await s.input().setValue('2.2');
    expect(s.model.value).toBe('2.2');
    await s.blur();
    expect(s.model.value).toBe('2,20');
    expect(s.errorText()).toBeUndefined();
  });

  it('in a business in Poland, reads złoty and rewrites them in the page format; a euro is not an amount', async () => {
    const s = await setup({}, 'es', business(POLISH));
    await s.input().setValue('13.5 zł');
    await s.blur();
    expect(s.model.value).toBe('13,50');
    expect(s.errorText()).toBeUndefined();
    await s.input().setValue('13,50 €');
    await s.blur();
    expect(s.model.value).toBe('13,50 €');
    expect(s.errorText()).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12,50.');
  });

  it('in yen, an amount has no decimals: «150» stays «150» and «1,5» is not an amount', async () => {
    const s = await setup({}, 'en', business(JAPANESE));
    await s.input().setValue('150');
    await s.blur();
    expect(s.model.value).toBe('150');
    expect(s.errorText()).toBeUndefined();
    await s.input().setValue('1,5');
    await s.blur();
    expect(s.errorText()).toBe('This is not an amount. Type a figure, for example 12.50.');
  });

  it('before the business answers, leaving the field keeps what was typed: no decimals the currency may not have', async () => {
    const s = await setup({}, 'en', null);
    await s.input().setValue('150');
    await s.blur();
    expect(s.model.value).toBe('150');
    await s.result('base.business.get', business(JAPANESE));
    expect(s.errorText()).toBeUndefined();
    await s.blur();
    expect(s.model.value).toBe('150');
    await s.input().setValue('2.2');
    await s.result('base.business.get', business(POLISH), {}, 2);
    await s.blur();
    expect(s.model.value).toBe('2.20');
  });

  it('what is not an amount says so after leaving the field', async () => {
    const s = await setup();
    await s.input().setValue('abc');
    expect(s.errorText()).toBeUndefined();
    await s.blur();
    expect(s.errorText()).toBe('This is not an amount. Type a figure, for example 12.50.');
    expect(s.input().classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
  });

  it('«1.250» gives both readings, in the business currency', async () => {
    const s = await setup({ modelValue: '1.250', showError: true }, 'en', business(POLISH));
    const pln = { currency: 'PLN', decimals: 2 };
    expect(s.errorText()).toBe(
      `This amount can be read in two ways: «1.250» could be ${formatMoney(125000, 'en', pln)} or ${formatMoney(125, 'en', pln)}. Write the decimals so there is no doubt.`,
    );
    expect(s.errorText()).toContain('zł');
  });

  it("the server's message for the field wins", async () => {
    const s = await setup({ modelValue: '12', errorText: 'Ensure this value is less than or equal to 9999999999999' });
    expect(s.errorText()).toBe('Ensure this value is less than or equal to 9999999999999');
  });

  it('a negative price says it cannot be negative and how to make a choice cheaper', async () => {
    const s = await setup({ modelValue: '-5', showError: true });
    expect(s.errorText()).toBe('A menu price cannot be below zero. To make a choice cheaper, give it a negative supplement instead.');
  });

  it('a supplement may be negative', async () => {
    const s = await setup({ modelValue: '-0.5', showError: true, signed: true }, 'es');
    expect(s.errorText()).toBeUndefined();
    await s.blur();
    expect(s.model.value).toBe('-0,50');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ modelValue: 'x', showError: true }, 'es');
    expect(s.errorText()).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12,50.');
  });
});
