// Sales & POS → Sell (WORKBOOK «Vender»): the screen, selling, the charge (the checkout sheet) and the document after
// it, a check joined with another one and the round sent to the kitchen; the other parts of the screen have their own
// `PosPage.<part>.test.ts`. Data only through the operations: the check comes back whole from every write and live
// from `sale.order.get`; the total is the preview's.
import { toast, toastError, toastInfo, toastSuccess, toastWarning } from '@erplora/ui/shell';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { click, errorFrame, MANAGER, settle } from '../__tests__/mount-sale';
import { CHECK, freshEachTest, LUCIA, setup, TWO } from '../__tests__/pos-page';
import CartHeading from '../components/pos/CartHeading.vue';
import CartLines from '../components/pos/CartLines.vue';
import ParkSheet from '../components/pos/ParkSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import PrebillModal from '../components/pos/PrebillModal.vue';
import StaffPicker from '../components/pos/StaffPicker.vue';
import { line, memoryStorage, order, page, preview, refused, settings } from '../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';
import { plain } from '../lib/format';

freshEachTest();

describe('PosPage: the screen', () => {
  it('is «Sales & POS · Sell» with the app’s tabs, once the till settings are read', async () => {
    const s = await setup({ ready: false });
    expect(s.params('sale.pos_settings.get')).toEqual([{}]);
    expect(s.find('pos-loading').exists()).toBe(true);
    const appPage = s.wrapper.findComponent(AppPage);
    expect(appPage.props('title')).toBe('Sales & POS');
    expect((appPage.props('tabs') as Array<{ id: string }>).map((tab) => tab.id)).toEqual(['pos', 'sales', 'quick-notes', 'departments', 'settings']);
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

/** A check with a line whose valuation the server refused (no tax rule applies to it). */
async function refusedCheck() {
  const s = await setup();
  await s.addProduct();
  s.net.lastStream().push(errorFrame(s.subId('sale.checkout.preview'), 'sale.no_tax_rule'));
  await s.reopen();
  return s;
}

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

  it('a valuation refusal says why instead of an endless dash, and the next valuation clears it', async () => {
    const s = await refusedCheck();
    expect(s.find('pos-total').text()).toBe('—');
    expect(s.find('pos-preview-error').text()).toContain('msg sale.no_tax_rule');
    await s.result('sale.checkout.preview', preview({ total: 150 }));
    expect(s.find('pos-preview-error').exists()).toBe(false);
    expect(plain(s.find('pos-total').text())).toBe('€1.50');
  });

  it('a refused check that is parked leaves no reason behind on the empty till', async () => {
    const s = await refusedCheck();
    expect(s.find('pos-preview-error').exists()).toBe(true);
    await click(s.find('pos-park').element);
    s.reply(CHECK);
    s.wrapper.findComponent(ParkSheet).vm.$emit('park', 'Ana');
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(s.find('pos-total').exists()).toBe(true);
    expect(s.find('pos-preview-error').exists()).toBe(false);
  });

  it('a reload comes back to the check the device had', async () => {
    localStorage.setItem(CURRENT_CHECK_KEY, 'o5');
    const s = await setup();
    await s.reopen();
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o5' }]);
    expect(s.sent().some((c) => c.path === '/api/customer/orders/customer' && c.query.order_id === 'o5')).toBe(true);
  });

  it('the chosen professional opens the check and seals the next lines; the chip says who', async () => {
    const s = await setup();
    await click(s.find('pos-staff-chip').element);
    await settle();
    s.wrapper.findComponent(StaffPicker).vm.$emit('choose', { id: 's1', name: 'Marta' });
    await settle();
    expect(s.wrapper.findComponent(CartHeading).props()).toMatchObject({ staffId: 's1', staffName: 'Marta' });
    await s.addProduct();
    expect(s.writes()[0]).toEqual(['/api/sale/orders', { staff_id: 's1', lines: [{ product_id: 'p1', staff_id: 's1' }] }]);
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

describe('PosPage: charging', () => {
  it('a business that requires a customer asks for one instead of charging', async () => {
    const s = await setup({ settings: { require_customer: true }, locale: 'es' });
    await s.addProduct();
    await click(s.find('pos-charge').element);
    expect(toastWarning).toHaveBeenCalledWith('Este negocio exige un cliente en cada venta. Elige uno para seguir con el cobro.');
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

describe('PosPage: a check joined with another one (TABLE-F16, SALE-F24)', () => {
  it('the check on screen joined from Tables (on this device or another) is not «closed on another device»: the till shows the one that stays, with its customer (hub#459)', async () => {
    const s = await setup();
    await s.addProduct();
    s.reply({ order_id: 'o1', customer_id: 'c1' });
    s.wrapper.findComponent({ name: 'CustomerSearch' }).vm.$emit('update:modelValue', LUCIA);
    await settle();
    expect(s.wrapper.findComponent(CartHeading).props('customerName')).toBe('Lucía');
    // The check that stays has no customer of its own.
    s.reply({ order_id: 'o2', customer_id: null });
    await s.result('sale.order.get', order({ id: 'o1', version: 9, status: 'voided', merged_into_id: 'o2', lines: [] }), { order_id: 'o1' }, 9);
    await settle();
    // The absorbed check's subscription goes after the SDK's 2 s grace on unmounting.
    await s.clock.advance(2000);
    await s.reopen();
    expect(toastError).not.toHaveBeenCalled();
    expect(toastInfo).toHaveBeenCalledWith('That check was joined with another one: the screen shows the joined check.');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o2');
    expect(s.params('sale.order.get')).toEqual([{ order_id: 'o2' }]);
    expect(s.sent().some((c) => c.path === '/api/customer/orders/customer' && c.query.order_id === 'o2')).toBe(true);
    // The absorbed check's customer does not carry over to the one that stays.
    expect(s.wrapper.findComponent(CartHeading).props('customerName')).toBeNull();
  });
});

describe('PosPage: sending the round to the kitchen (SALE-F20, KITCHEN-F18)', () => {
  /** Kitchen is on in this business and the person may send to it. */
  const WITH_KITCHEN = { ...MANAGER, permissions: [...MANAGER.permissions, 'kitchen.add_ticket'], apps: [{ label: 'kitchen', state: 'on' as const }] };
  const SENT = order({ id: 'o1', version: 2, lines: [line({ id: 'l1', product_id: 'p1', round_no: 1, fired_at: '2026-10-20T12:00:00Z' })] });
  const kitchenAnswers = (s: Awaited<ReturnType<typeof setup>>, send: () => Response | Promise<Response>) =>
    s.net.onApi((call) => (call.url.startsWith('/api/kitchen/tickets/send') ? send() : Response.json(SENT)));
  const sends = (s: Awaited<ReturnType<typeof setup>>) => s.sent().filter((c) => c.path === '/api/kitchen/tickets/send').map((c) => c.body);
  const checkout = (s: Awaited<ReturnType<typeof setup>>) => s.wrapper.findComponent({ name: 'CheckoutSheet' });

  it('without Kitchen on (or without the right to send to it) the cart has no «Current order»', async () => {
    for (const session of [MANAGER, { ...WITH_KITCHEN, permissions: MANAGER.permissions }]) {
      vi.stubGlobal('localStorage', memoryStorage());
      const s = await setup({ session });
      expect(s.wrapper.findComponent(PosCart).props('kitchen')).toBe(false);
    }
  });

  it('«Send order» asks Kitchen for the round, rush when armed, and says which order went', async () => {
    const s = await setup({ session: WITH_KITCHEN, locale: 'es' });
    await s.addProduct();
    expect(s.wrapper.findComponent(PosCart).props('kitchen')).toBe(true);
    kitchenAnswers(s, () => Response.json({ id: 't1', round_no: 1 }));
    s.wrapper.findComponent(PosCart).vm.$emit('send', true);
    await settle();
    expect(sends(s)).toEqual([{ order_id: 'o1', priority: 'rush' }]);
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({ message: 'Comanda 1 enviada a cocina.', tone: 'success', position: 'top' });
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a round sent whose sheet did not print says so in words at the top, never the raw reason (KITCHEN-F08, hub#748)', async () => {
    const s = await setup({ session: WITH_KITCHEN, locale: 'es' });
    await s.addProduct();
    kitchenAnswers(s, () => Response.json({ id: 't1', round_no: 2, print_error: 'no printer for usage kitchen' }));
    s.wrapper.findComponent(PosCart).vm.$emit('send', false);
    await settle();
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({
      message: 'Comanda 2 enviada a cocina, pero no se imprimió. Revisa la impresora de cocina en Impresión.',
      tone: 'warning',
      position: 'top',
    });
  });

  it('charging with lines not sent sends them first, then opens the charge', async () => {
    const s = await setup({ session: WITH_KITCHEN });
    await s.addProduct();
    kitchenAnswers(s, () => Response.json({ id: 't1', round_no: 1 }));
    s.wrapper.findComponent(PosCart).vm.$emit('charge');
    await settle();
    expect(sends(s)).toEqual([{ order_id: 'o1', priority: 'normal' }]);
    expect(checkout(s).props('open')).toBe(true);
  });

  it('the round a charge sends is said at the top, clear of the sheet’s keypad, and not at the bottom too (hub#732)', async () => {
    const s = await setup({ session: WITH_KITCHEN, locale: 'es' });
    await s.addProduct();
    kitchenAnswers(s, () => Response.json({ id: 't1', round_no: 1 }));
    s.wrapper.findComponent(PosCart).vm.$emit('charge');
    await settle();
    expect(checkout(s).props('open')).toBe(true);
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({ message: 'Comanda 1 enviada a cocina.', tone: 'success', position: 'top' });
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a round a charge sends whose sheet did not print is said at the top, for just as long (hub#732)', async () => {
    const s = await setup({ session: WITH_KITCHEN, locale: 'es' });
    await s.addProduct();
    kitchenAnswers(s, () => Response.json({ id: 't1', round_no: 2, print_error: 'no printer for usage kitchen' }));
    s.wrapper.findComponent(PosCart).vm.$emit('charge');
    await settle();
    expect(checkout(s).props('open')).toBe(true);
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({
      message: 'Comanda 2 enviada a cocina, pero no se imprimió. Revisa la impresora de cocina en Impresión.',
      tone: 'warning',
      position: 'top',
    });
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  // hub#755: with the send refused the cart stays, and at the bottom the notice would lie over «Charge» for its 4.5 s.
  it('when the round cannot be sent nothing is charged and the till says why at the top, clear of «Charge» (hub#755)', async () => {
    const s = await setup({ session: WITH_KITCHEN });
    await s.addProduct();
    kitchenAnswers(s, () => refused('internal_error', 'The kitchen did not answer.', 500));
    s.wrapper.findComponent(PosCart).vm.$emit('charge');
    await settle();
    expect(checkout(s).props('open')).toBe(false);
    expect(toastError).toHaveBeenCalledTimes(1);
    expect(toastError).toHaveBeenCalledWith('The order could not be sent to the kitchen. Try again.', { position: 'top' });
    expect(toast).not.toHaveBeenCalled();
  });

  it('a «Send order» that cannot be sent says why at the top too, clear of «Charge» (hub#755)', async () => {
    const s = await setup({ session: WITH_KITCHEN, locale: 'es' });
    await s.addProduct();
    kitchenAnswers(s, () => refused('internal_error', 'The kitchen did not answer.', 500));
    s.wrapper.findComponent(PosCart).vm.$emit('send', false);
    await settle();
    expect(toastError).toHaveBeenCalledTimes(1);
    expect(toastError).toHaveBeenCalledWith('No se ha podido enviar la comanda a cocina. Inténtalo de nuevo.', { position: 'top' });
    expect(toast).not.toHaveBeenCalled();
  });

  it('the cart follows the check’s kitchen tickets with Kitchen on and the right to see them (KITCHEN-F19)', async () => {
    const VIEW = { ...MANAGER, permissions: [...MANAGER.permissions, 'kitchen.view_ticket'], apps: [{ label: 'kitchen', state: 'on' as const }] };
    const cases: [typeof MANAGER, boolean][] = [
      [MANAGER, false],
      [{ ...VIEW, apps: [] }, false],
      [{ ...VIEW, apps: [{ label: 'kitchen', state: 'activating' }] }, false],
      [{ ...VIEW, permissions: MANAGER.permissions }, false],
      [VIEW, true],
    ];
    for (const [session, on] of cases) {
      vi.stubGlobal('localStorage', memoryStorage());
      const s = await setup({ session });
      expect(s.wrapper.findComponent(PosCart).props('kitchenTickets')).toBe(on);
    }
  });

  it('a round another device already sent does not stop the charge', async () => {
    const s = await setup({ session: WITH_KITCHEN });
    await s.addProduct();
    kitchenAnswers(s, () => refused('sale.nothing_to_fire', 'There is nothing new to send to the kitchen.'));
    s.wrapper.findComponent(PosCart).vm.$emit('charge');
    await settle();
    expect(checkout(s).props('open')).toBe(true);
  });
});
