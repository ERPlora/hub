// The charge sheet the till opens with «Charge» (WORKBOOK «Pantallas · Cobro»):
//   <CheckoutSheet v-model:open="charging" :order-id :line-ids :order-version :customer :staff-id @charged />
// A sheet over the till; nothing is read while it is closed; each opening is a new attempt (its own key);
// the ✕, the backdrop and Escape close it, never while charging; a charge closes it and hands the sale
// to the till (also when the lost answer's lookup found it).
import { type ActionNotice, connectActionCenter, useActionCenter } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';

import { business, click, flush, ionValue, MANAGER, type MountOptions, mountSale, resultFrame } from '../../__tests__/mount-sale';
import type { CompleteIn, PaymentMethodOut, PreviewOut, SaleOut } from '../../operations';
import { ionModalStubOf } from '../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub';
import CashSessionWindow from './CashSessionWindow.vue';
import CheckoutPanel from './CheckoutPanel.vue';
import CheckoutSheet from './CheckoutSheet.vue';

beforeEach(() => vi.clearAllMocks());

const PREVIEW: PreviewOut = {
  order_id: 'o1',
  order_version: 3,
  lines_count: 1,
  tax_included: true,
  subtotal: 826,
  tax_total: 174,
  discount_amount: 0,
  discount_percent: '0.00',
  ticket_discount_amount: 0,
  gift_total: 0,
  total: 1000,
  operation_total: 1000,
  breakdown: [],
  lines: [],
  cash_limit: 100000,
  ticket_limit: 300000,
  limits_currency: 'EUR',
};
const CARD: PaymentMethodOut = { id: 'm-card', name: 'card', display_name: 'Card', type: 'card', sort_order: 0, requires_change: false, allowed: true };
const SALE = { id: 's1', number: '20261014-0001', total: 1000, already: false } as SaleOut;
const OPS = ['sale.checkout.preview', 'sale.payment_method.list', 'sale.pos_settings.get'] as const;

async function setup(session?: MountOptions['session']) {
  const m = await mountSale(CheckoutSheet, {
    props: { open: false, orderId: 'o1', lineIds: [], orderVersion: 3, customer: null, staffId: null },
    session,
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  const modal = () => m.find('sale-checkout-modal');
  const panel = () => m.wrapper.findComponent(CheckoutPanel);
  const subscribed = () => OPS.flatMap((op) => m.client.stream.subscriptions(op));
  async function open() {
    await m.wrapper.setProps({ open: true });
    await flush();
  }
  /** Opens it and gives it a total, a card to charge with and the business's money (the charge waits for it, hub#921). */
  async function openReady() {
    await open();
    await m.clock.advance(150);
    const call = m.net.lastStream();
    call.push('event: hello\ndata: {"stream":"s-1"}\n\n');
    await flush();
    for (const [op, data] of [
      ['sale.checkout.preview', PREVIEW],
      ['sale.payment_method.list', { rows: [CARD], total: 1, limit: 100, offset: 0 }],
      ['sale.pos_settings.get', { default_document_type: 'ticket' }],
      ['base.business.get', business()],
    ] as const) {
      call.push(resultFrame(m.client.stream.subscriptions(op)[0].id, data, 1));
    }
    await flush();
  }
  const keys = () => m.sent().filter((c) => c.method === 'POST').map((c) => (c.body as CompleteIn).idempotency_key);
  const confirm = () => click(m.find('sale-checkout-confirm').element);
  /** What the till was handed and the sheet's last word on being open. */
  const outcome = () => [m.wrapper.emitted('charged'), m.wrapper.emitted('update:open')?.at(-1)];
  return { ...m, modal, panel, subscribed, open, openReady, keys, confirm, outcome };
}

describe('CheckoutSheet', () => {
  it('closed: nothing shown and nothing read', async () => {
    const s = await setup();
    expect([s.panel().exists(), s.subscribed()]).toEqual([false, []]);
  });

  it('open: the sheet named «Charge», with the check it charges', async () => {
    const s = await setup();
    await s.open();
    expect(s.modal().attributes('aria-label')).toBe('Charge');
    expect(s.panel().props()).toEqual({ orderId: 'o1', lineIds: [], orderVersion: 3, customer: null, staffId: null });
    expect(s.subscribed()).toHaveLength(3);
  });

  it('a charge hands the sale to the till with the lines it charged (none = the whole check) and closes; then nothing is read any more', async () => {
    const s = await setup();
    await s.openReady();
    s.answer(200, SALE);
    await s.confirm();
    expect(s.outcome()).toEqual([[[SALE, []]], [false]]);
    expect(s.panel().exists()).toBe(false);
    await s.clock.advance(2000);
    expect(s.subscribed()).toEqual([]);
  });

  it('each opening is a new attempt, with a key of its own', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'sale.order_changed', message: 'The check changed.' } });
    await s.openReady();
    await click(s.find('sale-checkout-confirm').element);
    await click(s.find('sale-checkout-close').element);
    await s.openReady();
    await click(s.find('sale-checkout-confirm').element);
    const [first, second] = s.keys();
    expect(first).toMatch(/^sale-/);
    expect(second).toMatch(/^sale-/);
    expect(second).not.toBe(first);
  });

  it('the ✕ and the backdrop close it', async () => {
    const s = await setup();
    await s.open();
    await click(s.find('sale-checkout-close').element);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    await s.open();
    expect(ionModalStubOf(s.modal().element).tapBackdrop()).toBe(true);
    await flush();
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
    expect(s.panel().exists()).toBe(false);
  });

  it('while charging nothing closes it', async () => {
    const s = await setup();
    await s.openReady();
    s.net.onApi(() => new Promise<Response>(() => {}));
    await click(s.find('sale-checkout-confirm').element);
    expect(s.modal().attributes('data-backdrop-dismiss')).toBe('false');
    expect((s.find('sale-checkout-close').element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    expect(ionModalStubOf(s.modal().element).tapBackdrop()).toBe(false);
  });
});

