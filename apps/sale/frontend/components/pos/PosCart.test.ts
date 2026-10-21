// The check column (WORKBOOK «Vender» — «Cuenta»): the bar (park, customer, open checks, close), the
// heading (title and chips), the lines and the foot, from what the page knows of the check. It paints and
// asks; the page writes. «Open checks» opens its dropdown here.
import { describe, expect, it } from 'vitest';
import { h, ref } from 'vue';

import { click, mountSale, settle } from '../../__tests__/mount-sale';
import { line, order, settings } from './__tests__/fixtures';
import CartFooter from './CartFooter.vue';
import CartHeading from './CartHeading.vue';
import CartLines from './CartLines.vue';
import CartToolbar from './CartToolbar.vue';
import KitchenTickets from './KitchenTickets.vue';
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

describe('PosCart: «Check» and «Current order» with Kitchen (SALE-F20)', () => {
  const SENT = line({ id: 'l3', product_id: 'p3', round_no: 1, fired_at: '2026-10-20T12:00:00Z' });
  const WITH_ROUND = order({ lines: [line({ id: 'l1' }), line({ id: 'l2', product_id: 'p2' }), SENT] });

  it('without Kitchen there are no tabs: the check is all there is', async () => {
    const m = await setup();
    expect(m.find('pos-cart-tabs').exists()).toBe(false);
  });

  it('says how many items wait to be sent, also to a screen reader', async () => {
    const m = await setup({ kitchen: true, order: WITH_ROUND }, 'es');
    const tab = m.find('pos-cart-tab-round');
    expect(tab.attributes('aria-label')).toBe('Comanda actual, 2 artículos por enviar');
    expect(m.find('pos-cart-tab-round-badge').text()).toBe('2');
    expect(m.find('pos-cart-tab-check').attributes('aria-selected')).toBe('true');
    expect(m.wrapper.findComponent(CartLines).props('lines')).toHaveLength(3);
  });

  it('«Current order» shows only what is pending, with the send bar; a send goes up with its rush', async () => {
    const m = await setup({ kitchen: true, order: WITH_ROUND }, 'es');
    await click(m.find('pos-cart-tab-round').element);
    expect(m.find('pos-cart-tab-round').attributes('aria-selected')).toBe('true');
    expect(m.wrapper.findComponent(CartLines).props('lines').map((l: { id: string }) => l.id)).toEqual(['l1', 'l2']);
    expect(m.find('pos-cart-round-hint').text()).toContain('Revisa cantidades');
    await click(m.find('pos-kitchen-send').element);
    expect(m.cart().emitted('send')).toEqual([[false]]);
  });

  it('«Tickets · N» follows the check’s kitchen tickets in the head of what it sent, only when they can be seen (KITCHEN-F19)', async () => {
    const m = await setup({ kitchen: true, kitchenTickets: true, order: WITH_ROUND });
    const tickets = m.wrapper.findComponent(KitchenTickets);
    expect(tickets.exists()).toBe(true);
    expect(tickets.props('orderId')).toBe(WITH_ROUND.id);
    for (const over of [{ kitchenTickets: false }, { kitchenTickets: true, order: order({ lines: [line({ id: 'l1' })] }) }]) {
      const without = await setup({ kitchen: true, order: WITH_ROUND, ...over });
      expect(without.wrapper.findComponent(KitchenTickets).exists()).toBe(false);
    }
  });

  it('the first line opening the check keeps «Current order»; another check starts on «Check» (KITCHEN-F18)', async () => {
    const shown = ref<ReturnType<typeof order> | null>(null);
    const m = await mountSale(
      { setup: () => () => h(PosCart, props({ kitchen: true, order: shown.value })) },
      { locale: 'en' },
    );
    await click(m.find('pos-cart-tab-round').element);
    shown.value = order({ id: 'o9', lines: [line({ id: 'l1' })] });
    await settle();
    expect(m.find('pos-cart-tab-round').attributes('aria-selected')).toBe('true');
    expect(m.find('pos-kitchen-send').exists()).toBe(true);
    shown.value = order({ id: 'o10', lines: [line({ id: 'l2' })] });
    await settle();
    expect(m.find('pos-cart-tab-check').attributes('aria-selected')).toBe('true');
  });

  it('with everything sent «Current order» says so and offers no send', async () => {
    const m = await setup({ kitchen: true, order: order({ lines: [SENT] }) }, 'es');
    expect(m.find('pos-cart-tab-round').attributes('aria-label')).toBe('Comanda actual');
    await click(m.find('pos-cart-tab-round').element);
    expect(m.find('pos-cart-round-empty').text()).toContain('Todo está enviado');
    expect(m.find('pos-kitchen-send').exists()).toBe(false);
  });
});
