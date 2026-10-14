// The phone's cart button (WORKBOOK «Vender»: «the floating button with the total»): a cart while the
// check is empty; with items, a pill with the server's total and how many, and a name that says both.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import CartFab from './CartFab.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(CartFab, { props: { count: 0, total: undefined, expanded: false, ...props }, locale });
}

describe('CartFab', () => {
  it('with an empty check it is only the cart, «Open cart»', async () => {
    const m = await setup({}, 'es');
    const fab = m.find('pos-cart-fab');
    expect(fab.attributes('aria-label')).toBe('Abrir carrito');
    expect(fab.attributes('aria-controls')).toBe('pos-cart-drawer');
    expect(fab.attributes('aria-expanded')).toBe('false');
    expect(fab.attributes('data-has-items')).toBeUndefined();
    expect(m.find('pos-cart-fab-total').exists()).toBe(false);
  });

  it('with items, the total and the count, said in words too (one and many)', async () => {
    const one = await setup({ count: 1, total: 150 }, 'es');
    expect(plain(one.find('pos-cart-fab').attributes('aria-label') ?? '')).toBe('Abrir carrito, 1 artículo, total 1,50 €');
    const many = await setup({ count: 3, total: 1250 });
    const fab = many.find('pos-cart-fab');
    expect(fab.attributes('data-has-items')).toBe('true');
    expect(plain(many.find('pos-cart-fab-total').text())).toBe('€12.50');
    expect(many.find('pos-cart-fab-count').text()).toBe('3');
    expect(fab.attributes('aria-label')).toBe('Open cart, 3 items, total €12.50');
  });

  it('opens the drawer', async () => {
    const m = await setup({ count: 2, total: 300 });
    await click(m.find('pos-cart-fab').element);
    expect(m.wrapper.emitted('open')).toHaveLength(1);
  });
});
