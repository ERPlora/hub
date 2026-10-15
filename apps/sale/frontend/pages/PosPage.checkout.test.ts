// The till with the REAL checkout sheet and the REAL document window (no stubs; only Ionic's modal is the
// test double and the customer search is the Customers app's own business): what is charged is frozen
// when «Charge» opens the sheet (the marked lines, the version of the total it paints), a check changed
// meanwhile is refused and said in the sheet, a check closed elsewhere is let go once the sheet closes,
// and a partial charge keeps the check and opens its sale's document.
import { toastError } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, flush, mountSale, resultFrame, settle } from '../__tests__/mount-sale';
import CartLines from '../components/pos/CartLines.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import { line, memoryStorage, order, preview, product, settings } from '../components/pos/__tests__/fixtures';
import { CURRENT_CHECK_KEY } from '../composables/pos/useCurrentCheck';
import type { CompleteIn, PaymentMethodOut, SaleOut } from '../operations';
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
vi.mock('../../../customer/frontend/components/CustomerSearch.vue', async () => {
  const { h } = await import('vue');
  return {
    default: {
      name: 'CustomerSearch',
      props: { modelValue: Object, open: Boolean },
      emits: ['update:modelValue', 'update:open'],
      render: () => h('button', { 'data-testid': 'customer-stub' }),
    },
    snapshotOf: () => ({}),
  };
});

beforeEach(() => vi.stubGlobal('localStorage', memoryStorage()));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(toastError).mockClear();
});

const TWO = order({ id: 'o1', version: 2, lines: [line({ id: 'l1' }), line({ id: 'l2', product_id: 'p2', name: 'Tea' })] });
const CARD: PaymentMethodOut = { id: 'm-card', name: 'Card', display_name: 'Card', type: 'card', sort_order: 1, requires_change: false, allowed: true };
const SALE = { id: 'sale-9', number: '20261014-0009', total: 150, already: false } as SaleOut;

async function setup() {
  const m = await mountSale(PosPage);
  await m.live();
  await m.result('sale.pos_settings.get', settings());
  /** Pushes `data` to every subscription of `op` whose params satisfy `match`. */
  async function push(op: string, data: unknown, match: (params: Record<string, unknown>) => boolean = () => true) {
    const subs = m.client.stream.subscriptions(op as never).filter((s) => match(s.params as Record<string, unknown>));
    if (!subs.length) throw new Error(`no subscription to ${op}`);
    for (const sub of subs) m.net.lastStream().push(resultFrame(sub.id, data, 10));
    await flush();
  }
  /** Each POST answers by path, in order. */
  const answers: Record<string, Response[]> = {};
  m.net.onApi(({ url }) => answers[new URL(url, 'http://a.localhost').pathname]?.shift() ?? Response.json({}));
  const charges = () => m.sent().filter((c) => c.path === '/api/sale/sales');
  async function openCheck() {
    answers['/api/sale/orders'] = [Response.json(TWO)];
    m.wrapper.findComponent(PosCatalog).vm.$emit('add', product({ id: 'p1' }));
    await settle();
    await m.reopen();
  }
  async function chargeMarked(lineId: string) {
    m.wrapper.findComponent(CartLines).vm.$emit('mark', TWO.lines.find((l) => l.id === lineId));
    await settle();
    await click(m.find('pos-charge').element);
    await settle();
    await m.reopen();
    await push('sale.checkout.preview', preview({ order_version: 2, total: 150, lines_count: 1 }), (p) => 'line_ids' in p);
    await push('sale.checkout.preview', preview({ order_version: 2, total: 300, lines_count: 2 }), (p) => !('line_ids' in p));
    // A single method (card): the sheet starts on it, with nothing to pick.
    await push('sale.payment_method.list', { rows: [CARD], total: 1, limit: 100, offset: 0 });
  }
  return { ...m, push, answers, charges, openCheck, chargeMarked };
}

describe('PosPage + the real checkout sheet', () => {
  it('the check changing under the open sheet: the charge keeps the marked line and the version it showed; the 409 is read in the sheet', async () => {
    const s = await setup();
    await s.openCheck();
    await s.chargeMarked('l2');
    // Another device voids the marked line: the live check drops it, and the mark with it.
    await s.push('sale.order.get', order({ id: 'o1', version: 3, lines: [line({ id: 'l1' })] }), (p) => p.order_id === 'o1');
    expect(s.wrapper.findComponent(CartLines).props('marks')).toEqual([]);
    const message = 'The check changed while it was being charged. Nothing was charged.';
    s.answers['/api/sale/sales'] = [Response.json({ error: { code: 'sale.order_changed', message } }, { status: 409 })];
    await click(s.find('sale-checkout-confirm').element);
    await settle();
    expect(s.charges().at(-1)?.body).toMatchObject({ order_id: 'o1', line_ids: ['l2'], order_version: 2 } satisfies Partial<CompleteIn>);
    expect(s.find('sale-checkout-error').text()).toContain(message);
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
  });

  it('a check closed on another device while the sheet is open is let go when the sheet closes', async () => {
    const s = await setup();
    await s.openCheck();
    await s.chargeMarked('l1');
    await s.push('sale.order.get', order({ id: 'o1', version: 7, status: 'completed', lines: [] }), (p) => p.order_id === 'o1');
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(toastError).not.toHaveBeenCalled();
    await click(s.find('sale-checkout-close').element);
    await settle();
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBeNull();
    expect(toastError).toHaveBeenCalledWith('That check was closed on another device: the screen starts a new one.');
  });

  it('a partial charge keeps the check with what is left and opens that sale’s document', async () => {
    const s = await setup();
    await s.openCheck();
    await s.chargeMarked('l1');
    s.answers['/api/sale/sales'] = [Response.json(SALE)];
    await click(s.find('sale-checkout-confirm').element);
    await settle();
    await s.reopen();
    expect(s.charges().at(-1)?.body).toMatchObject({ line_ids: ['l1'], order_version: 2 });
    expect(localStorage.getItem(CURRENT_CHECK_KEY)).toBe('o1');
    expect(s.find('sale-checkout').exists()).toBe(false);
    expect(s.params('sale.sale.get')).toEqual([{ sale_id: 'sale-9' }]);
    expect(s.find('sale-document-modal').exists()).toBe(true);
  });
});
