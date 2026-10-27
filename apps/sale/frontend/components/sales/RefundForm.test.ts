// The body of the Refund window (SALE-F31; the old `erp-sale-refund`): what can go back comes from
// `sale.refund.options` (live); the window proposes a full refund split by tender, «What goes back»
// re-proposes the marked lines' share, «Refund everything» puts the full proposal back, every amount can
// be edited, and the button «Refund <amount>» says why it cannot go yet (aria-disabled, never a dead
// tap). `sale.sale.refund` carries the attempt key born when the window opened, the same on a retry, so
// a lost answer never refunds twice. A refusal is read inside the window, which stays open. The cashier, who may not
// refund, is asked for a manager's approval (BASE-F84): approved with the manager's PIN, the very same refund goes once;
// «Cancel» on the approval leaves its refusal inside the window.
import { InlineFeedback } from '@erplora/ui/components';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { approvalDialog, approvalSettled, asksApproval, CANCELLED } from '../../__tests__/approval-dialog';
import { click, EMPLOYEE, errorFrame, flush, ionValue, mountSale } from '../../__tests__/mount-sale';
import { plain } from '../../lib/format';
import type { LineOption, RefundOptionsOut, TenderOption } from '../../operations';
import RefundForm from './RefundForm.vue';
import RefundLines from './RefundLines.vue';
import RefundTenderCard from './RefundTenderCard.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  const { modalControllerStub } = await import('../../__tests__/approval-dialog');
  const ionic = await importOriginal<typeof import('@ionic/vue')>();
  return { ...ionic, IonModal: IonModalStub, modalController: modalControllerStub(ionic.modalController) };
});
vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toastSuccess: vi.fn(() => Promise.resolve()),
  toastError: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => {
  vi.mocked(toastSuccess).mockClear();
  vi.mocked(toastError).mockClear();
  approvalDialog.reset();
});

const tender = (id: string, over: Partial<TenderOption> = {}): TenderOption => ({
  payment_id: id,
  position: 1,
  method_id: `m-${id}`,
  method_name: 'Cash',
  method_type: 'cash',
  charged: 1000,
  refunded: 0,
  remaining: 1000,
  refundable: true,
  reason: '',
  ...over,
});
const line = (id: string, over: Partial<LineOption> = {}): LineOption => ({
  line_id: id,
  name: 'Café',
  unit: 'ud',
  quantity: '1.000',
  returned: '0.000',
  left: '1.000',
  line_total: 300,
  is_gift: false,
  paid_by_voucher: false,
  voucher_name: '',
  ...over,
});
const options = (over: Partial<RefundOptionsOut> = {}): RefundOptionsOut => ({
  sale_id: 's1',
  number: '20261014-0007',
  status: 'completed',
  currency: 'EUR',
  currency_decimals: 2,
  total: 1500,
  refunded_total: 0,
  refundable_total: 1500,
  tenders: [tender('p1'), tender('p2', { position: 2, method_name: 'Card', method_type: 'card', charged: 500, remaining: 500 })],
  lines: [line('a'), line('b', { name: 'Croissant', quantity: '3.000', left: '3.000', line_total: 1200 })],
  ...over,
});

const prop = (el: Element, name: string): unknown => (el as unknown as Record<string, unknown>)[name];
/** What a person reads in `el`: its texts in order, one space apart. */
const words = (el: Element): string => [...el.childNodes].map((n) => plain(n.textContent ?? '').trim()).filter(Boolean).join(' ');

async function setup(data: RefundOptionsOut | null = options(), locale: 'en' | 'es' = 'en', session = undefined as typeof EMPLOYEE | undefined) {
  const m = await mountSale(RefundForm, { props: { saleId: 's1' }, locale, session });
  const call = await m.live();
  if (data) await m.result('sale.refund.options', data);
  const cards = () => m.wrapper.findAllComponents(RefundTenderCard);
  const amounts = () => cards().map((card) => card.props('amount'));
  const confirmButton = () => m.find('refund-confirm');
  const blocked = () => (m.find('refund-blocked').exists() ? plain(m.find('refund-blocked').text()) : null);
  async function setAmount(index: number, text: string) {
    cards()[index].vm.$emit('update:amount', text);
    await flush();
  }
  async function pick(picked: Record<string, number>) {
    m.wrapper.findComponent(RefundLines).vm.$emit('update:picked', picked);
    await flush();
  }
  async function reason(text: string) {
    await ionValue(m.find('refund-reason').element, text, 'ionInput');
  }
  async function confirm() {
    await click(confirmButton().element);
  }
  const refunds = () => m.sent().filter((c) => c.path === '/api/sale/sales/refund');
  return { ...m, call, cards, amounts, confirmButton, blocked, setAmount, pick, reason, confirm, refunds };
}

