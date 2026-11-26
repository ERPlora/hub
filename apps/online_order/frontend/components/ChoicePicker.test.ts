// ChoicePicker (ONLINE_ORDER-F04): one group of what goes with a dish or a set menu, as the customer picks it. Its rule
// above its choices; a checkbox per choice, the unchecked ones waiting once a group with a ceiling is full; one-less
// and one-more buttons with the count where a choice may repeat. The taps go up.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountInShell } from '../__tests__/mount-online-order';
import { MONEY, SAUCES as GROUP, VISITOR } from '../__tests__/table-page';
import en from '../locale/en.json';
import es from '../locale/es.json';
import ChoicePicker, { type PickGroup } from './ChoicePicker.vue';

const SAUCES: PickGroup = { ...GROUP, options: [...GROUP.options, { id: 'o3', name: 'Mojo', price_delta: 0, allergens: [] }] };

type Control = Element & { checked?: boolean; disabled?: boolean };

async function setup(group: PickGroup, picks: string[] = []) {
  const mounted = await mountInShell(
    ChoicePicker,
    { props: { group, choice: { picks, refused: null }, money: MONEY }, session: VISITOR },
    { path: '/p/casa-pepe/order/code', session: VISITOR, messages: { en, es } },
  );
  const prop = (testid: string, name: 'checked' | 'disabled') =>
    (mounted.wrapper.find(`[data-testid="${testid}"]`).element as Control)[name];
  return { ...mounted, prop };
}

describe('ChoicePicker', () => {
  it('names the group with how many to pick, and each choice with what it adds', async () => {
    const s = await setup(SAUCES);
    const html = s.wrapper.html();
    expect(html).toContain('Sauces');
    expect(html).toContain('Optional · up to 2');
    expect(s.wrapper.find('[data-testid="oo-pick-o1"]').text()).toContain('+€0.50');
    expect(s.wrapper.find('[data-testid="oo-pick-o1"]').html()).toContain('Egg');
  });

  it('sends a tap up when a choice is checked, and shows what is chosen', async () => {
    const s = await setup(SAUCES, ['o2']);
    await ionValue(s.wrapper.find('[data-testid="oo-pick-check-o1"]').element, true);
    expect(s.wrapper.emitted('tap')).toEqual([['o1']]);
    expect(s.prop('oo-pick-check-o2', 'checked')).toBe(true);
    expect(s.prop('oo-pick-check-o1', 'checked')).toBe(false);
  });

  it('lets the unchecked choices wait once the group is full', async () => {
    const s = await setup(SAUCES, ['o1', 'o2']);
    expect(s.prop('oo-pick-check-o3', 'disabled')).toBe(true);
    expect(s.prop('oo-pick-check-o1', 'disabled')).toBe(false);
  });

  it('swaps in a group of one: nothing waits', async () => {
    const s = await setup({ ...SAUCES, min_choices: 1, max_choices: 1 }, ['o1']);
    expect(s.prop('oo-pick-check-o2', 'disabled')).toBe(false);
    expect(s.wrapper.html()).toContain('Choose 1');
  });

  it('counts a choice that may repeat, with one less and one more', async () => {
    const s = await setup({ ...SAUCES, allow_repeat: true }, ['o1', 'o1']);
    expect(s.wrapper.find('[data-testid="oo-pick-count-o1"]').text()).toBe('2');
    expect(s.prop('oo-pick-less-o2', 'disabled')).toBe(true);
    expect(s.prop('oo-pick-more-o3', 'disabled')).toBe(true);
    await click(s.wrapper.find('[data-testid="oo-pick-less-o1"]').element);
    expect(s.wrapper.emitted('less')).toEqual([['o1']]);
  });
});
