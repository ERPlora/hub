// The check column (WORKBOOK «Vender» — «Cuenta»): the bar (park, customer, open checks, close), the
// heading (title and chips), the lines and the foot, from what the page knows of the check. It paints and
// asks; the page writes. «Open checks» opens its dropdown here.
import { describe, expect, it } from 'vitest';
import { h } from 'vue';

import { click, mountSale } from '../../__tests__/mount-sale';
import { line, order, settings } from './__tests__/fixtures';
import CartFooter from './CartFooter.vue';
import CartHeading from './CartHeading.vue';
import CartLines from './CartLines.vue';
import CartToolbar from './CartToolbar.vue';
import OpenChecksPopover from './OpenChecksPopover.vue';
import PosCart from './PosCart.vue';

const CHECK = order({ label: 'Table 4', discount_percent: '10.00', lines: [line({ id: 'l1' }), line({ id: 'l2', product_id: 'p2' })] });

function props(over: Record<string, unknown> = {}) {
  return {
    order: CHECK,
    label: 'Table 4',
    total: 270,
    ticketDiscount: 30,
    marks: ['l2'],
    staffNames: { s1: 'Marta' },
    settings: settings(),
    customerName: 'Lucía',
    staffId: 's1',
    staffName: 'Marta',
    needsCustomer: false,
    busy: false,
    drawer: false,
    openChecks: 2,
    ...over,
  };
}

async function setup(over: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSale(
    { setup: () => () => h(PosCart, props(over), { customer: () => h('button', { 'data-testid': 'slot-customer' }, 'Lucía') }) },
    { locale },
  );
  return { ...m, cart: () => m.wrapper.findComponent(PosCart) };
}

describe('PosCart', () => {
  it('hands each piece what it paints', async () => {
    const m = await setup();
    expect(m.wrapper.findComponent(CartToolbar).props()).toMatchObject({ parkingEnabled: true, hasLines: true, openChecks: 2, drawer: false });
    expect(m.find('slot-customer').exists()).toBe(true);
    expect(m.wrapper.findComponent(CartHeading).props()).toMatchObject({ label: 'Table 4', customerName: 'Lucía', staffId: 's1', staffName: 'Marta' });
    expect(m.wrapper.findComponent(CartLines).props()).toMatchObject({ lines: CHECK.lines, marks: ['l2'], allowDiscounts: true });
    expect(m.wrapper.findComponent(CartFooter).props()).toMatchObject({
      hasLines: true,
      total: 270,
      discountPercent: '10.00',
      ticketDiscount: 30,
      blockedReason: null,
    });
    expect(m.find('pos-cart').attributes('id')).toBe('pos-cart-drawer');
  });

  it('the table button sits before the customer’s, and the heading names the check’s table (SALE-F19)', async () => {
    const m = await mountSale({
      setup: () => () =>
        h(PosCart, props({ tableNumber: '4' }), {
          table: () => h('button', { 'data-testid': 'slot-table' }, 'Table'),
          customer: () => h('button', { 'data-testid': 'slot-customer' }, 'Lucía'),
        }),
    });
    const slot = m.wrapper.find('.pos-toolbar__slot');
    expect(slot.findAll('button').map((b) => b.attributes('data-testid'))).toEqual(['slot-table', 'slot-customer']);
    expect(m.wrapper.findComponent(CartHeading).props('tableNumber')).toBe('4');
    const bare = await setup();
    expect(bare.wrapper.findComponent(CartHeading).props('tableNumber')).toBeNull();
  });

  it('without a check: no lines, nothing to charge, the total is zero', async () => {
    const m = await setup({ order: null, label: '', total: undefined, marks: [] });
    expect(m.wrapper.findComponent(CartLines).props('lines')).toEqual([]);
    expect(m.wrapper.findComponent(CartFooter).props()).toMatchObject({ hasLines: false, total: 0 });
  });

  it('a required customer that is missing blocks Charge with its reason', async () => {
    const m = await setup({ needsCustomer: true, customerName: null }, 'es');
    expect(m.wrapper.findComponent(CartFooter).props('blockedReason')).toBe(
      'Este negocio exige un cliente en cada venta. Elige uno para seguir con el cobro.',
    );
  });

  it('opens and closes the open checks', async () => {
    const m = await setup();
    expect(m.wrapper.findComponent(OpenChecksPopover).exists()).toBe(false);
    m.wrapper.findComponent(CartToolbar).vm.$emit('toggleChecks');
    await m.wrapper.vm.$nextTick();
    expect(m.wrapper.findComponent(OpenChecksPopover).props()).toMatchObject({ currentId: 'o1', parkingEnabled: true, hasLines: true });
    m.wrapper.findComponent(OpenChecksPopover).vm.$emit('close');
    await m.wrapper.vm.$nextTick();
    expect(m.wrapper.findComponent(OpenChecksPopover).exists()).toBe(false);
  });

  it('passes every request up', async () => {
    const m = await setup();
    const L = CHECK.lines[0];
    m.wrapper.findComponent(CartToolbar).vm.$emit('park');
    m.wrapper.findComponent(CartToolbar).vm.$emit('close');
    m.wrapper.findComponent(CartHeading).vm.$emit('rename', 'T5');
    m.wrapper.findComponent(CartHeading).vm.$emit('staff');
    m.wrapper.findComponent(CartHeading).vm.$emit('askCustomer');
    const lines = m.wrapper.findComponent(CartLines);
    lines.vm.$emit('mark', L);
    lines.vm.$emit('quantity', L, '2');
    lines.vm.$emit('discount', L);
    lines.vm.$emit('note', L);
    lines.vm.$emit('gift', L);
    lines.vm.$emit('staff', L);
    lines.vm.$emit('void', L);
    const foot = m.wrapper.findComponent(CartFooter);
    foot.vm.$emit('discount');
    foot.vm.$emit('prebill');
    foot.vm.$emit('charge');
    const cart = m.cart();
    expect(cart.emitted('park')).toHaveLength(1);
    expect(cart.emitted('close')).toHaveLength(1);
    expect(cart.emitted('rename')).toEqual([['T5']]);
    expect(cart.emitted('staff')).toHaveLength(1);
    expect(cart.emitted('askCustomer')).toHaveLength(1);
    expect(cart.emitted('mark')).toEqual([[L]]);
    expect(cart.emitted('quantity')).toEqual([[L, '2']]);
    for (const event of ['lineDiscount', 'note', 'gift', 'lineStaff', 'voidLine']) expect(cart.emitted(event), event).toEqual([[L]]);
    for (const event of ['ticketDiscount', 'prebill', 'charge']) expect(cart.emitted(event), event).toHaveLength(1);
  });

  it('the dropdown resumes a check and parks this one', async () => {
    const m = await setup();
    await click(m.find('pos-open-checks').element);
    const popover = m.wrapper.findComponent(OpenChecksPopover);
    const row = { id: 'o2' };
    popover.vm.$emit('resume', row);
    popover.vm.$emit('park');
    expect(m.cart().emitted('resume')).toEqual([[row]]);
    expect(m.cart().emitted('park')).toHaveLength(1);
  });
});
