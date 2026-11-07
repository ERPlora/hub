// The sale screens in the business's currency (flow business-currency): the till paints and types the money of the
// business (`base.business.get`, its country's, with the decimals the server counts), and what was charged is shown
// with the sale's own currency, never the euro by default nor rewritten when the business's changes. Until the
// business answers, the till paints no figure: a dash where the amount goes (hub#936: never 15.00 for 1,500 yen).
import { describe, expect, it, vi } from 'vitest';
import { type Component, h, ref } from 'vue';

import type { TargetGroupOut } from '../../../modifier/frontend/operations';
import { business, click, JAPANESE, mountSale, POLISH, settle } from '../__tests__/mount-sale';
import { plain } from '../lib/format';
import PayKeypad from './checkout/PayKeypad.vue';
import { LETTERHEAD, saleOut, SETTINGS } from './document/__tests__/fixtures';
import ReceiptPaper from './document/ReceiptPaper.vue';
import CartFab from './pos/CartFab.vue';
import CartFooter from './pos/CartFooter.vue';
import CartLine from './pos/CartLine.vue';
import ComboSheet from './pos/ComboSheet.vue';
import ComboTiles from './pos/ComboTiles.vue';
import DiscountSheet from './pos/DiscountSheet.vue';
import ModifierSheet from './pos/ModifierSheet.vue';
import OpenChecksPopover from './pos/OpenChecksPopover.vue';
import { line, orderRow, page, product, service } from './pos/__tests__/fixtures';
import ProductGrid from './pos/ProductGrid.vue';
import ProductSearch from './pos/ProductSearch.vue';
import ProductTile from './pos/ProductTile.vue';
import ServicePriceSheet from './pos/ServicePriceSheet.vue';
import ServiceSearchResults from './pos/ServiceSearchResults.vue';
import ServiceTile from './pos/ServiceTile.vue';

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

  // hub#936: «Charge · 15.00» for a check of 1,500 yen while the business had not answered (two decimals supposed).
  it('a ¥1,500 check before the business answers its money: a dash, as while the total is on its way', async () => {
    const m = await mountSale(CartFooter, { props: { ...FOOT, total: 1500 }, locale: 'es', business: null });
    await m.live();
    const before = [plain(m.find('pos-total').text()), plain(m.find('pos-charge').text())];
    await m.result('base.business.get', business(JAPANESE));
    const after = [plain(m.find('pos-total').text()), plain(m.find('pos-charge').text())];
    expect({ before, after }).toEqual({ before: ['—', 'Cobrar · —'], after: ['1.500 ¥', 'Cobrar · 1.500 ¥'] });
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

// hub#936: every piece of the till that paints money paints none before the business answers it, and then the yen.
const GROUP: TargetGroupOut = {
  id: 'extras',
  name: 'Extras',
  kitchen_name: '',
  min_choices: 0,
  max_choices: 1,
  allow_repeat: false,
  is_required: false,
  options: [{ id: 'cheese', name: 'Cheese', kitchen_name: '', price_delta: 500, tax_category_key: null, is_default: false }],
};
const dish = (id: string, name: string, price_delta = 0) => ({ id, product_id: `p-${id}`, product_name: name, sku: '', price_delta });
const MENU = {
  id: 'm1',
  name: 'Lunch',
  kitchen_name: 'LUNCH',
  price: 1500,
  supply_kind: 'service',
  sort_order: 0,
  groups: [{ id: 'mains', name: 'Mains', min_choices: 0, max_choices: 1, allow_repeat: false, options: [dish('steak', 'Steak', 500)] }],
};
const LINE = { line: line({ unit_price: 1500, line_total: 1500 }), markable: false, marked: false, staffName: null, allowDiscounts: true };
const text = (el: Element | null | undefined) => plain(el?.textContent ?? '').trim();

type Mounted = Awaited<ReturnType<typeof mountSale>>;
const PIECES: {
  piece: string;
  component: Component;
  props?: Record<string, unknown>;
  /** What the piece's own reads answer, before the business does. */
  seed?: (m: Mounted) => Promise<void>;
  read: (m: Mounted) => string;
  before?: string;
  after: string;
}[] = [
  {
    piece: 'the check’s ticket discount',
    component: CartFooter,
    props: { ...FOOT, total: 1000, discountAmount: 500, ticketDiscount: 500 },
    read: (m) => text(m.find('pos-ticket-discount-row').findAll('span')[1]?.element),
    after: '−¥500',
  },
  { piece: 'the phone’s cart button', component: CartFab, props: { count: 2, total: 1500, expanded: false }, read: (m) => text(m.find('pos-cart-fab-total').element), after: '¥1,500' },
  { piece: 'a line’s amount', component: CartLine, props: LINE, read: (m) => text(m.wrapper.find('.pos-line__amount').element), after: '¥1,500' },
  { piece: 'a line’s unit price', component: CartLine, props: LINE, read: (m) => text(m.wrapper.find('.pos-line__price').element), after: '¥1,500' },
  { piece: 'a product’s tile', component: ProductTile, props: { product: product({ price: 1500 }) }, read: (m) => text(m.wrapper.find('.pos-tile__price').element), after: '¥1,500' },
  { piece: 'a service’s tile', component: ServiceTile, props: { service: service({ price: 1500 }) }, read: (m) => text(m.wrapper.find('.pos-tile__price').element), after: '¥1,500' },
  {
    piece: 'a service’s tile «From»',
    component: ServiceTile,
    props: { service: service({ pricing_type: 'from', price: 6500 }) },
    read: (m) => text(m.wrapper.find('.pos-tile__price').element),
    before: 'From —',
    after: 'From ¥6,500',
  },
  {
    piece: 'the service amount’s «Use <price>»',
    component: ServicePriceSheet,
    props: { open: true, service: service({ pricing_type: 'from', price: 1500 }), pending: false, error: null },
    read: (m) => text(m.inDoc('pos-service-price-suggest')),
    before: 'Use —',
    after: 'Use ¥1,500',
  },
  {
    piece: 'the options sheet’s «Add · <price>»',
    component: ModifierSheet,
    props: { open: true, product: product({ price: 1500 }), groups: [GROUP], pending: false, error: null },
    read: (m) => text(m.inDoc('pos-options-add')),
    before: 'Add · —',
    after: 'Add · ¥1,500',
  },
  {
    piece: 'an option’s supplement',
    component: ModifierSheet,
    props: { open: true, product: product({ price: 1500 }), groups: [GROUP], pending: false, error: null },
    read: (m) => text(m.inDoc('pos-option-cheese')?.querySelector('.pos-options__delta')),
    after: '+¥500',
  },
  {
    piece: 'the menu sheet’s «Add · <price>»',
    component: ComboSheet,
    props: { open: true, combo: MENU, pending: false, error: null },
    read: (m) => text(m.inDoc('pos-menu-add')),
    before: 'Add · —',
    after: 'Add · ¥1,500',
  },
  {
    piece: 'a dish’s supplement',
    component: ComboSheet,
    props: { open: true, combo: MENU, pending: false, error: null },
    read: (m) => text(m.inDoc('pos-menu-dish-steak')?.querySelector('.pos-options__delta')),
    after: '+¥500',
  },
  {
    piece: 'a menu’s tile',
    component: ComboTiles,
    seed: (m) => m.result('combo.combo.for_sale', page([MENU])),
    read: (m) => text(m.find('pos-menu-m1').find('.pos-tile__price').element),
    after: '¥1,500',
  },
  {
    piece: 'a product found by the search',
    component: ProductSearch,
    seed: (m) => m.result('inventory.product.list', page([product({ id: 'p1', price: 1500 })])),
    read: (m) => text(m.find('pos-search-p1').find('.pos-search__price').element),
    after: '¥1,500',
  },
  {
    piece: 'a service found by the search',
    component: ServiceSearchResults,
    props: { term: 'cut' },
    seed: (m) => m.result('service.service.list_for_sale', page([service({ id: 'sv1', price: 1500 })])),
    read: (m) => text(m.find('pos-search-service-sv1').find('.pos-search__price').element),
    after: '¥1,500',
  },
  {
    piece: 'an open check without a title',
    component: OpenChecksPopover,
    props: { currentId: 'o1', parkingEnabled: true, hasLines: true },
    seed: (m) => m.result('sale.order.list', page([orderRow({ id: 'o3', label: '', provisional_total: 1500 })])),
    read: (m) => text(m.find('pos-parked-o3').find('.pos-checks__name').element),
    after: '¥1,500',
  },
  {
    piece: 'an open check’s amount beside its time',
    component: OpenChecksPopover,
    props: { currentId: 'o1', parkingEnabled: true, hasLines: true },
    seed: (m) => m.result('sale.order.list', page([orderRow({ id: 'o2', label: 'Terrace', provisional_total: 1500, created_at: '2026-10-14T08:30:00' })])),
    read: (m) => text(m.find('pos-parked-o2').find('.pos-checks__meta').element),
    before: '8:30 AM · —',
    after: '8:30 AM · ¥1,500',
  },
];

describe('hub#936: before the business answers its money, the till paints no figure', () => {
  it.each(PIECES)('$piece: a dash, never a figure with two decimals the yen does not have; then the yen', async ({ component, props, seed, read, before = '—', after }) => {
    const m = await mountSale(component, { props, locale: 'en', business: null });
    await m.live();
    await seed?.(m);
    await settle();
    const painted = read(m);
    await m.result('base.business.get', business(JAPANESE));
    await settle();
    expect({ before: painted, after: read(m) }).toEqual({ before, after });
  });
});

describe('what was charged, in the sale’s own currency', () => {
  it('a ticket charged in zlotys prints zlotys while the business is now in euros', async () => {
    const m = await mountSale(ReceiptPaper, {
      props: { sale: saleOut({ currency: 'PLN', currency_decimals: 2 }), letterhead: LETTERHEAD, settings: SETTINGS },
      locale: 'es',
    });
    const totals = m.wrapper.findAll('[data-testid="sale-receipt-total-row"]').map((row) => plain(row.text()));
    expect(totals.length).toBeGreaterThan(0);
    expect(totals.every((row) => row.includes('zł') && !row.includes('€'))).toBe(true);
  });
});
