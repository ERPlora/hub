// The charge sheet the till opens with «Charge» (WORKBOOK «Pantallas · Cobro»):
//   <CheckoutSheet v-model:open="charging" :order-id :line-ids :order-version :customer :staff-id @charged />
// A sheet over the till; nothing is read while it is closed; each opening is a new attempt (its own key);
// the ✕, the backdrop and Escape close it, never while charging; a charge closes it and hands the sale
// to the till (also when the lost answer's lookup found it).
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { click, flush, mountSale, resultFrame } from '../../__tests__/mount-sale';
import type { CompleteIn, PaymentMethodOut, PreviewOut, SaleOut } from '../../operations';
import { ionModalStubOf } from '../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub';
import CheckoutPanel from './CheckoutPanel.vue';
import CheckoutSheet from './CheckoutSheet.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toast: vi.fn(() => Promise.resolve()),
}));
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
  breakdown: [],
  lines: [],
  cash_limit: 100000,
  ticket_limit: 300000,
};
const CARD: PaymentMethodOut = { id: 'm-card', name: 'card', display_name: 'Card', type: 'card', sort_order: 0, requires_change: false, allowed: true };
const SALE = { id: 's1', number: '20261014-0001', total: 1000, already: false } as SaleOut;
const OPS = ['sale.checkout.preview', 'sale.payment_method.list', 'sale.pos_settings.get'] as const;

async function setup() {
  const m = await mountSale(CheckoutSheet, {
    props: { open: false, orderId: 'o1', lineIds: [], orderVersion: 3, customer: null, staffId: null },
  });
  await m.wrapper.setProps({ 'onUpdate:open': (open: boolean) => m.wrapper.setProps({ open }) });
  const modal = () => m.find('sale-checkout-modal');
  const panel = () => m.wrapper.findComponent(CheckoutPanel);
  const subscribed = () => OPS.flatMap((op) => m.client.stream.subscriptions(op));
  async function open() {
    await m.wrapper.setProps({ open: true });
    await flush();
  }
  /** Opens it and gives it a total and a card to charge with. */
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
    ] as const) {
      call.push(resultFrame(m.client.stream.subscriptions(op)[0].id, data, 1));
    }
    await flush();
  }
  const keys = () => m.sent().filter((c) => c.method === 'POST').map((c) => (c.body as CompleteIn).idempotency_key);
  return { ...m, modal, panel, subscribed, open, openReady, keys };
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

  it('a charge hands the sale to the till and closes; then nothing is read any more', async () => {
    const s = await setup();
    await s.openReady();
    s.answer(200, SALE);
    await click(s.find('sale-checkout-confirm').element);
    expect(s.wrapper.emitted('charged')).toEqual([[SALE]]);
    expect(s.wrapper.emitted('update:open')?.at(-1)).toEqual([false]);
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
