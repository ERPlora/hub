// The charge of the sheet (SALE-F01, F06, F14): one attempt key per opening of the sheet, reused on every
// retry, so the server records at most one sale per attempt; the door (`sale.sale.complete`, or
// `sale.sale.complete_over_limit` with the same payload when a discount over the cap needs it and the
// person may approve it); a refusal kept with the server's words; and, when the answer is lost (no
// network, a 5xx, a proxy's HTML), the recovery: ask `sale.sale.by_idempotency_key` up to twice —
// charged finishes as a charge, not charged says the server is not answering, unknown sends to Sales.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { EMPLOYEE, flush, MANAGER, mountSale } from '../../__tests__/mount-sale';
import type { CompleteIn, SaleOut } from '../../operations';
import { RECOVERY_DELAY_MS, useCheckout } from './useCheckout';

type Input = Omit<CompleteIn, 'idempotency_key'>;
type Checkout = ReturnType<typeof useCheckout>;

const INPUT: Input = { order_id: 'o1', order_version: 3, payments: [{ method_id: 'm-card' }], document_type: 'ticket' };
const SALE = { id: 's1', number: '20261014-0001', total: 4250, already: false } as SaleOut;

const Probe = defineComponent({
  emits: ['charged'],
  setup(_props, { emit, expose }) {
    // Inside an object: the instance proxy unwraps exposed refs, the test reads them as refs.
    expose({ checkout: useCheckout({ onCharged: (sale) => emit('charged', sale) }) });
    return () => h('div');
  },
});

type Reply = Response | (() => Response);

async function setup(session = MANAGER) {
  const m = await mountSale(Probe, { session });
  const { checkout } = m.wrapper.vm as unknown as { checkout: Checkout };
  /** Answers each API call by its path, in order; a path with no reply left gets a network failure. */
  function replies(byPath: Record<string, Reply[]>): void {
    m.net.onApi(({ url }) => {
      const path = new URL(url, 'http://a.localhost').pathname;
      const next = byPath[path]?.shift();
      if (!next) throw new TypeError('Failed to fetch');
      return typeof next === 'function' ? next() : next;
    });
  }
  const charged = () => m.wrapper.emitted('charged') ?? [];
  return { ...m, checkout, replies, charged };
}

const refusal = (status: number, code: string, message: string) => Response.json({ error: { code, message } }, { status });
const COMPLETE = '/api/sale/sales';
const OVER_LIMIT = '/api/sale/sales/complete_over_limit';
const BY_KEY = '/api/sale/sales/by_key';

