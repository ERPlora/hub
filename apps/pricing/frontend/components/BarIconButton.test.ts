// A button of a page's bar whose icon says what it does (the bin of a price list's detail): in the bar, the icon alone,
// its label as its accessible name and its title; listed in the bar's «⋮» on a phone, a row with its icon and its
// label, which acts once the menu has gone.
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, provide } from 'vue';

import { TOPBAR_MENU_KEY } from '../../../../packages/ui/src/shell/topbar-menu';
import { mountPricing } from '../__tests__/mount-pricing';
import BarIconButton from './BarIconButton.vue';

const PROPS = { testid: 'pricing-detail-delete', icon: 'ion:trash-outline', label: 'Delete', color: 'danger' };

describe('BarIconButton', () => {
  it('in the bar is the icon alone, named by its label, and says it was pressed', async () => {
    const m = await mountPricing(BarIconButton, { props: PROPS });
    const button = m.wrapper.get('[data-testid="pricing-detail-delete"]');
    expect([button.attributes('aria-label'), button.attributes('title'), button.text()]).toEqual(['Delete', 'Delete', '']);
    expect(button.find('[slot="icon-only"]').exists()).toBe(true);
    await button.trigger('click');
    expect(m.wrapper.emitted('press')).toEqual([[]]);
  });

  it('listed in the bar’s «⋮» it is a row with its icon and its label, pressed once the menu has gone', async () => {
    const waiting: Array<() => void> = [];
    const closeThen = vi.fn((action: () => void) => waiting.push(action));
    let pressed = 0;
    const InTheMenu = defineComponent(() => {
      provide(TOPBAR_MENU_KEY, { closeThen });
      return () => h(BarIconButton, { ...PROPS, onPress: () => (pressed += 1) });
    });
    const m = await mountPricing(InTheMenu);
    const button = m.wrapper.get('[data-testid="pricing-detail-delete"]');
    expect(button.text()).toBe('Delete');
    expect(button.find('[slot="start"]').exists()).toBe(true);
    await button.trigger('click');
    expect([closeThen.mock.calls.length, pressed]).toEqual([1, 0]);
    waiting[0]();
    expect(pressed).toBe(1);
  });
});
