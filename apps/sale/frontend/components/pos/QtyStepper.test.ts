// The quantity selector of a cart line (SALE-F01 step 2, F10): minus, the field, plus. It only says
// what was asked; the line shows what the server keeps (a refused quantity puts the field back).
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import QtyStepper from './QtyStepper.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(QtyStepper, { props: { quantity: '2.000', unit: 'ud', ...props }, locale });
  const field = () => m.wrapper.find('input').element as HTMLInputElement;
  return { ...m, field };
}

async function type(el: HTMLInputElement, value: string, key = 'Enter') {
  el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('QtyStepper', () => {
  it('shows the quantity in the reader’s language, with its unit when it is not «ud»', async () => {
    const units = await setup();
    expect(units.field().value).toBe('2');
    expect(units.find('pos-qty-unit').exists()).toBe(false);
    const weight = await setup({ quantity: '0.532', unit: 'kg' }, 'es');
    expect(weight.field().value).toBe('0,532');
    expect(weight.find('pos-qty-unit').text()).toBe('kg');
  });

  it('plus and minus ask one unit more or less; minus from one asks zero (the line goes)', async () => {
    const m = await setup({ quantity: '1.000' });
    await click(m.find('pos-qty-plus').element);
    await click(m.find('pos-qty-minus').element);
    expect(m.wrapper.emitted('change')).toEqual([['2'], ['0']]);
    expect(m.find('pos-qty-plus').attributes('aria-label')).toBe('One more');
    expect(m.find('pos-qty-minus').attributes('aria-label')).toBe('One less');
    expect(m.wrapper.find('input').attributes('aria-label')).toBe('Quantity');
  });

  it('a typed quantity is sent as the server reads it (dot decimals), only when it changed', async () => {
    const m = await setup({ quantity: '0.500', unit: 'kg' }, 'es');
    await type(m.field(), '0,532');
    expect(m.wrapper.emitted('change')).toEqual([['0.532']]);
    await type(m.field(), '0,5');
    expect(m.wrapper.emitted('change')).toEqual([['0.532']]);
  });

  it('something that is not a quantity puts the field back and asks nothing', async () => {
    const m = await setup();
    await type(m.field(), 'abc');
    expect(m.wrapper.emitted('change')).toBeUndefined();
    expect(m.field().value).toBe('2');
  });

  it('follows the quantity the server keeps', async () => {
    const m = await setup();
    await m.wrapper.setProps({ quantity: '5.000' });
    expect(m.field().value).toBe('5');
  });

  it('can be locked while a write is in flight', async () => {
    const m = await setup({ disabled: true });
    expect(m.find('pos-qty-plus').attributes('disabled')).toBeDefined();
    expect(m.find('pos-qty-minus').attributes('disabled')).toBeDefined();
  });
});
