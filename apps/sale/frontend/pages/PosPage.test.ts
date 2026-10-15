// Sales & POS → Sell (WORKBOOK «Vender»; SALE-F01, F05, F09, F14, F16, F17, F19, F21, F22): the catalogue
// and the check side by side (the phone's drawer and its button), every sheet, the table of the check
// (with Tables on), the charge (the checkout sheet) and the document after it. Data only through the operations: the check comes back
// whole from every write and live from `sale.order.get`; the total is the preview's.
import { toast, toastError, toastSuccess } from '@erplora/ui/shell';
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
import PrebillModal from '../components/pos/PrebillModal.vue';
import ServicePriceSheet from '../components/pos/ServicePriceSheet.vue';
import StaffPicker from '../components/pos/StaffPicker.vue';
import TableButton from '../components/pos/TableButton.vue';
import TablePicker from '../components/pos/TablePicker.vue';
import { line, memoryStorage, order, page, preview, product, service, settings } from '../components/pos/__tests__/fixtures';
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
  vi.mocked(toastError).mockClear();
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

async function setup(
  options: { settings?: Parameters<typeof settings>[0]; session?: typeof MANAGER; locale?: 'en' | 'es'; ready?: boolean; path?: string } = {},
) {
  const m = await mountSale(PosPage, { session: options.session, locale: options.locale, path: options.path });
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

  it('the till shows the person; the charge keeps the fiscal recipient (the company)', async () => {
    const s = await setup();
    await s.addProduct();
    s.reply({ order_id: 'o1', customer_id: 'c1' });
    const company = { ...LUCIA, customer_name: 'Ruiz Peluqueros SL', display_name: 'Lucía' };
    s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', company);
    await settle();
    expect(s.wrapper.findComponent(CartHeading).props('customerName')).toBe('Lucía');
    s.wrapper.findComponent(PosCart).vm.$emit('prebill');
    await settle();
    expect(s.wrapper.findComponent(PrebillModal).props('customerName')).toBe('Lucía');
    await click(s.find('pos-charge').element);
    expect(s.wrapper.findComponent({ name: 'CheckoutSheet' }).props('customer')).toEqual(company);
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

describe('PosPage: services of Services (SALE-F38)', () => {
  /** Services is on in this business and the person reads its catalog. */
  const WITH_SERVICES = { ...MANAGER, permissions: [...MANAGER.permissions, 'service.view_service'], apps: [{ label: 'service', state: 'on' as const }] };
  const SERVICE_CHECK = order({ id: 'o1', version: 1, lines: [line({ id: 'l1', product_id: null, service_id: 'sv1', is_service: true })] });

  it('the catalogue offers the services with Services on, the setting on and the permission to read them', async () => {
    const on = await setup({ session: WITH_SERVICES });
    expect(on.wrapper.findComponent(PosCatalog).props('showServices')).toBe(true);
    const hidden = await setup({ session: WITH_SERVICES, settings: { show_services: false } });
    expect(hidden.wrapper.findComponent(PosCatalog).props('showServices')).toBe(false);
    const off = await setup({ session: { ...WITH_SERVICES, apps: [] } });
    expect(off.wrapper.findComponent(PosCatalog).props('showServices')).toBe(false);
    const blind = await setup({ session: { ...WITH_SERVICES, permissions: MANAGER.permissions } });
    expect(blind.wrapper.findComponent(PosCatalog).props('showServices')).toBe(false);
  });

  it('a fixed-price service opens the check with it', async () => {
    const s = await setup({ session: WITH_SERVICES });
    s.reply(SERVICE_CHECK);
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', service({ id: 'sv1' }));
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { service_lines: [{ service_id: 'sv1' }] }]]);
  });

  it('a service without a fixed price asks its amount first, then adds it and closes the sheet', async () => {
    const s = await setup({ session: WITH_SERVICES });
    const colour = service({ id: 'sv2', name: 'Color', pricing_type: 'from', price: 6500 });
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', colour);
    await settle();
    const sheet = s.wrapper.findComponent(ServicePriceSheet);
    expect(sheet.props()).toMatchObject({ open: true, service: colour });
    expect(s.writes()).toEqual([]);
    s.reply(SERVICE_CHECK);
    sheet.vm.$emit('add', 7000);
    await settle();
    expect(s.writes()).toEqual([['/api/sale/orders', { service_lines: [{ service_id: 'sv2', unit_price: 7000 }] }]]);
    expect(s.wrapper.findComponent(ServicePriceSheet).props('open')).toBe(false);
  });

  it('a refused amount stays in the sheet in the server’s words', async () => {
    const s = await setup({ session: WITH_SERVICES });
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', service({ id: 'sv2', pricing_type: 'variable' }));
    await settle();
    s.net.onApi(() => Response.json({ error: { code: 'sale.service_price_out_of_range', message: 'Out of range.' } }, { status: 409 }));
    s.wrapper.findComponent(ServicePriceSheet).vm.$emit('add', 100);
    await settle();
    expect(s.wrapper.findComponent(ServicePriceSheet).props()).toMatchObject({ open: true, error: 'Out of range.' });
  });

  it('a refused fixed-price service says why in a toast', async () => {
    const s = await setup({ session: WITH_SERVICES });
    s.net.onApi(() => Response.json({ error: { code: 'sale.service_not_available', message: 'Not offered.' } }, { status: 409 }));
    s.wrapper.findComponent(PosCatalog).vm.$emit('service', service({ id: 'sv1' }));
    await settle();
    expect(toastError).toHaveBeenCalledWith('Not offered.');
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
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-1' }, []);
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(s.wrapper.findComponent(CartLines).props('lines')).toEqual([]);
    expect(s.wrapper.findComponent({ name: 'DocumentModal' }).props()).toMatchObject({ open: true, saleId: 'sale-1', duplicate: false });
  });

  it('a partial charge keeps the check, drops the marks and opens that sale’s document too', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    s.wrapper.findComponent(CartLines).vm.$emit('mark', TWO.lines[0]);
    await settle();
    await click(s.find('pos-charge').element);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-2' }, ['l1']);
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.wrapper.findComponent(CartLines).props('marks')).toEqual([]);
    expect(s.wrapper.findComponent({ name: 'DocumentModal' }).props()).toMatchObject({ open: true, saleId: 'sale-2', duplicate: false });
  });

  it('whole or partial is what was charged, not the marks at the answer (a live update may have dropped them)', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    s.wrapper.findComponent(CartLines).vm.$emit('mark', TWO.lines[0]);
    await settle();
    await click(s.find('pos-charge').element);
    // The live check drops the mark before the charge answers.
    s.wrapper.findComponent(CartLines).vm.$emit('mark', TWO.lines[0]);
    await settle();
    expect(s.wrapper.findComponent(CartLines).props('marks')).toEqual([]);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-3' }, ['l1']);
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
  });

  it('every line of the check charged on its marks is a whole charge', async () => {
    const s = await setup();
    await s.addProduct('p1', TWO);
    await click(s.find('pos-charge').element);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-4' }, ['l1', 'l2']);
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
  });

  it('a check closed elsewhere while the sheet is open stays until the sheet closes, then the screen lets it go', async () => {
    const s = await setup();
    await s.addProduct();
    await click(s.find('pos-charge').element);
    await s.result('sale.order.get', order({ id: 'o1', version: 9, status: 'completed', lines: [] }), { order_id: 'o1' }, 9);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(toastError).not.toHaveBeenCalled();
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('update:open', false);
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(toastError).toHaveBeenCalledWith('That check was closed on another device: the screen starts a new one.');
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

describe('PosPage: a check opened by its address (/sale/pos?order=<id>, APPOINTMENT-F17)', () => {
  const O7 = order({ id: 'o7', label: 'Lucía · APT-20261014-0001', lines: [line({ id: 'l7' })] });

  it('opens that check on the till and leaves the address clean', async () => {
    const s = await setup({ path: '/sale/pos?order=o7', ready: false });
    s.answer(200, O7);
    await s.result('sale.pos_settings.get', settings());
    await settle();
    await s.reopen();
    expect(s.sent().some((c) => c.path === '/api/sale/orders/detail' && c.query.order_id === 'o7')).toBe(true);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o7');
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o7' }]);
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos');
    expect(toastError).not.toHaveBeenCalled();
  });

  it('a check that is no longer open (or does not exist) is said, and the till carries on as it was', async () => {
    localStorage.setItem(CURRENT_CHECK_KEY, 'o5');
    const s = await setup({ path: '/sale/pos?order=o7', ready: false, locale: 'es' });
    s.answer(200, { ...O7, status: 'completed' });
    await s.result('sale.pos_settings.get', settings());
    await settle();
    expect(toastError).toHaveBeenCalledWith('Esa cuenta ya no está abierta (se cobró, se anuló o no existe): el TPV sigue como estaba.');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o5');
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos');
    vi.mocked(toastError).mockClear();
    const missing = await setup({ path: '/sale/pos?order=o8', ready: false });
    missing.answer(404, { error: { code: 'sale.order_not_found', message: 'That check does not exist.' } });
    await missing.result('sale.pos_settings.get', settings());
    await settle();
    expect(toastError).toHaveBeenCalledWith('That check is not open any more (charged, voided or gone): the till carries on as it was.');
  });

  it('another page’s «order» in its address (a sort, Ionic keeping the till alive behind) opens nothing', async () => {
    const s = await setup({ path: '/sale/sales?order=asc', ready: false });
    s.answer(200, O7);
    await s.result('sale.pos_settings.get', settings());
    await settle();
    expect(s.sent().some((c) => c.path === '/api/sale/orders/detail')).toBe(false);
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/sales?order=asc');
  });

  it('with another check with lines on screen, asks first, as resuming one does', async () => {
    const s = await setup();
    await s.addProduct();
    s.answer(200, O7);
    await s.router.push('/sale/pos?order=o7');
    await settle();
    await settle();
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(true);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
  });
});

describe('PosPage: the table of the check (SALE-F19)', () => {
  const TABLE_PERMISSIONS = ['table.view_table', 'table.add_session', 'table.view_session', 'table.change_session'];
  /** Tables is on in this business and the person sees the tables, seats and follows the table checks. */
  const WITH_TABLES = { ...MANAGER, permissions: [...MANAGER.permissions, ...TABLE_PERMISSIONS], apps: [{ label: 'table', state: 'on' as const }] };
  const without = (permission: string) => ({ ...WITH_TABLES, permissions: WITH_TABLES.permissions.filter((p) => p !== permission) });
  const TABLE_OPS = ['table.session.by_order', 'table.table.list', 'table.floor.status'] as const;
  const seatOf = (over: Record<string, unknown> = {}) => ({
    id: 's1',
    table_id: 't4',
    table_number: '4',
    zone_id: 'z1',
    zone_name: 'Terrace',
    order_id: 'o1',
    guests_count: 4,
    status: 'open',
    waiter_id: 'u1',
    waiter_name: 'Ana',
    opened_at: '2026-10-15T12:00:00+02:00',
    closed_at: null,
    notes: '',
    split_from_id: null,
    transferred_from_id: null,
    merged_into_id: null,
    paid_total: null,
    customer_id: null,
    customer_name: null,
    ...over,
  });

  it('without Tables on, or without the right to see the tables or seat, nothing about tables shows nor is followed', async () => {
    const sessions = [
      { ...WITH_TABLES, apps: [] },
      { ...WITH_TABLES, apps: [{ label: 'table', state: 'activating' as const }] },
      without('table.view_table'),
      without('table.add_session'),
    ];
    for (const session of sessions) {
      const s = await setup({ session });
      await s.addProduct();
      expect(s.find('pos-table-trigger').exists()).toBe(false);
      expect(s.find('pos-table-chip').exists()).toBe(false);
      for (const op of TABLE_OPS) expect(s.params(op), op).toEqual([]);
    }
  });

  it('with Tables on, the button is in the check’s bar; the check’s table is followed once there is a check', async () => {
    const s = await setup({ session: WITH_TABLES, locale: 'es' });
    expect(s.find('pos-table-trigger').attributes('aria-label')).toBe('Asignar mesa');
    for (const op of TABLE_OPS) expect(s.params(op), op).toEqual([]);
    await s.addProduct();
    expect(s.params('table.session.by_order')).toEqual([{ order_id: 'o1' }]);
    await s.result('table.session.by_order', { rows: [seatOf()] });
    expect(s.wrapper.findComponent(TableButton).props('tableNumber')).toBe('4');
    expect(s.find('pos-table-chip').text()).toBe('Mesa 4');
    expect(s.find('pos-check-context-empty').exists()).toBe(false);
  });

  it('without the right to see the table checks, the button stays but no table is followed', async () => {
    const s = await setup({ session: without('table.view_session') });
    await s.addProduct();
    expect(s.find('pos-table-trigger').exists()).toBe(true);
    expect(s.params('table.session.by_order')).toEqual([]);
  });

  it('the button opens «Choose table» with the check, its seat and its parked table check', async () => {
    const s = await setup({ session: WITH_TABLES });
    await s.addProduct();
    const seat = seatOf();
    await s.result('table.session.by_order', { rows: [seat] });
    expect(s.wrapper.findComponent(TablePicker).exists()).toBe(false);
    await click(s.find('pos-table-trigger').element);
    expect(s.wrapper.findComponent(TablePicker).props()).toMatchObject({ open: true, orderId: 'o1', seat, parked: null });
    await s.reopen();
    expect(s.params('table.table.list')).toHaveLength(1);
  });

  it('seated with no check yet: the check Tables opened goes on the till, with the customer already chosen', async () => {
    const s = await setup({ session: WITH_TABLES });
    s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', LUCIA);
    await settle();
    await click(s.find('pos-table-trigger').element);
    expect(s.wrapper.findComponent(TablePicker).props('orderId')).toBeNull();
    s.reply({ order_id: 'o9', customer_id: 'c1' });
    s.wrapper.findComponent(TablePicker).vm.$emit('seated', seatOf({ order_id: 'o9' }));
    await settle();
    await s.reopen();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o9');
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o9' }]);
    expect(s.params('table.session.by_order')).toEqual([{ order_id: 'o9' }]);
    expect(s.writes()).toEqual([['/api/customer/orders/link', { order_id: 'o9', customer_id: 'c1' }]]);
    expect(s.wrapper.findComponent(CartHeading).props('customerName')).toBe('Lucía');
  });

  it('seated with the check on screen: the till keeps it', async () => {
    const s = await setup({ session: WITH_TABLES });
    await s.addProduct();
    await click(s.find('pos-table-trigger').element);
    s.wrapper.findComponent(TablePicker).vm.$emit('seated', seatOf());
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.writes()).toEqual([['/api/sale/orders', { lines: [{ product_id: 'p1' }] }]]);
  });

  it('a charged check takes its table off the screen', async () => {
    const s = await setup({ session: WITH_TABLES });
    await s.addProduct();
    await s.result('table.session.by_order', { rows: [seatOf()] });
    expect(s.find('pos-table-chip').exists()).toBe(true);
    await click(s.find('pos-charge').element);
    s.wrapper.findComponent({ name: 'CheckoutSheet' }).vm.$emit('charged', { id: 'sale-1' }, []);
    await settle();
    expect(s.find('pos-table-chip').exists()).toBe(false);
    expect(s.wrapper.findComponent(TableButton).props('tableNumber')).toBeNull();
  });
});

describe('PosPage: the phone', () => {
  it('the open drawer is a modal dialog named «Check», and Escape closes it', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const s = await setup({ locale: 'es' });
    const drawer = () => s.find('pos-cart-drawer');
    expect(drawer().attributes('role')).toBeUndefined();
    await click(s.find('pos-cart-fab').element);
    expect(drawer().attributes()).toMatchObject({ role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Cuenta', tabindex: '-1' });
    s.find('pos-till').element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await settle();
    expect(s.find('pos-till').classes()).not.toContain('pos-till--cart-open');
    expect(drawer().attributes('role')).toBeUndefined();
  });


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
