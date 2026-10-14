// Sales & POS → Sell (WORKBOOK «Vender»; SALE-F01, F05, F09, F14, F16, F17, F21, F22): the catalogue
// and the check side by side (the phone's drawer and its button), every sheet, the charge (the
// checkout sheet) and the document after it. Data only through the operations: the check comes back
// whole from every write and live from `sale.order.get`; the total is the preview's.
import { toast, toastSuccess } from '@erplora/ui/shell';
import { AppPage } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, EMPLOYEE, errorFrame, flush, MANAGER, mountSale, settle } from '../__tests__/mount-sale';
import CartHeading from '../components/pos/CartHeading.vue';
import CartLines from '../components/pos/CartLines.vue';
import DirtyCheckDialog from '../components/pos/DirtyCheckDialog.vue';
import OpenPriceSheet from '../components/pos/OpenPriceSheet.vue';
import ParkSheet from '../components/pos/ParkSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import StaffPicker from '../components/pos/StaffPicker.vue';
import { line, memoryStorage, order, page, preview, product, settings } from '../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';
import { plain } from '../lib/format';
import PosPage from './PosPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toast: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
  toastSuccess: vi.fn(() => Promise.resolve()),
}));
// The other workers' pieces, by their contracts: stubbed here.
vi.mock('../components/checkout/CheckoutSheet.vue', async () => {
  const { h } = await import('vue');
  return {
    default: {
      name: 'CheckoutSheet',
      props: { open: Boolean, orderId: String, lineIds: Array, orderVersion: Number, customer: Object, staffId: String },
      emits: ['update:open', 'charged'],
      render: () => h('div', { 'data-testid': 'checkout-stub' }),
    },
  };
});
vi.mock('../components/document/DocumentModal.vue', async () => {
  const { h } = await import('vue');
  return {
    default: {
      name: 'DocumentModal',
      props: { open: Boolean, saleId: String, duplicate: Boolean },
      emits: ['update:open'],
      render: () => h('div', { 'data-testid': 'document-stub' }),
    },
  };
});
vi.mock('../../../customer/frontend/components/CustomerSearch.vue', async () => {
  const { h } = await import('vue');
  return {
    default: {
      name: 'CustomerSearch',
      props: { modelValue: Object, open: Boolean },
      emits: ['update:modelValue', 'update:open'],
      render: () => h('button', { 'data-testid': 'customer-stub' }),
    },
  };
});

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(toast).mockClear();
  vi.mocked(toastSuccess).mockClear();
});

const CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: 'p1' })] });
const TWO = order({ id: 'o1', version: 2, lines: [line({ id: 'l1' }), line({ id: 'l2', product_id: 'p2', name: 'Tea' })] });
const LUCIA = {
  customer_id: 'c1',
  customer_name: 'Lucía',
  customer_tax_id: '',
  customer_address: '',
  customer_country: 'ES',
};

async function setup(options: { settings?: Parameters<typeof settings>[0]; session?: typeof MANAGER; locale?: 'en' | 'es'; ready?: boolean } = {}) {
  const m = await mountSale(PosPage, { session: options.session, locale: options.locale });
  await m.live();
  if (options.ready !== false) await m.result('sale.pos_settings.get', settings(options.settings));
  const component = <T>(c: T) => m.wrapper.findComponent(c as never);
  const writes = () => m.sent().filter((c) => c.method === 'POST').map((c) => [c.path, c.body]);
  /** Every POST answers `body`. */
  const reply = (body: unknown) => m.net.onApi(() => Response.json(body));
  async function addProduct(id = 'p1', answer = CHECK) {
    reply(answer);
    m.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id }));
    await settle();
    await m.reopen();
  }
  return { ...m, component, writes, reply, addProduct };
}