describe('RefundForm: what can go back', () => {
  it('reads it from the server, saying it is loading', async () => {
    const s = await setup(null);
    expect(s.params('sale.refund.options')).toEqual([{ sale_id: 's1' }]);
    expect(s.find('refund-loading').text()).toBe('Loading what can be refunded…');
  });

  it('proposes the full refund, split by tender, with the lines to mark', async () => {
    const s = await setup();
    expect(s.find('refund-explain').text()).toBe('Choose how much goes back to each way it was paid. The split below is a proposal — change any amount.');
    expect(s.wrapper.findComponent(RefundLines).props('lines')).toEqual(options().lines);
    expect(s.cards().map((card) => card.props('tender').payment_id)).toEqual(['p1', 'p2']);
    expect(s.amounts()).toEqual(['10.00', '5.00']);
    expect(words(s.find('refund-total').element)).toBe('Refunding €15.00');
    expect(plain(s.confirmButton().text())).toBe('Refund €15.00');
  });

  it('marking lines proposes their share, split by what each tender has left', async () => {
    const s = await setup();
    await s.pick({ b: 1000 });
    expect(s.amounts()).toEqual(['2.67', '1.33']);
    expect(words(s.find('refund-total').element)).toBe('Refunding €4.00');
    await s.pick({});
    expect(s.amounts()).toEqual(['10.00', '5.00']);
  });

  it('«Refund everything» puts the full proposal back after an edit', async () => {
    const s = await setup();
    await s.setAmount(0, '1');
    expect(words(s.find('refund-total').element)).toBe('Refunding €6.00');
    await click(s.find('refund-propose-all').element);
    expect(s.amounts()).toEqual(['10.00', '5.00']);
  });

  it('a later answer of the server keeps what the person typed', async () => {
    const s = await setup();
    await s.setAmount(0, '1');
    await s.result('sale.refund.options', options({ refunded_total: 0 }), {}, 2);
    expect(s.amounts()).toEqual(['1', '5.00']);
  });

  it('nothing left to give back says so, with no button', async () => {
    const s = await setup(options({ refundable_total: 0, tenders: [tender('p1', { refunded: 1000, remaining: 0, refundable: false, reason: 'already_refunded' })] }));
    expect(s.find('refund-nothing').text()).toContain('There is nothing left to refund on this sale.');
    expect(s.confirmButton().exists()).toBe(false);
  });

  it('a failed read says so, with Retry', async () => {
    const s = await setup(null);
    s.call.push(errorFrame(s.subId('sale.refund.options'), 'not_found'));
    await flush();
    expect(s.wrapper.findComponent(InlineFeedback).text()).toContain('The sale could not be loaded, so there is nothing to refund yet. Try again.');
    const reconnect = vi.spyOn(s.client.stream, 'reconnect');
    await s.find('refund-retry').trigger('click');
    expect(reconnect).toHaveBeenCalledOnce();
  });
});

describe('RefundForm: why it cannot go yet', () => {
  it('a reason is needed: the button says so instead of refunding (aria-disabled, the tap answers)', async () => {
    const s = await setup();
    expect(s.blocked()).toBe('A refund needs a reason.');
    expect(s.confirmButton().attributes('aria-disabled')).toBe('true');
    expect(prop(s.confirmButton().element, 'disabled')).toBe(false);
    await s.confirm();
    expect(s.refunds()).toEqual([]);
    expect(toastError).toHaveBeenCalledWith('A refund needs a reason.');
  });

  it('more than a tender has left names it, on the window and on its card', async () => {
    const s = await setup();
    await s.reason('Broken');
    await s.setAmount(0, '20');
    expect(s.blocked()).toBe('Cash: €20.00 is more than the €10.00 still refundable.');
    expect(s.cards()[0].props('error')).toBe('Cash: €20.00 is more than the €10.00 still refundable.');
  });

  it('what is not an amount, or nothing at all, says so', async () => {
    const s = await setup();
    await s.reason('Broken');
    await s.setAmount(1, 'abc');
    expect(s.blocked()).toBe('Card: type an amount, like 12.50.');
    expect(s.cards()[1].props('error')).toBe('Card: type an amount, like 12.50.');
    await s.setAmount(0, '0');
    await s.setAmount(1, '');
    expect(s.blocked()).toBe('Type how much goes back.');
  });

  it('money on a tender that cannot go back its own way asks where it goes', async () => {
    const s = await setup(
      options({ tenders: [tender('p1'), tender('p2', { position: 2, method_name: 'Gift card', remaining: 500, refundable: false, reason: 'method_unavailable' })] }),
    );
    await s.reason('Broken');
    expect(s.blocked()).toBe('Gift card: choose where this money goes back.');
    s.cards()[1].vm.$emit('update:destination', 'm-card');
    await flush();
    expect(s.blocked()).toBeNull();
    expect(s.confirmButton().attributes('aria-disabled')).toBeUndefined();
  });
});

