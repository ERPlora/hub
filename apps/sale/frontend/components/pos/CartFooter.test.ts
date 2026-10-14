// The foot of the check (WORKBOOK «Vender»): the «Ticket discount» row when there is one, «Total» (the
// one the server works out), the discount button, the printer («Print bill») and «Charge · <amount>».
// Charge is blocked but still answers when something is missing (SALE-F05): the page says what.
import { describe, expect, it } from 'vitest';

import { click, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import CartFooter from './CartFooter.vue';

/** Ionic's `disabled` is a property of the element, not an attribute. */
const disabled = (el: Element) => (el as HTMLElement & { disabled?: boolean }).disabled === true;

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  return mountSale(CartFooter, {
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
}

describe('CartFooter', () => {
  it('paints the server’s total and «Charge · total»', async () => {
    const m = await setup({}, 'es');
    expect(plain(m.find('pos-total').text())).toBe('12,50 €');
    expect(plain(m.find('pos-charge').text())).toBe('Cobrar · 12,50 €');
    expect(m.find('pos-ticket-discount-row').exists()).toBe(false);
  });

  it('while the total is still on its way it shows a dash, never a number of its own', async () => {
    const m = await setup({ total: undefined });
    expect(m.find('pos-total').text()).toBe('—');
  });

  it('the ticket discount row: the percentage, and what it takes off as the server says', async () => {
    const m = await setup({ discountPercent: '10.00', ticketDiscount: 139 }, 'es');
    const row = m.find('pos-ticket-discount-row');
    expect(plain(row.text())).toContain('Descuento del ticket −10 %');
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
    expect(disabled(charge.element)).toBe(false);
    await click(charge.element);
    expect(m.wrapper.emitted('charge')).toHaveLength(1);
  });
});
