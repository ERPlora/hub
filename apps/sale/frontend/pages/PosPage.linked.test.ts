// Sales & POS → Sell: a check opened by its address (/sale/pos?order=<id>), as Appointments' «Charge» does
// (APPOINTMENT-F17, SALE-F26). Until that check is on the till with its customer read, the till says it is opening it
// and shows neither the catalogue nor any other check; one that cannot be opened is said in its place, and «Continue»
// gives the till back as it was. The till entered without an address is not held back.
import { toastError } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, settle } from '../__tests__/mount-sale';
import { freshEachTest, setup } from '../__tests__/pos-page';
import DirtyCheckDialog from '../components/pos/DirtyCheckDialog.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import { line, order, settings } from '../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';

freshEachTest();

const O7 = order({ id: 'o7', label: 'Lucía · APT-20261014-0001', lines: [line({ id: 'l7' })] });
const NO_CUSTOMER = { order_id: 'o7', customer_id: null };
const GONE = 'Esa cuenta ya no está abierta: se cobró, se anuló o no existe.';

/** An answer the test lets go when it wants. */
function held() {
  let release!: (body: unknown) => void;
  const answered = new Promise<Response>((resolve) => (release = (body) => resolve(Response.json(body))));
  return { route: () => answered, release };
}

/** The till on a device that had another check on screen (`o5`), arriving at the address of `o7`. */
async function arrive(answers: Parameters<Awaited<ReturnType<typeof setup>>['answerBy']>[0]) {
  localStorage.setItem(CURRENT_CHECK_KEY, 'o5');
  const s = await setup({ path: '/sale/pos?order=o7', ready: false, locale: 'es' });
  s.answerBy(answers);
  await s.result('sale.pos_settings.get', settings());
  await settle();
  return s;
}

/** What the till shows: that it is opening a check, the catalogue, and the check on screen (`none`: an empty one). */
function shows(s: Awaited<ReturnType<typeof setup>>) {
  const cart = s.wrapper.findComponent(PosCart);
  return {
    opening: s.find('pos-linked-loading').exists(),
    catalogue: s.wrapper.findComponent(PosCatalog).exists(),
    check: cart.exists() ? ((cart.props('order') as { id: string } | null)?.id ?? 'none') : null,
  };
}

describe('PosPage: a check opened by its address (/sale/pos?order=<id>, APPOINTMENT-F17)', () => {
  it('says it is opening the check, with neither the catalogue nor another check, until that check and its customer are read', async () => {
    const detail = held();
    const customer = held();
    const s = await arrive({ '/api/sale/orders/detail': detail.route, '/api/customer/orders/customer': customer.route });
    expect(s.find('pos-linked-loading').text()).toBe('Abriendo la cuenta…');
    expect(shows(s)).toEqual({ opening: true, catalogue: false, check: null });
    detail.release(O7);
    await settle();
    expect(shows(s)).toEqual({ opening: true, catalogue: false, check: null });
    customer.release(NO_CUSTOMER);
    await settle();
    expect(shows(s)).toEqual({ opening: false, catalogue: true, check: 'o7' });
    expect(s.find('pos-line-l7').exists()).toBe(true);
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos');
  });

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

  it('the check already on the till is read again and shown, without holding the till', async () => {
    localStorage.setItem(CURRENT_CHECK_KEY, 'o7');
    const s = await setup({ path: '/sale/pos?order=o7', ready: false });
    s.answerBy({ '/api/sale/orders/detail': [200, O7], '/api/customer/orders/customer': [200, NO_CUSTOMER] });
    await s.result('sale.pos_settings.get', settings());
    await settle();
    expect(s.find('pos-linked-loading').exists()).toBe(false);
    expect(s.wrapper.findComponent(PosCart).props('order')).toMatchObject({ id: 'o7' });
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o7');
  });

  it('a check that is no longer open is said in its place, with nothing to sell on; «Continue» gives the till back as it was', async () => {
    const s = await arrive({ '/api/sale/orders/detail': [200, { ...O7, status: 'completed' }] });
    expect(s.find('pos-linked-error').text()).toContain(GONE);
    expect(shows(s)).toEqual({ opening: false, catalogue: false, check: null });
    expect(toastError).not.toHaveBeenCalled();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o5');
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/pos');
    expect(s.find('pos-linked-action').text()).toBe('Continuar');
    await click(s.find('pos-linked-action').element);
    await settle();
    expect(s.find('pos-linked-error').exists()).toBe(false);
    expect(shows(s)).toMatchObject({ opening: false, catalogue: true });
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o5');
  });

  it('a check that does not exist is said the same way; any other refusal in the server’s words', async () => {
    const missing = await arrive({ '/api/sale/orders/detail': [404, { error: { code: 'sale.order_not_found', message: 'No existe.' } }] });
    expect(missing.find('pos-linked-error').text()).toContain(GONE);
    expect(shows(missing)).toMatchObject({ catalogue: false, check: null });
    const refused = await arrive({ '/api/sale/orders/detail': [403, { error: { code: 'permission_denied', message: 'No puedes ver esa cuenta.' } }] });
    expect(refused.find('pos-linked-error').text()).toContain('No puedes ver esa cuenta.');
    expect(shows(refused)).toMatchObject({ catalogue: false, check: null });
  });

  it('another page’s «order» in its address (a sort, Ionic keeping the till alive behind) opens nothing', async () => {
    const s = await setup({ path: '/sale/sales?order=asc', ready: false });
    s.answer(200, O7);
    await s.result('sale.pos_settings.get', settings());
    await settle();
    expect(s.sent().some((c) => c.path === '/api/sale/orders/detail')).toBe(false);
    expect(s.find('pos-linked-loading').exists()).toBe(false);
    expect(s.router.currentRoute.value.fullPath).toBe('/sale/sales?order=asc');
  });

  it('the till entered without an address is not held back', async () => {
    const s = await setup();
    expect(s.find('pos-linked-loading').exists()).toBe(false);
    expect(s.wrapper.findComponent(PosCatalog).exists()).toBe(true);
    expect(s.wrapper.findComponent(PosCart).exists()).toBe(true);
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

  it('«Cancel» on that question keeps the check on screen and opens nothing', async () => {
    const s = await setup();
    await s.addProduct();
    s.answer(200, O7);
    await s.router.push('/sale/pos?order=o7');
    await settle();
    await settle();
    s.wrapper.findComponent(DirtyCheckDialog).vm.$emit('update:open', false);
    await settle();
    expect(s.wrapper.findComponent(DirtyCheckDialog).props('open')).toBe(false);
    expect(shows(s)).toEqual({ opening: false, catalogue: true, check: 'o1' });
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
  });
});