describe('RefundForm: refunding', () => {
  it('sends the tenders, the reason and the attempt key; says «Refund recorded.» and is done', async () => {
    const s = await setup();
    s.answer(200, { already: false, refund_id: 'r1', sale_id: 's1', total: 1500, fully_refunded: true });
    await s.reason('  Broken cup ');
    await s.confirm();
    const [sent] = s.refunds();
    expect(sent.method).toBe('POST');
    expect(sent.body).toEqual({
      sale_id: 's1',
      reason: 'Broken cup',
      idempotency_key: expect.stringMatching(/^refund-s1-[A-Za-z0-9-]+$/),
      allocations: [
        { payment_id: 'p1', amount: 1000 },
        { payment_id: 'p2', amount: 500 },
      ],
    });
    expect(toastSuccess).toHaveBeenCalledWith('Refund recorded.');
    expect(s.wrapper.emitted('refunded')).toHaveLength(1);
  });

  it('the marked lines go with their units; a destination with its tender', async () => {
    const s = await setup(
      options({ tenders: [tender('p1', { remaining: 1500, charged: 1500, refundable: false, reason: 'method_unavailable' })] }),
    );
    await s.pick({ b: 2000, a: 1000 });
    s.cards()[0].vm.$emit('update:destination', 'm-card');
    await s.reason('Returned');
    await s.confirm();
    expect(s.refunds()[0].body).toMatchObject({
      allocations: [{ payment_id: 'p1', amount: 1100, to_method_id: 'm-card' }],
      lines: [
        { line_id: 'a', quantity: '1.000' },
        { line_id: 'b', quantity: '2.000' },
      ],
    });
  });

  it('a refusal is read inside the window; trying again carries the same attempt key', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'sale.refund_line_already_returned', message: 'One of the marked lines already went back with another refund.' } });
    await s.reason('Broken');
    await s.confirm();
    expect(s.find('refund-error').text()).toContain('One of the marked lines already went back with another refund.');
    expect(s.wrapper.emitted('refunded')).toBeUndefined();
    s.answer(200, { already: true, refund_id: 'r1', sale_id: 's1', total: 1500, fully_refunded: true });
    await s.confirm();
    const keys = s.refunds().map((c) => (c.body as { idempotency_key: string }).idempotency_key);
    expect(keys).toHaveLength(2);
    expect(keys[1]).toBe(keys[0]);
    expect(s.wrapper.emitted('refunded')).toHaveLength(1);
    expect(s.find('refund-error').exists()).toBe(false);
  });

  it('the cashier is asked for a manager’s approval, and the manager’s PIN refunds the very same attempt once', async () => {
    const s = await setup(options(), 'en', EMPLOYEE);
    let calls = 0;
    s.net.onApi(() =>
      calls++ === 0
        ? Response.json(asksApproval('sale.sale.refund', 'Refund a sale'), { status: 403 })
        : Response.json({ already: false, refund_id: 'r1', sale_id: 's1', total: 1500, fully_refunded: true }),
    );
    await s.reason('Broken');
    await s.confirm();
    await approvalSettled();
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Refund a sale']);
    const [asked, approved] = s.refunds().map((call) => call.body);
    expect(approved).toEqual(asked);
    expect(toastSuccess).toHaveBeenCalledWith('Refund recorded.');
    expect(s.wrapper.emitted('refunded')).toHaveLength(1);
  });

  it('«Cancel» on the approval leaves its refusal inside the window', async () => {
    const s = await setup(options(), 'es', EMPLOYEE);
    approvalDialog.answer = CANCELLED;
    s.answer(403, { error: { ...asksApproval('sale.sale.refund', 'Devolver una venta').error, message: 'Esto necesita la aprobación de un encargado.' } });
    await s.reason('Roto');
    await s.confirm();
    await approvalSettled();
    expect(approvalDialog.questions.map((question) => question.label)).toEqual(['Devolver una venta']);
    expect(s.refunds()).toHaveLength(1);
    expect(s.find('refund-error').text()).toContain('Esto necesita la aprobación de un encargado.');
    expect(s.wrapper.emitted('refunded')).toBeUndefined();
  });

  it('an answer that never came says a retry will not refund twice', async () => {
    const s = await setup();
    s.net.onApi(() => {
      throw new TypeError('offline');
    });
    await s.reason('Broken');
    await s.confirm();
    expect(s.find('refund-error').text()).toContain("We couldn't confirm whether the refund was recorded. Tapping Refund again won't record it twice.");
  });

  it('an answer that is not the API’s (a proxy’s error page) says it too, never the SDK’s English', async () => {
    const s = await setup();
    s.answer(502, 'Bad gateway');
    await s.reason('Broken');
    await s.confirm();
    expect(s.find('refund-error').text()).toContain("We couldn't confirm whether the refund was recorded. Tapping Refund again won't record it twice.");
    expect(s.find('refund-error').text()).not.toContain('HTTP 502');
  });

  it('every opening is a new attempt', async () => {
    const first = await setup();
    await first.reason('x');
    await first.confirm();
    const second = await setup();
    await second.reason('x');
    await second.confirm();
    const key = (c: { body: unknown }) => (c.body as { idempotency_key: string }).idempotency_key;
    expect(key(first.refunds()[0])).not.toBe(key(second.refunds()[0]));
  });
});

