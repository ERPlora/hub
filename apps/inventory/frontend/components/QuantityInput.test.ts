// A quantity field of the inventory (initial stock, threshold, received, counted, written off;
// WORKBOOK INVENTORY-F26): an outlined md text field with the decimal keyboard that says the unit and
// its step («In kg, in steps of 0.001»). It accepts «2,5» or «0.532»; what is not a quantity says so
// under the field after the person leaves it or tries to save. Whether it fits the unit's step is the
// server's to say (409 with its field), and the server's message wins.
import { IonInput } from '@ionic/vue';
import { describe, expect, it } from 'vitest';

import { flush, mountInventory } from '../__tests__/mount-inventory';
import QuantityInput from './QuantityInput.vue';

type Control = HTMLElement & { errorText?: string; helperText?: string };

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountInventory(QuantityInput, {
    props: { modelValue: '', label: 'Quantity received', testid: 'qty', unit: 'kg', step: '0.001', ...props },
    locale,
  });
  const input = () => m.wrapper.findComponent(IonInput);
  return { ...m, input, errorText: () => (input().element as Control).errorText };
}

describe('QuantityInput', () => {
  it('is an outlined md decimal field that says the unit and its step', async () => {
    const s = await setup();
    const input = s.input();
    expect([input.props('label'), input.props('fill'), input.attributes('mode'), input.props('inputmode')]).toEqual([
      'Quantity received',
      'outline',
      'md',
      'decimal',
    ]);
    expect(input.props('helperText')).toBe('In kg, in steps of 0.001');
  });

  it('paints the step in the page language and says nothing without a unit', async () => {
    expect((await setup({}, 'es')).input().props('helperText')).toBe('En kg, de 0,001 en 0,001');
    // Ionic Vue marks a prop left out with a symbol: the element is what says there is no helper.
    expect(((await setup({ unit: undefined, step: undefined })).input().element as Control).helperText).toBeUndefined();
  });

  it('hands the parent what is typed', async () => {
    const s = await setup();
    await s.input().setValue('2,5');
    expect(s.wrapper.emitted('update:modelValue')).toEqual([['2,5']]);
  });

  it('what is not a quantity says so after leaving the field or a save attempt', async () => {
    const s = await setup({ modelValue: '-1' });
    expect(s.errorText()).toBeUndefined();
    s.input().element.dispatchEvent(new CustomEvent('ionBlur'));
    await flush();
    expect(s.errorText()).toBe('This is not a quantity. Type a figure with up to three decimals, for example 2.5.');
    const t = await setup({ modelValue: 'x', showError: true }, 'es');
    expect(t.errorText()).toBe('Esto no es una cantidad. Escribe una cifra con hasta tres decimales, por ejemplo 2,5.');
  });

  it("the server's message wins (a quantity off the unit's step)", async () => {
    const s = await setup({ modelValue: '0.0005', errorText: 'The quantity does not respect the step allowed for this unit: use multiples of 0,001 kg.' });
    expect(s.errorText()).toBe('The quantity does not respect the step allowed for this unit: use multiples of 0,001 kg.');
  });
});