describe('PosPage: the screen', () => {
  it('is «Sales & POS · Sell» with the app’s tabs, once the till settings are read', async () => {
    const s = await setup({ ready: false });
    expect(s.params('sale.pos_settings.get')).toEqual([{}]);
    expect(s.find('pos-loading').exists()).toBe(true);
    const appPage = s.wrapper.findComponent(AppPage);
    expect(appPage.props('title')).toBe('Sales & POS');
    expect((appPage.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['pos', 'sales', 'quick_notes', 'departments', 'settings']);
    await s.result('sale.pos_settings.get', settings());
    expect(s.find('pos-loading').exists()).toBe(false);
    expect(s.wrapper.findComponent(PosCatalog).exists()).toBe(true);
    expect(s.wrapper.findComponent(PosCart).exists()).toBe(true);
  });

  it('the settings that cannot be read say so with «Retry»; an inactive app says it is off', async () => {
    const s = await setup({ ready: false, locale: 'es' });
    s.net.lastStream().push(errorFrame(s.subId('sale.pos_settings.get'), 'internal_error'));
    await s.reopen();
    expect(s.find('pos-load-error').text()).toContain('Error cargando el TPV');
    expect(s.find('pos-load-retry').exists()).toBe(true);
    const off = await setup({ ready: false, locale: 'es' });
    off.net.lastStream().push(errorFrame(off.subId('sale.pos_settings.get'), 'app_inactive'));
    await off.reopen();
    expect(off.find('pos-load-error').text()).toContain('Esta app no está activa en este negocio.');
  });

  it('counts the other open checks on the receipt icon', async () => {
    const s = await setup();
    expect(s.params('sale.order.list')).toEqual([{ status: 'open', limit: 1, offset: 0 }]);
    await s.result('sale.order.list', page([], 3, 1));
    expect(s.wrapper.findComponent(PosCart).props('openChecks')).toBe(3);
  });
});

describe('PosPage: selling', () => {
  it('a tap opens the check, which is then followed live and valued by the server', async () => {
    const s = await setup();
    await s.addProduct();
    expect(s.writes()).toEqual([['/api/sale/orders', { lines: [{ product_id: 'p1' }] }]]);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o1' }]);
    expect(s.params('sale.checkout.preview')).toEqual([{ order_id: 'o1' }]);
    await s.result('sale.checkout.preview', preview({ total: 150 }));
    expect(plain(s.find('pos-total').text())).toBe('€1.50');
    expect(s.wrapper.findComponent(CartLines).props('lines')).toEqual(CHECK.lines);
  });

  it('a reload comes back to the check the device had', async () => {
    localStorage.setItem(CURRENT_CHECK_KEY, 'o5');
    const s = await setup();
    await s.reopen();
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o5' }]);
    expect(s.sent().some((c) => c.path === '/api/customer/orders/customer' && c.query.order_id === 'o5')).toBe(true);
  });

  it('the chosen professional seals the next lines; the chip says who', async () => {
    const s = await setup();
    await click(s.find('pos-staff-chip').element);
    await settle();
    s.wrapper.findComponent(StaffPicker).vm.$emit('choose', { id: 's1', name: 'Marta' });
    await settle();
    expect(s.wrapper.findComponent(CartHeading).props()).toMatchObject({ staffId: 's1', staffName: 'Marta' });
    await s.addProduct();
    expect(s.writes()[0]).toEqual(['/api/sale/orders', { lines: [{ product_id: 'p1', staff_id: 's1' }] }]);
  });

  it('a customer chosen with a check open is linked to it', async () => {
    const s = await setup();
    await s.addProduct();
    s.reply({ order_id: 'o1', customer_id: 'c1' });
    s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', LUCIA);
    await settle();
    expect(s.writes().at(-1)).toEqual(['/api/customer/orders/link', { order_id: 'o1', customer_id: 'c1' }]);
    expect(s.wrapper.findComponent(CartHeading).props('customerName')).toBe('Lucía');
  });

  it('a customer chosen before the first line is linked when the check opens', async () => {
    const s = await setup();
    s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', LUCIA);
    await settle();
    expect(s.writes()).toEqual([]);
    await s.addProduct();
    expect(s.writes().map((w) => w[0])).toEqual(['/api/sale/orders', '/api/customer/orders/link']);
  });
});

describe('PosPage: open price', () => {
  it('without the permission the tile says a manager has to do it', async () => {
    const s = await setup({ session: EMPLOYEE });
    s.wrapper.findComponent(PosCatalog).vm.$emit('openPrice');
    await settle();
    expect(toast).toHaveBeenCalledWith('A manager has to do it', 'warning');
    expect(s.wrapper.findComponent(OpenPriceSheet).props('open')).toBe(false);
  });

  it('with it, the sheet adds an open-price line and closes', async () => {
    const s = await setup();
    s.wrapper.findComponent(PosCatalog).vm.$emit('openPrice');
    await settle();
    expect(s.wrapper.findComponent(OpenPriceSheet).props('open')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(OpenPriceSheet).vm.$emit('add', { unit_price: 300, department_id: 'd1', name: 'Fruit' });
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { open_lines: [{ unit_price: 300, department_id: 'd1', name: 'Fruit' }] }]]);
    expect(s.wrapper.findComponent(OpenPriceSheet).props('open')).toBe(false);
  });
});