describe('useCheckout', () => {
  it('opens with an attempt key the server accepts', async () => {
    const s = await setup();
    expect(s.checkout.key.value).toMatch(/^sale-[A-Za-z0-9_.:-]{8,123}$/);
  });

  it('charges through sale.sale.complete with the attempt key and finishes the charge', async () => {
    const s = await setup();
    s.replies({ [COMPLETE]: [Response.json(SALE)] });
    const key = s.checkout.key.value;
    const done = s.checkout.charge(INPUT);
    expect(s.checkout.busy.value).toBe(true);
    await done;
    expect(s.sent()).toEqual([{ method: 'POST', path: COMPLETE, query: {}, body: { ...INPUT, idempotency_key: key } }]);
    expect(s.charged()).toEqual([[SALE]]);
    expect([s.checkout.busy.value, s.checkout.failure.value]).toEqual([false, null]);
  });

  it('a refusal on a field keeps which field it is (the recipient’s tax ID, SALE-F04)', async () => {
    const s = await setup();
    const message = 'That tax ID is not valid.';
    s.replies({
      [COMPLETE]: [Response.json({ error: { code: 'invalid_field', message, fields: { customer_tax_id: message } } }, { status: 422 })],
    });
    await s.checkout.charge(INPUT);
    expect(s.checkout.failure.value).toEqual({ kind: 'refused', code: 'invalid_field', message, fields: { customer_tax_id: message } });
  });

  it('ignores a second press while the charge is in flight', async () => {
    const s = await setup();
    s.replies({ [COMPLETE]: [Response.json(SALE)] });
    const first = s.checkout.charge(INPUT);
    await s.checkout.charge(INPUT);
    await first;
    expect(s.sent()).toHaveLength(1);
  });

  it('a refusal keeps the server’s words, charges nothing, and the next attempt gets a new key', async () => {
    const s = await setup();
    const message = 'The amount tendered does not cover the total.';
    s.replies({ [COMPLETE]: [refusal(409, 'sale.insufficient_tendered', message)] });
    const key = s.checkout.key.value;
    await s.checkout.charge(INPUT);
    expect(s.checkout.failure.value).toEqual({ kind: 'refused', code: 'sale.insufficient_tendered', message });
    expect(s.charged()).toEqual([]);
    expect(s.checkout.key.value).not.toBe(key);
    expect(s.sent().map((c) => c.path)).toEqual([COMPLETE]);
  });

  it('a business that files for real and cannot reach the AEAT is refused in the server’s words, in its language', async () => {
    // Working-rules §15: VeriFactu refuses the charge itself (no ticket that could never be filed); the till
    // shows what the server says, already in the cashier's language, and charges nothing.
    const s = await setup();
    const message =
      'No se ha emitido nada: este negocio presenta en real a la AEAT y ahora no puede hacerle llegar sus registros: ' +
      'la opción en vivo de VeriFactu no está en tu plan: añádela en tu cuenta de ERPlora. Resuélvelo en VeriFactu → Ajustes y vuelve a intentarlo.';
    s.replies({ [COMPLETE]: [refusal(409, 'verifactu.live_option_unpaid', message)] });
    await s.checkout.charge(INPUT);
    expect(s.checkout.failure.value).toEqual({ kind: 'refused', code: 'verifactu.live_option_unpaid', message });
    expect(s.charged()).toEqual([]);
    expect(s.sent().map((c) => c.path)).toEqual([COMPLETE]);
  });

  it('a discount over the cap goes again through complete_over_limit, same payload and key, for a manager', async () => {
    const s = await setup(MANAGER);
    s.replies({
      [COMPLETE]: [refusal(409, 'sale.discount_over_limit', 'That discount is over the limit.')],
      [OVER_LIMIT]: [Response.json(SALE)],
    });
    const key = s.checkout.key.value;
    await s.checkout.charge(INPUT);
    expect(s.sent().map((c) => [c.path, c.body])).toEqual([
      [COMPLETE, { ...INPUT, idempotency_key: key }],
      [OVER_LIMIT, { ...INPUT, idempotency_key: key }],
    ]);
    expect(s.charged()).toEqual([[SALE]]);
  });

  it('without the permission, the discount refusal is said and nothing else is tried', async () => {
    const s = await setup(EMPLOYEE);
    const message = 'That discount is over the limit: a manager has to approve it.';
    s.replies({ [COMPLETE]: [refusal(409, 'sale.discount_over_limit', message)] });
    await s.checkout.charge(INPUT);
    expect(s.sent().map((c) => c.path)).toEqual([COMPLETE]);
    expect(s.checkout.failure.value).toEqual({ kind: 'refused', code: 'sale.discount_over_limit', message });
  });

  it('no answer: asks by the attempt key and, if it was charged, finishes as a charge', async () => {
    const s = await setup();
    s.replies({ [BY_KEY]: [Response.json({ found: true, sale: SALE })] });
    const key = s.checkout.key.value;
    await s.checkout.charge(INPUT);
    expect(s.sent().map((c) => [c.method, c.path, c.query])).toEqual([
      ['POST', COMPLETE, {}],
      ['GET', BY_KEY, { idempotency_key: key }],
    ]);
    expect(s.charged()).toEqual([[SALE]]);
    expect(s.checkout.failure.value).toBeNull();
  });

  it('no answer and not charged: the server is not answering, and the next press reuses the key', async () => {
    const s = await setup();
    s.replies({ [BY_KEY]: [Response.json({ found: false, sale: null })] });
    const key = s.checkout.key.value;
    await s.checkout.charge(INPUT);
    expect(s.checkout.failure.value).toEqual({ kind: 'not_charged' });
    expect(s.charged()).toEqual([]);
    s.replies({ [COMPLETE]: [Response.json(SALE)] });
    await s.checkout.charge(INPUT);
    expect((s.sent().at(-1)?.body as CompleteIn).idempotency_key).toBe(key);
    expect(s.charged()).toEqual([[SALE]]);
  });

  it('a 5xx or a proxy’s HTML page is a lost answer too; two failed lookups leave it unknown', async () => {
    const s = await setup();
    const html = () => new Response('<html><body>502 Bad Gateway</body></html>', { status: 502 });
    s.replies({ [COMPLETE]: [html], [BY_KEY]: [refusal(503, 'unavailable', 'Unavailable'), html] });
    const key = s.checkout.key.value;
    const done = s.checkout.charge(INPUT);
    await flush();
    expect(s.sent().map((c) => c.path)).toEqual([COMPLETE, BY_KEY]);
    await s.clock.advance(RECOVERY_DELAY_MS);
    await done;
    expect(s.sent().map((c) => c.path)).toEqual([COMPLETE, BY_KEY, BY_KEY]);
    expect(s.checkout.failure.value).toEqual({ kind: 'unknown' });
    expect([s.checkout.key.value, s.checkout.busy.value]).toEqual([key, false]);
  });

  it('the same attempt already being recorded is resolved by its key', async () => {
    const s = await setup();
    s.replies({
      [COMPLETE]: [refusal(409, 'sale.checkout_in_progress', 'This charge is already being recorded.')],
      [BY_KEY]: [Response.json({ found: true, sale: { ...SALE, already: true } })],
    });
    await s.checkout.charge(INPUT);
    expect(s.charged()).toEqual([[{ ...SALE, already: true }]]);
  });

  it('a new attempt clears the last failure', async () => {
    const s = await setup();
    s.replies({ [COMPLETE]: [refusal(409, 'sale.order_changed', 'The check changed.'), Response.json(SALE)] });
    await s.checkout.charge(INPUT);
    expect(s.checkout.failure.value?.kind).toBe('refused');
    const done = s.checkout.charge(INPUT);
    expect(s.checkout.failure.value).toBeNull();
    await done;
  });
});