describe('RefundForm: the rest', () => {
  it('speaks Spanish', async () => {
    const s = await setup(options(), 'es');
    expect(s.find('refund-explain').text()).toBe('Elige cuánto vuelve por cada forma en que se pagó. El reparto de abajo es una propuesta: cambia el importe que quieras.');
    expect(s.amounts()).toEqual(['10,00', '5,00']);
    expect(words(s.find('refund-total').element)).toBe('Se devuelve 15,00 €');
    expect(plain(s.confirmButton().text())).toBe('Devolver 15,00 €');
    expect(s.find('refund-propose-all').text()).toBe('Devolver todo');
    expect([prop(s.find('refund-reason').element, 'label'), prop(s.find('refund-reason').element, 'placeholder')]).toEqual(['Motivo', 'Por qué vuelve el dinero']);
    expect(s.blocked()).toBe('Una devolución necesita un motivo.');
  });
});

describe('RefundForm: the session of a voucher (SALE-F32)', () => {
  const COVERED = line('v', { name: 'Corte', line_total: 0, paid_by_voucher: true, voucher_name: 'Bono 5 cortes' });

  it('a sale paid whole with a voucher has a session to give back, with no money', async () => {
    const s = await setup(options({ total: 0, refundable_total: 0, tenders: [], lines: [COVERED] }), 'es');
    expect(s.find('refund-nothing').exists()).toBe(false);
    // No money in it: nothing to «Refund everything».
    expect(s.find('refund-propose-all').exists()).toBe(false);
    expect(s.blocked()).toBe('Marca la línea cuya sesión vuelve al bono.');
    await s.pick({ v: 1000 });
    await s.reason('No vino');
    expect(s.blocked()).toBeNull();
    expect(plain(s.confirmButton().text())).toBe('Devolver la sesión');
    s.answer(200, { already: false, refund_id: 'r1', sale_id: 's1', total: 0, fully_refunded: true });
    await s.confirm();
    expect(s.refunds().at(-1)?.body).toMatchObject({ sale_id: 's1', reason: 'No vino', allocations: [], lines: [{ line_id: 'v', quantity: '1.000' }] });
  });

  it('money and the session go back together', async () => {
    const s = await setup(options({ lines: [line('a'), COVERED] }));
    await s.pick({ v: 1000 });
    await s.setAmount(0, '3.00');
    await s.setAmount(1, '0');
    await s.reason('wrong');
    s.answer(200, { already: false, refund_id: 'r1', sale_id: 's1', total: 300, fully_refunded: false });
    await s.confirm();
    expect(s.refunds().at(-1)?.body).toMatchObject({ allocations: [{ payment_id: 'p1', amount: 300 }], lines: [{ line_id: 'v' }] });
  });

  it('nothing left is «nothing left» only when no session is left either', async () => {
    const s = await setup(options({ total: 0, refundable_total: 0, tenders: [], lines: [{ ...COVERED, left: '0.000', returned: '1.000' }] }));
    expect(s.find('refund-nothing').exists()).toBe(true);
  });
});
