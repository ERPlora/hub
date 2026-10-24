// The faces and the PIN pad of a shared till (BASE-G55, G60): a card per person with a PIN (initials and name, never
// an email: gh:hub#2536), the pad of the chosen one, and back to the faces. One person: already chosen.
import { afterEach, describe, expect, it } from 'vitest';

import { mountBase } from '../__tests__/mount-base';
import PinDoor from './PinDoor.vue';

const ANA = { id: 'c-ana', name: 'Ana López', initials: 'AL' };
const BEA = { id: 'c-bea', name: 'Bea', initials: 'B' };

afterEach(() => {
  document.body.innerHTML = '';
});

async function door(props: Record<string, unknown> = {}) {
  const mounted = await mountBase(PinDoor, {
    props: { people: [ANA, BEA], pinLength: 4, chooseLabel: 'Choose your user', backLabel: 'Change user', ...props },
  });
  const press = async (digits: string) => {
    for (const digit of digits) await mounted.wrapper.get(`[data-testid="pinpad-key-${digit}"]`).trigger('click');
  };
  return { ...mounted, press };
}

describe('PinDoor', () => {
  it('shows a face per person, with their initials and name and nothing else', async () => {
    const { wrapper } = await door();
    const faces = wrapper.findAll('[data-testid="pin-face"]');
    expect(faces.map((face) => face.text())).toEqual(['ALAna López', 'BBea']);
    expect(wrapper.text()).toContain('Choose your user');
    expect(wrapper.find('[data-testid="pinpad"]').exists()).toBe(false);
  });

  it('a face opens its pad; its PIN enters as that person, at the last digit', async () => {
    const { wrapper, press } = await door();
    await wrapper.findAll('[data-testid="pin-face"]')[1].trigger('click');
    expect(wrapper.get('[data-testid="pin-door-chosen"]').text()).toContain('Bea');
    expect(wrapper.get('[data-testid="pinpad"]').attributes('aria-label')).toBe('PIN of Bea');
    await press('9071');
    expect(wrapper.emitted('enter')).toEqual([[{ person: 'c-bea', pin: '9071' }]]);
  });

  it('the arrow goes back to the faces', async () => {
    const { wrapper } = await door();
    await wrapper.findAll('[data-testid="pin-face"]')[0].trigger('click');
    await wrapper.get('[data-testid="pinpad-back"]').trigger('click');
    expect(wrapper.findAll('[data-testid="pin-face"]')).toHaveLength(2);
  });

  it('with one person, the pad is already theirs and there is nobody to go back to', async () => {
    const { wrapper } = await door({ people: [ANA] });
    expect(wrapper.find('[data-testid="pin-face"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="pinpad"]').attributes('aria-label')).toBe('PIN of Ana López');
    expect(wrapper.find('[data-testid="pinpad-back"]').exists()).toBe(false);
  });

  it('someone who leaves the grid (given leave, PIN removed) is no longer chosen', async () => {
    const { wrapper } = await door();
    await wrapper.findAll('[data-testid="pin-face"]')[1].trigger('click');
    await wrapper.setProps({ people: [ANA, { id: 'c-cai', name: 'Cai', initials: 'C' }] });
    expect(wrapper.findAll('[data-testid="pin-face"]')).toHaveLength(2);
  });

  it('paints the refusal under the circles and takes nothing while an entry is on its way', async () => {
    const { wrapper, press } = await door({ people: [ANA], error: 'Wrong PIN.', busy: true });
    expect(wrapper.get('[data-testid="pinpad-error"]').text()).toBe('Wrong PIN.');
    await press('4826');
    expect(wrapper.emitted('enter')).toBeUndefined();
  });
});
