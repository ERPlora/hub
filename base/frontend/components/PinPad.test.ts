// The PIN pad (BASE-G54, G55, G60, G126): as many circles as the business's PIN has digits, the keypad, and the
// entry at the last digit, without a button (Clover's, hub#974). Digits from a keyboard too; Backspace erases.
import { afterEach, describe, expect, it } from 'vitest';

import { mountBase } from '../__tests__/mount-base';
import PinPad from './PinPad.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

async function pad(props: Record<string, unknown> = {}) {
  const { wrapper } = await mountBase(PinPad, { props: { length: 4, label: 'Enter your PIN', ...props } });
  const press = async (digits: string) => {
    for (const digit of digits) await wrapper.get(`[data-testid="pinpad-key-${digit}"]`).trigger('click');
  };
  const filled = () => wrapper.findAll('[data-testid="pinpad-dot"].is-filled').length;
  return { wrapper, press, filled };
}

describe('PinPad', () => {
  it('paints one circle per digit of the business’s PIN', async () => {
    const { wrapper } = await pad({ length: 6 });
    expect(wrapper.findAll('[data-testid="pinpad-dot"]')).toHaveLength(6);
    expect(wrapper.get('[data-testid="pinpad"]').attributes('aria-label')).toBe('Enter your PIN');
  });

  it('enters at the last digit, once, and empties the circles', async () => {
    const { wrapper, press, filled } = await pad();
    await press('482');
    expect(filled()).toBe(3);
    expect(wrapper.emitted('complete')).toBeUndefined();
    await press('6');
    expect(wrapper.emitted('complete')).toEqual([['4826']]);
    expect(filled()).toBe(0);
  });

  it('erases the last digit', async () => {
    const { wrapper, press, filled } = await pad();
    await press('48');
    await wrapper.get('[data-testid="pinpad-erase"]').trigger('click');
    expect(filled()).toBe(1);
  });

  it('takes the digits and Backspace of a keyboard', async () => {
    const { wrapper, filled } = await pad();
    for (const key of ['4', '8', 'Backspace', '8', '2', '6']) {
      document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    }
    await wrapper.vm.$nextTick();
    expect(wrapper.emitted('complete')).toEqual([['4826']]);
    expect(filled()).toBe(0);
  });

  it('busy, it takes nothing', async () => {
    const { wrapper, press, filled } = await pad({ disabled: true });
    await press('4826');
    expect(filled()).toBe(0);
    expect(wrapper.emitted('complete')).toBeUndefined();
  });

  it('says what went wrong under the circles, for a screen reader too', async () => {
    const { wrapper } = await pad({ error: 'Wrong PIN.' });
    const error = wrapper.get('[data-testid="pinpad-error"]');
    expect(error.text()).toBe('Wrong PIN.');
    expect(error.attributes('role')).toBe('alert');
  });

  it('the arrow left of the 0 goes back only where the screen offers it', async () => {
    const without = await pad();
    expect(without.wrapper.find('[data-testid="pinpad-back"]').exists()).toBe(false);
    document.body.innerHTML = '';
    const { wrapper } = await pad({ backLabel: 'Change user' });
    const back = wrapper.get('[data-testid="pinpad-back"]');
    expect(back.attributes('aria-label')).toBe('Change user');
    await back.trigger('click');
    expect(wrapper.emitted('back')).toHaveLength(1);
  });

  it('names its keys in Spanish', async () => {
    const { wrapper } = await mountBase(PinPad, { props: { length: 4, label: 'Introduce tu PIN' }, locale: 'es' });
    expect(wrapper.get('[data-testid="pinpad-erase"]').attributes('aria-label')).toBe('Borrar');
  });
});
