// Sales & POS → Sell: another check on the till, parked under a title, resumed or opened by its address.
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { click, flush, settle } from '../__tests__/mount-sale';
import { CHECK, freshEachTest, setup } from '../__tests__/pos-page';
import DirtyCheckDialog from '../components/pos/DirtyCheckDialog.vue';
import ParkSheet from '../components/pos/ParkSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import { line, order, settings } from '../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';

// The checkout sheet, the document window and Customers' search, by their contracts.
vi.mock('../components/checkout/CheckoutSheet.vue', async () => (await import('../__tests__/pos-page-stubs')).CHECKOUT_SHEET);
vi.mock('../components/document/DocumentModal.vue', async () => (await import('../__tests__/pos-page-stubs')).DOCUMENT_MODAL);
vi.mock('../../../customer/frontend/components/CustomerSearch.vue', async () => (await import('../__tests__/pos-page-stubs')).CUSTOMER_SEARCH);

freshEachTest();

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
