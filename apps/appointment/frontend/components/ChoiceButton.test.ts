// A choice of the booking panel (a length, a free time): a big button that says whether it is the one chosen, never
// sends the form, and can carry a mark (a time inside the minimum notice).
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import ChoiceButton from './ChoiceButton.vue';

function setup(props: Record<string, unknown>) {
  return { wrapper: mount(ChoiceButton, { props: props as { pressed: boolean }, slots: { default: '30' } }) };
}

describe('ChoiceButton', () => {
  it('is a plain button that says whether it is pressed, with its words', async () => {
    const s = setup({ pressed: true });
    const button = s.wrapper.get('button');
    expect([button.attributes('type'), button.attributes('aria-pressed'), button.text()]).toEqual(['button', 'true', '30']);
    await s.wrapper.setProps({ pressed: false });
    expect(button.attributes('aria-pressed')).toBe('false');
  });

  it('carries its mark and what the page gives it, and a click reaches the page', async () => {
    let clicks = 0;
    const s = setup({ pressed: false, marked: true, 'data-testid': 'x', onClick: () => (clicks += 1) });
    const button = s.wrapper.get('button');
    expect(button.classes()).toContain('choice-button--marked');
    expect(button.attributes('data-testid')).toBe('x');
    await button.trigger('click');
    expect(clicks).toBe(1);
  });
});
