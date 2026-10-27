// The sale screens in the business's currency (flow business-currency): the till paints and types the money of the
// business (`base.business.get`, its country's, with the decimals the server counts), and what was charged is shown
// with the sale's own currency, never the euro by default nor rewritten when the business's changes. Until the
// business answers, an amount is a figure without a sign.
import { describe, expect, it, vi } from 'vitest';
import { h, ref } from 'vue';

import { business, click, JAPANESE, mountSale, POLISH, settle } from '../__tests__/mount-sale';
import { plain } from '../lib/format';
import PayKeypad from './checkout/PayKeypad.vue';
import { saleOut, SETTINGS } from './document/__tests__/fixtures';
import ReceiptPaper from './document/ReceiptPaper.vue';
import CartFooter from './pos/CartFooter.vue';
import DiscountSheet from './pos/DiscountSheet.vue';
import { product } from './pos/__tests__/fixtures';
import ProductGrid from './pos/ProductGrid.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const FOOT = { hasLines: true, total: 1250, discountPercent: '0.00', discountAmount: 0, ticketDiscount: 0, allowDiscounts: true, blockedReason: null };

describe('the till, in the business’s currency', () => {
  it('a business in Poland sees its total and «Charge» in zlotys', async () => {
    const m = await mountSale(CartFooter, { props: FOOT, locale: 'es', business: business(POLISH) });
    await m.live();
    expect(plain(m.find('pos-total').text())).toBe('12,50 zł');
    expect(plain(m.find('pos-charge').text())).toBe('Cobrar · 12,50 zł');
  });

  it('a business in Japan sees yen without decimals', async () => {
    const m = await mountSale(CartFooter, { props: { ...FOOT, total: 1250 }, locale: 'en', business: business(JAPANESE) });
    await m.live();
    expect(m.find('pos-total').text()).toBe('¥1,250');
  });

  it('until the business answers, the total is a figure without a sign, never in euros', async () => {
    const m = await mountSale(CartFooter, { props: FOOT, locale: 'es', business: null });
    await m.live();
    expect(plain(m.find('pos-total').text())).toBe('12,50');
  });

  it('the discount switches to an amount with the business’s sign, not «€» (gh:sales#380)', async () => {
    const open = ref(true);
    const m = await mountSale(
      {
        setup: () => () =>
          h(DiscountSheet, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), name: null, amount: 0, pending: false, error: null }),
      },
      { locale: 'es', business: business(POLISH) },
    );
    await m.live();
    await settle();
    expect(m.find('pos-discount-mode').findAll('ion-label').map((l) => l.element.innerHTML.trim())).toEqual(['%', 'zł']);
    m.find('pos-discount-mode').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'amount' } }));
    await settle();
    for (const key of ['5', 'dot', '5']) await click(m.find(`pos-key-${key}`).element);
    expect(plain(m.find('pos-discount-value').text())).toBe('5,50 zł');
  });

  it('a discount in yen is typed without a decimal key', async () => {
    const open = ref(true);
    const m = await mountSale(
      {
        setup: () => () =>
          h(DiscountSheet, { open: open.value, 'onUpdate:open': (v: boolean) => (open.value = v), name: null, amount: 0, pending: false, error: null }),
      },
      { locale: 'en', business: business(JAPANESE) },
    );
    await m.live();
    m.find('pos-discount-mode').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'amount' } }));
    await settle();
    expect((m.find('pos-key-dot').element as HTMLButtonElement).disabled).toBe(true);
    for (const key of ['5', '0', '0']) await click(m.find(`pos-key-${key}`).element);
    expect(m.find('pos-discount-value').text()).toBe('¥500');
  });

  it('the «Open price» tile is typed in the business’s currency: «+ zł» in Poland', async () => {
    const props = { products: [product({ id: 'p1', name: 'Coffee' })], loading: false, hasMore: false };
    const m = await mountSale(ProductGrid, { props, locale: 'es', business: business(POLISH) });
    await m.live();
    expect(m.find('pos-open-price-tile').find('.pos-tile__price').text()).toBe('+ zł');
  });

  it('the charge’s keypad has no decimal key in a currency without decimals', async () => {
    const m = await mountSale(PayKeypad, { props: { decimals: 0 } });
    expect((m.find('sale-checkout-keypad-dot').element as HTMLButtonElement).disabled).toBe(true);
    const euros = await mountSale(PayKeypad, { props: { decimals: 2 } });
    expect((euros.find('sale-checkout-keypad-dot').element as HTMLButtonElement).disabled).toBe(false);
  });
});

describe('what was charged, in the sale’s own currency', () => {
  it('a ticket charged in zlotys prints zlotys while the business is now in euros', async () => {
    const m = await mountSale(ReceiptPaper, {
      props: { sale: saleOut({ currency: 'PLN', currency_decimals: 2 }), settings: SETTINGS },
      locale: 'es',
    });
    const totals = m.wrapper.findAll('[data-testid="sale-receipt-total-row"]').map((row) => plain(row.text()));
    expect(totals.length).toBeGreaterThan(0);
    expect(totals.every((row) => row.includes('zł') && !row.includes('€'))).toBe(true);
  });
});
