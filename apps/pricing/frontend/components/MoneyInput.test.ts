// A money field of the pricing forms (a price of a list, a rule's amount per unit; PRICING-F07, F10):
// an outlined md text field with the decimal keyboard. It accepts «2,20», «1.234,56» or what is pasted
// from the screen and, on leaving it, rewrites a readable amount in the page format. What is not an
// amount says so under the field («This is not an amount…», or both readings of «1.250»), after the
// person leaves it or tries to save; the server's message for the field wins.
import { IonInput } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { flush, mountPricing } from '../__tests__/mount-pricing';
import { formatMoney } from '../lib/format';
import MoneyInput from './MoneyInput.vue';

type Control = HTMLElement & { errorText?: string };

const PLN = { currency: 'PLN', decimals: 2 };
const EUR = { currency: 'EUR', decimals: 2 };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const model = { value: (props.modelValue as string) ?? '' };
  const m = await mountPricing(MoneyInput, {
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
  });
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

  it('what is not an amount says so after leaving the field', async () => {
    const s = await setup();
    await s.input().setValue('abc');
    expect(s.errorText()).toBeUndefined();
    await s.blur();
    expect(s.errorText()).toBe('This is not an amount. Type a figure, for example 12.50.');
    expect(s.input().classes()).toEqual(expect.arrayContaining(['ion-invalid', 'ion-touched']));
  });

  it('«1.250» gives both readings', async () => {
    const s = await setup({ modelValue: '1.250', showError: true });
    expect(s.errorText()).toBe(
      `This amount can be read in two ways: «1.250» could be ${formatMoney(125000, 'en')} or ${formatMoney(125, 'en')}. Write the decimals so there is no doubt.`,
    );
  });

  it("the server's message for the field wins", async () => {
    const s = await setup({ modelValue: '12', errorText: 'Ensure this value is less than or equal to 9999999999999' });
    expect(s.errorText()).toBe('Ensure this value is less than or equal to 9999999999999');
  });

  it('in the field’s currency: «12,5 zł» is read in zlotys, and a euro amount is not one (pricing-business-currency)', async () => {
    const s = await setup({ money: PLN }, 'es');
    await s.input().setValue('12,5 zł');
    await s.blur();
    expect([s.model.value, s.errorText()]).toEqual(['12,50', undefined]);
    await s.input().setValue('12,50 €');
    await s.blur();
    expect(s.errorText()).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12,50.');
  });

  it('«1.250» gives both readings in the field’s currency', async () => {
    const s = await setup({ modelValue: '1.250', showError: true, money: PLN });
    expect(s.errorText()).toBe(
      `This amount can be read in two ways: «1.250» could be ${formatMoney(125000, 'en', PLN)} or ${formatMoney(125, 'en', PLN)}. Write the decimals so there is no doubt.`,
    );
    expect(s.errorText()).toContain('zł');
  });

  it('a negative amount says it cannot be negative', async () => {
    const s = await setup({ modelValue: '-5', showError: true });
    expect(s.errorText()).toBe('This amount cannot be negative.');
  });

  it('speaks Spanish', async () => {
    const s = await setup({ modelValue: 'x', showError: true }, 'es');
    expect(s.errorText()).toBe('Esto no es un importe. Escribe una cifra, por ejemplo 12,50.');
  });
});

// hub#921: a rule's amount is in the business's money, whose decimals are unknown until it answers: leaving the field
// before that keeps what was typed, so a «150» left before the yen arrives is still 150 (never «150.00», which the yen
// cannot read).
describe('MoneyInput: the business’s money', () => {
  it('until the money is known, leaving keeps what was typed: no decimals invented', async () => {
    const s = await setup();
    await s.input().setValue('150');
    await s.blur();
    expect([s.model.value, s.errorText()]).toEqual(['150', undefined]);
    await s.wrapper.setProps({ money: { currency: 'JPY', decimals: 0 } });
    await s.blur();
    expect([s.model.value, s.errorText()]).toEqual(['150', undefined]);
  });

  it('once the money is known, hands the parent what is typed and rewrites it in the page format on leaving', async () => {
    const s = await setup({ money: EUR }, 'es');
    await s.input().setValue('2.2');
    expect(s.model.value).toBe('2.2');
    await s.blur();
    expect([s.model.value, s.errorText()]).toEqual(['2,20', undefined]);
  });
});
