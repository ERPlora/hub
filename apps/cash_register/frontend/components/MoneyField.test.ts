// The one money field of the drawer (the float, an amount, the counted cash, a typed count total): an
// outlined md `ion-input` that types like a number pad («inputmode decimal») and says under itself why
// what was typed is not an amount — the parent reads it with `readMoney` and passes the reason.
import { describe, expect, it } from 'vitest';

import { ionValue, mountCash } from '../__tests__/mount-cash-register';
import MoneyField from './MoneyField.vue';

const prop = (el: Element | null, name: string): unknown => (el as unknown as Record<string, unknown>)[name];

describe('MoneyField', () => {
  it('is an outlined md text field with the decimal pad, its label and its value', async () => {
    const m = await mountCash(MoneyField, { props: { modelValue: '150,50', label: 'Opening float', testid: 'float' } });
    const input = m.inDoc('float');
    expect([prop(input, 'label'), prop(input, 'value'), prop(input, 'inputmode'), prop(input, 'fill'), input?.getAttribute('mode') ?? prop(input, 'mode')]).toEqual([
      'Opening float',
      '150,50',
      'decimal',
      'outline',
      'md',
    ]);
  });

  it('tells what is typed and shows the reason it is not an amount', async () => {
    const m = await mountCash(MoneyField, { props: { modelValue: '', label: 'Amount', testid: 'amount', error: 'Not an amount' } });
    await ionValue(m.inDoc('amount'), '12,5', 'ionInput');
    expect(m.wrapper.emitted('update:modelValue')).toEqual([['12,5']]);
    expect(prop(m.inDoc('amount'), 'errorText')).toBe('Not an amount');
    expect(m.inDoc('amount')?.classList.contains('ion-invalid')).toBe(true);
  });
});