describe('PosPage: charging', () => {
  it('a business that requires a customer asks for one instead of charging', async () => {
    const s = await setup({ settings: { require_customer: true }, locale: 'es' });
    await s.addProduct();
    await click(s.find('pos-charge').element);
    expect(toast).toHaveBeenCalledWith('Este negocio exige un cliente en cada venta. Elige uno para seguir con el cobro.', 'warning');
    expect(s.wrapper.findComponent({ name: 'CustomerSearch' }).props('open')).toBe(true);
    expect(s.wrapper.findComponent({ name: 'CheckoutSheet' }).props('open')).toBe(false);
  });

  it('«Charge» opens the checkout with the check, its version, the marked lines, the customer and who serves', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    s.wrapper.findComponent(CartLines).vm.$emit('mark', TWO.lines[1]);
    await settle();
    await click(s.find('pos-charge').element);
    expect(s.wrapper.findComponent({ name: 'CheckoutSheet' }).props()).toMatchObject({
      open: true,
      orderId: 'o1',
      orderVersion: 2,
      lineIds: ['l2'],
      customer: null,
      staffId: null,
    });
  });

  it('a whole charge empties the screen and opens the sale’s document (not a duplicate)', async () => {
    const s = await setup();
    await s.addProduct();
    await click(s.find('pos-charge').element);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-1' });
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(s.wrapper.findComponent(CartLines).props('lines')).toEqual([]);
    expect(s.wrapper.findComponent({ name: 'DocumentModal' }).props()).toMatchObject({ open: true, saleId: 'sale-1', duplicate: false });
  });

  it('a partial charge keeps the check and drops the marks', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    s.wrapper.findComponent(CartLines).vm.$emit('mark', TWO.lines[0]);
    await settle();
    await click(s.find('pos-charge').element);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-2' });
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.wrapper.findComponent(CartLines).props('marks')).toEqual([]);
    expect(s.wrapper.findComponent({ name: 'DocumentModal' }).props('open')).toBe(false);
  });
});

describe('PosPage: parking and switching', () => {
  it('parks under a title: the screen empties and says so', async () => {
    const s = await setup();
    await s.addProduct();
    await click(s.find('pos-park').element);
    expect(s.wrapper.findComponent(ParkSheet).props('open')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(ParkSheet).vm.$emit('park', 'Ana');
    await settle();
    expect(s.writes().at(-1)).toEqual(['/api/sale/orders/set_label', { order_id: 'o1', label: 'Ana' }]);
    expect(toastSuccess).toHaveBeenCalledWith('Parked as “Ana”');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(s.wrapper.findComponent(ParkSheet).props('open')).toBe(false);
  });

  it('resuming another check with lines on screen asks first; «Park it and open» parks and switches', async () => {
    const s = await setup();
    await s.addProduct();
    s.wrapper.findComponent(PosCart).vm.$emit('resume', { id: 'o2', label: 'Table 2' });
    await settle();
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(true);
    s.reply(CHECK);
    s.wrapper.findComponent(DirtyCheckDialog).vm.$emit('choose', 'park');
    await settle();
    await flush();
    expect(s.writes().find((w) => w[0] === '/api/sale/orders/set_label')?.[1]).toMatchObject({ order_id: 'o1' });
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o2');
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(false);
  });

  it('with nothing on screen, a check is resumed straight away', async () => {
    const s = await setup();
    s.wrapper.findComponent(PosCart).vm.$emit('resume', { id: 'o2', label: '' });
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o2');
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(false);
  });
});

describe('PosPage: the phone', () => {
  it('the cart button carries the count and the total, and opens the drawer', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    await s.result('sale.checkout.preview', preview({ total: 300 }));
    const fab = s.find('pos-cart-fab');
    expect(fab.attributes('aria-label')).toBe('Open cart, 2 items, total €3.00');
    await click(fab.element);
    expect(s.find('pos-till').classes()).toContain('pos-till--cart-open');
    await click(s.find('pos-cart-backdrop').element);
    expect(s.find('pos-till').classes()).not.toContain('pos-till--cart-open');
  });
});
