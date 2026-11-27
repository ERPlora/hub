// The foot of the check (WORKBOOK «Vender»): the «Ticket discount» row when there is one, «Total» (the
// one the server works out), the discount button, the printer («Print bill») and Charge: the cash icon and the amount,
// named «Charge · <amount>».
// Charge is blocked but still answers when something is missing (SALE-F05): the page says what.
import { describe, expect, it } from 'vitest';

import { HubIcon } from '@erplora/ui/shell';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import CartFooter from './CartFooter.vue';

/** Ionic's `disabled` is a property of the element, not an attribute. */
const disabled = (el: Element) => (el as HTMLElement & { disabled?: boolean }).disabled === true;

/** What Charge shows (its amount), what it is called and its tooltip. */
function charge(m: Awaited<ReturnType<typeof setup>>) {
  const button = m.find('pos-charge');
  return { shown: plain(button.text()), name: plain(button.attributes('aria-label') ?? ''), tooltip: plain(button.attributes('title') ?? '') };
}

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const mounted = await mountSale(CartFooter, {
    props: {
      hasLines: true,
      total: 1250,
      discountPercent: '0.00',
      discountAmount: 0,
      ticketDiscount: 0,
      allowDiscounts: true,
      blockedReason: null,
      ...props,
    },
    locale,
  });
  await mounted.live();
  return mounted;
}

describe('CartFooter', () => {
  it('paints the server’s total, and Charge as its cash icon and the amount, named «Charge · total»', async () => {
    const m = await setup({}, 'es');
    expect(plain(m.find('pos-total').text())).toBe('12,50 €');
    expect(charge(m)).toEqual({ shown: '12,50 €', name: 'Cobrar · 12,50 €', tooltip: 'Cobrar · 12,50 €' });
    expect(m.find('pos-charge').findComponent(HubIcon).props('name')).toBe('ion:cash-outline');
    expect(m.find('pos-ticket-discount-row').exists()).toBe(false);
  });

  it('with lines marked, Charge shows what it charges and is named with how many; Total stays the whole check (SALE-F22)', async () => {
    const one = await setup({ total: 750, markedLines: 1, markedTotal: 180 }, 'es');
    expect(charge(one)).toEqual({ shown: '1,80 €', name: 'Cobrar 1 línea · 1,80 €', tooltip: 'Cobrar 1 línea · 1,80 €' });
    expect(plain(one.find('pos-total').text())).toBe('7,50 €');
    const two = await setup({ total: 750, markedLines: 2, markedTotal: 360 }, 'es');
    expect(charge(two)).toMatchObject({ shown: '3,60 €', name: 'Cobrar 2 líneas · 3,60 €' });
    const en = await setup({ total: 750, markedLines: 1, markedTotal: 180 });
    expect(charge(en)).toMatchObject({ shown: '€1.80', name: 'Charge 1 line · €1.80' });
    const enMany = await setup({ total: 750, markedLines: 3, markedTotal: 540 });
    expect(charge(enMany)).toMatchObject({ shown: '€5.40', name: 'Charge 3 lines · €5.40' });
  });

  it('with nothing marked, Charge says the whole check', async () => {
    const m = await setup({ total: 750, markedLines: 0, markedTotal: undefined }, 'es');
    expect(charge(m)).toMatchObject({ shown: '7,50 €', name: 'Cobrar · 7,50 €' });
  });

  it('while what the marked lines come to is on its way, Charge shows a dash, never the whole check', async () => {
    const m = await setup({ total: 750, markedLines: 1, markedTotal: undefined });
    expect(charge(m)).toMatchObject({ shown: '—', name: 'Charge 1 line · —' });
  });

  it('while the total is still on its way it shows a dash, never a number of its own', async () => {
    const m = await setup({ total: undefined });
    expect(m.find('pos-total').text()).toBe('—');
  });

  it('the ticket discount row: the percentage, and what it takes off as the server says', async () => {
    const m = await setup({ discountPercent: '10.00', ticketDiscount: 139 }, 'es');
    const row = m.find('pos-ticket-discount-row');
    expect(plain(row.text())).toContain('Descuento del tique −10 %');
    expect(plain(row.text())).toContain('−1,39 €');
    const amount = await setup({ discountAmount: 500, ticketDiscount: 500 });
    expect(plain(amount.find('pos-ticket-discount-row').text())).toContain('−€5.00');
  });

  it('discount, bill and charge are asked up', async () => {
    const m = await setup();
    await click(m.find('pos-ticket-discount').element);
    await click(m.find('pos-prebill').element);
    await click(m.find('pos-charge').element);
    expect(m.wrapper.emitted('discount')).toHaveLength(1);
    expect(m.wrapper.emitted('prebill')).toHaveLength(1);
    expect(m.wrapper.emitted('charge')).toHaveLength(1);
    expect(m.find('pos-prebill').attributes('aria-label')).toBe('Print bill');
    expect(m.find('pos-ticket-discount').attributes('aria-label')).toBe('Ticket discount');
  });

  it('an empty check can do none of it', async () => {
    const m = await setup({ hasLines: false, total: 0 });
    for (const id of ['pos-ticket-discount', 'pos-prebill', 'pos-charge']) expect(disabled(m.find(id).element), id).toBe(true);
  });

  it('the discount button is an outlined tag until the check has a discount (% or amount), then a filled one', async () => {
    const icon = (m: Awaited<ReturnType<typeof setup>>) => m.find('pos-ticket-discount').findComponent(HubIcon).props('name');
    expect(icon(await setup())).toBe('ion:pricetag-outline');
    expect(icon(await setup({ discountPercent: '10.00', ticketDiscount: 139 }))).toBe('ion:pricetag');
    expect(icon(await setup({ discountAmount: 500, ticketDiscount: 500 }))).toBe('ion:pricetag');
  });

  it('no discount button when the business does not allow discounts', async () => {
    const m = await setup({ allowDiscounts: false });
    expect(m.find('pos-ticket-discount').exists()).toBe(false);
  });

  it('blocked, Charge looks so and says why, but still takes the tap', async () => {
    const m = await setup({ blockedReason: 'This business requires a customer on every sale.' });
    const charge = m.find('pos-charge');
    expect(charge.attributes('aria-disabled')).toBe('true');
    expect(charge.classes()).toContain('pos-charge--blocked');
    expect(charge.attributes('title')).toBe('This business requires a customer on every sale.');
    expect(plain(charge.attributes('aria-label') ?? '')).toBe('Charge · €12.50');
    expect(disabled(charge.element)).toBe(false);
    await click(charge.element);
    expect(m.wrapper.emitted('charge')).toHaveLength(1);
  });
});
