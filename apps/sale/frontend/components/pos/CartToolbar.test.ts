// The bar on top of the check (WORKBOOK «Vender»): «Park this check» (only where parked tickets are
// allowed), the customer button (the Customers app's, in the slot), «Open checks» with how many, and
// «Close» in the phone's drawer.
import { describe, expect, it } from 'vitest';
import { h } from 'vue';

import { click, mountSale } from '../../__tests__/mount-sale';
import CartToolbar from './CartToolbar.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(
    {
      components: { CartToolbar },
      setup: () => () =>
        h(
          CartToolbar,
          { parkingEnabled: true, hasLines: true, openChecks: 0, checksOpen: false, drawer: false, ...props },
          { default: () => h('button', { 'data-testid': 'slot-customer' }, 'Assign customer') },
        ),
    },
    { locale },
  );
}

const disabled = (el: Element) => (el as HTMLElement & { disabled?: boolean }).disabled === true;

describe('CartToolbar', () => {
  it('parks, holds the customer button and opens the open checks', async () => {
    const m = await setup({}, 'es');
    const park = m.find('pos-park');
    expect(park.attributes('aria-label')).toBe('Aparcar esta cuenta');
    expect(m.find('slot-customer').exists()).toBe(true);
    const checks = m.find('pos-open-checks');
    expect(checks.attributes('aria-label')).toBe('Cuentas abiertas');
    expect(checks.attributes('aria-expanded')).toBe('false');
    expect(m.find('pos-open-checks-count').exists()).toBe(false);
    await click(park.element);
    await click(checks.element);
    const toolbar = m.wrapper.findComponent(CartToolbar);
    expect(toolbar.emitted('park')).toHaveLength(1);
    expect(toolbar.emitted('toggleChecks')).toHaveLength(1);
  });

  it('counts the other open checks on their icon', async () => {
    const m = await setup({ openChecks: 3, checksOpen: true });
    expect(m.find('pos-open-checks-count').text()).toBe('3');
    expect(m.find('pos-open-checks').attributes('aria-expanded')).toBe('true');
  });

  it('nothing to park on an empty check; no park at all where parked tickets are off', async () => {
    expect(disabled((await setup({ hasLines: false })).find('pos-park').element)).toBe(true);
    expect((await setup({ parkingEnabled: false })).find('pos-park').exists()).toBe(false);
  });

  it('«Close» only in the phone’s drawer', async () => {
    expect((await setup()).find('pos-cart-close').exists()).toBe(false);
    const m = await setup({ drawer: true });
    const close = m.find('pos-cart-close');
    expect(close.attributes('aria-label')).toBe('Close');
    await click(close.element);
    expect(m.wrapper.findComponent(CartToolbar).emitted('close')).toHaveLength(1);
  });
});