describe('CheckoutSheet keeps the screen clear during a charge', () => {
  const notice = (id: string): ActionNotice => ({ id, severity: 'danger', icon: 'ion:warning-outline', label: id, title: id });

  it('a notice that comes while it is open only makes the bell pulse; once closed, the next one comes as a card', async () => {
    const notices = ref<ActionNotice[]>([]);
    const disconnect = connectActionCenter({ notices, failed: ref(false) });
    try {
      const center = useActionCenter();
      const s = await setup();
      await s.open();
      const pulse = center.pulse.value;
      notices.value = [notice('printer.offline')];
      await flush();
      expect(center.arrival.value).toBeUndefined();
      expect(center.pulse.value).not.toBe(pulse);

      await s.wrapper.setProps({ open: false });
      await flush();
      notices.value = [notice('printer.offline'), notice('invoice.blocked')];
      await flush();
      expect(center.arrival.value?.id).toBe('invoice.blocked');
    } finally {
      disconnect();
    }
  });
});

describe('CheckoutSheet: cash with the drawer closed (SALE-F08, CASH_REGISTER-F03)', () => {
  const DRAWER = { ...MANAGER, permissions: [...MANAGER.permissions, 'cash_register.add_session'], apps: [{ label: 'cash_register', state: 'on' as const }] };
  const CLOSED = { error: { code: 'sale.cash_register_closed', message: 'The cash register is closed: open a cash session to charge in cash.' } };

  it('«Open a cash session» opens Cash register’s window over the sheet; with the session open, the same sheet charges', async () => {
    const s = await setup(DRAWER);
    await s.openReady();
    const sales = [Response.json(CLOSED, { status: 409 }), Response.json(SALE)];
    s.net.onApi(({ url }) =>
      new URL(url, 'http://a.localhost').pathname === '/api/sale/sales' ? sales.shift()! : Response.json({ id: 'cs1' }, { status: 201 }),
    );
    await s.confirm();
    expect(s.find('sale-checkout-error').text()).toBe(CLOSED.error.message);

    await click(s.find('sale-checkout-open-drawer').element);
    await vi.waitFor(() => expect(s.inDoc('cash-register-open')).not.toBeNull());
    expect([s.router.currentRoute.value.path, s.wrapper.emitted('update:open')]).toEqual(['/sale/pos', undefined]);

    await ionValue(s.inDoc('cash-register-open-balance'), '100', 'ionInput');
    await click(s.inDoc('cash-register-open-submit'));
    await flush();
    expect(s.sent().at(-1)).toMatchObject({ method: 'POST', path: '/api/cash_register/sessions/open', body: { opening_balance: 10000 } });
    expect([s.find('sale-checkout-error').exists(), s.wrapper.emitted('update:open')]).toEqual([false, undefined]);

    await s.confirm();
    expect(s.outcome()).toEqual([[[SALE, []]], [false]]);
  });

  it('when Cash register’s window cannot load, it goes to Cash register instead and the sheet closes', async () => {
    const s = await setup(DRAWER);
    await s.openReady();
    s.wrapper.findComponent(CashSessionWindow).vm.$emit('unavailable');
    await flush();
    expect(s.router.currentRoute.value.path).toBe('/cash_register/sessions');
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
  });
});
