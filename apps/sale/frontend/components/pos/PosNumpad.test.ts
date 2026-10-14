// The till's keypad (spec «Sheets»: 3 columns, 1…9, the decimal key, 0 and clear): it types an amount
// in major units («12.5»), never more decimals than allowed, nor two separators, nor leading zeros.
import { describe, expect, it } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale } from '../../__tests__/mount-sale';
import PosNumpad from './PosNumpad.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const value = ref('');
  const m = await mountSale(
    { setup: () => () => h(PosNumpad, { modelValue: value.value, 'onUpdate:modelValue': (v: string) => (value.value = v), ...props }) },
    { locale },
  );
  const press = async (...keys: string[]) => {
    for (const key of keys) await click(m.find(`pos-key-${key}`).element);
  };
  return { ...m, value, press };
}

describe('PosNumpad', () => {
  it('has the keys 1…9, the decimal key in the reader’s language, 0 and clear', async () => {
    const m = await setup({}, 'es');
    const keys = m.wrapper.findAll('button').map((b) => b.text());
    expect(keys).toEqual(['1', '2', '3', '4', '5', '6', '7', '8', '9', ',', '0', 'C']);
    expect(m.find('pos-key-clear').attributes('aria-label')).toBe('Borrar');
  });

  it('types an amount with the dot, at most two decimals and one separator', async () => {
    const m = await setup();
    await m.press('1', '2', 'dot', '5', 'dot', '0', '9');
    expect(m.value.value).toBe('12.50');
  });

  it('no leading zeros; a separator first is «0.»', async () => {
    const m = await setup();
    await m.press('0', '0', '7');
    expect(m.value.value).toBe('7');
    await m.press('clear', 'dot', '5');
    expect(m.value.value).toBe('0.5');
  });

  it('clear empties it; without decimals the separator does nothing', async () => {
    const m = await setup({ decimals: 0 });
    await m.press('4', 'dot', '2');
    expect(m.value.value).toBe('42');
    expect((m.find('pos-key-dot').element as HTMLButtonElement).disabled).toBe(true);
    await m.press('clear');
    expect(m.value.value).toBe('');
  });

  it('stops at the longest amount it takes', async () => {
    const m = await setup({ maxLength: 3 });
    await m.press('1', '2', '3', '4');
    expect(m.value.value).toBe('123');
  });
});
