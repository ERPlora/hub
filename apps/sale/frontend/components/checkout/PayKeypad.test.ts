// The keypad of the charge sheet (SALE-F01, F03): three columns, 1…9, the decimal separator, 0 and C,
// as the old one (no quick amounts: removed on purpose). Each key says which it is; the separator is the
// page language's (a comma in Spanish), and the key it sends is always '.'.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import PayKeypad from './PayKeypad.vue';

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountSale(PayKeypad, { locale });
  const keys = () => m.wrapper.findAll('button');
  const sent = () => (m.wrapper.emitted('key') ?? []).map(([k]) => k);
  return { ...m, keys, sent };
}

describe('PayKeypad', () => {
  it('lays out 1…9, the separator, 0 and C, named for the tests and for a screen reader', async () => {
    const s = await setup();
    expect(s.keys().map((k) => k.text())).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', 'C']);
    expect(s.keys().map((k) => k.attributes('data-testid'))).toEqual([
      ...['1', '2', '3', '4', '5', '6', '7', '8', '9'].map((d) => `sale-checkout-keypad-${d}`),
      'sale-checkout-keypad-dot',
      'sale-checkout-keypad-0',
      'sale-checkout-keypad-clear',
    ]);
    expect(s.find('sale-checkout-keypad').attributes()).toMatchObject({ role: 'group', 'aria-label': 'Keypad' });
    expect(s.find('sale-checkout-keypad-clear').attributes('aria-label')).toBe('Clear');
    expect(s.keys().every((k) => k.attributes('type') === 'button')).toBe(true);
  });

  it('sends the key pressed; the separator always as «.»', async () => {
    const s = await setup('es');
    await click(s.find('sale-checkout-keypad-1').element);
    await click(s.find('sale-checkout-keypad-dot').element);
    await click(s.find('sale-checkout-keypad-5').element);
    await click(s.find('sale-checkout-keypad-clear').element);
    expect(s.sent()).toEqual(['1', '.', '5', 'C']);
  });

  it('speaks Spanish, with the comma as separator', async () => {
    const s = await setup('es');
    expect(s.find('sale-checkout-keypad-dot').text()).toBe(',');
    expect(s.find('sale-checkout-keypad').attributes('aria-label')).toBe('Teclado');
    expect(s.find('sale-checkout-keypad-clear').attributes('aria-label')).toBe('Borrar');
  });
});
