// The charge sheet's content (WORKBOOK «Pantallas · Cobro»; SALE-F01–F06, F22): the amount to charge is
// the server's (`sale.checkout.preview`: total, cash limit, ticket limit), the methods are those the
// settings allow (`sale.payment_method.list`), the document starts from the till settings
// (`sale.pos_settings.get`); the person types what was handed over, splits, chooses receipt or invoice,
// and «Charge» sends `sale.sale.complete` with this opening's attempt key. Every way it can go: cash,
// card, split, the legal limits, invoice and its recipient abroad, part of a check, a refusal, a lost
// answer, a read that fails.
import { toast } from '@erplora/ui/shell';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CustomerSnapshot } from '../../../../customer/frontend/components/CustomerSearch.vue';
import { click, EMPLOYEE, errorFrame, flush, ionValue, type MountOptions, mountSale, resultFrame } from '../../__tests__/mount-sale';
import { RECOVERY_DELAY_MS } from '../../composables/checkout/useCheckout';
import { plain } from '../../lib/format';
import type { CompleteIn, PaymentMethodOut, PreviewOut, SaleOut, SettingsOut } from '../../operations';
import CheckoutPanel from './CheckoutPanel.vue';
import CheckoutSide from './CheckoutSide.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...((await importOriginal()) as object),
  toast: vi.fn(() => Promise.resolve()),
}));
beforeEach(() => vi.mocked(toast).mockClear());

const PREVIEW_OP = 'sale.checkout.preview';
const METHODS_OP = 'sale.payment_method.list';
const SETTINGS_OP = 'sale.pos_settings.get';

const preview = (over: Partial<PreviewOut> = {}): PreviewOut => ({
  order_id: 'o1',
  order_version: 3,
  lines_count: 2,
  tax_included: true,
  subtotal: 3512,
  tax_total: 738,
  discount_amount: 0,
  discount_percent: '0.00',
  ticket_discount_amount: 0,
  gift_total: 0,
  total: 4250,
  breakdown: [],
  lines: [],
  cash_limit: 100000,
  ticket_limit: 300000,
  ...over,
});

const method = (id: string, type: PaymentMethodOut['type'], display_name: string, allowed = true): PaymentMethodOut => ({
  id,
  name: id,
  display_name,
  type,
  sort_order: 0,
  requires_change: type === 'cash',
  allowed,
});
const CARD = method('m-card', 'card', 'Card');
const CASH = method('m-cash', 'cash', 'Cash');
const TRANSFER = method('m-transfer', 'transfer', 'Transfer', false);
const METHODS = { rows: [CARD, CASH, TRANSFER], total: 3, limit: 100, offset: 0 };

const SETTINGS: SettingsOut = {
  allow_cash: true,
  allow_card: true,
  allow_transfer: false,
  show_products: true,
  show_services: true,
  require_customer: false,
  allow_discounts: true,
  max_discount_percent: 100,
  enable_parked_tickets: true,
  default_tax_included: true,
  auto_invoice_with_tax_id: false,
  default_document_type: 'ticket',
  receipt_header: '',
  receipt_footer: '',
  receipt_footer_image: '',
  receipt_marketing_url: '',
  receipt_marketing_text: '',
  updated_at: null,
};

const CUSTOMER: CustomerSnapshot = {
  customer_id: 'c1',
  customer_name: 'Bar Pepe SL',
  customer_tax_id: 'B12345678',
  customer_address: 'Calle Mayor 1, 28001 Madrid, España',
  customer_country: 'ES',
};

const SALE = { id: 's1', number: '20261014-0001', total: 4250, already: false } as SaleOut;

const BLANK_RECIPIENT = { customer_name: '', customer_tax_id: '', customer_address: '', customer_country: '', customer_id_type: '' };

interface Setup {
  props?: Record<string, unknown>;
  locale?: MountOptions['locale'];
  session?: MountOptions['session'];
  preview?: PreviewOut | null;
  methods?: typeof METHODS | null;
  settings?: SettingsOut | null;
}

async function setup(options: Setup = {}) {
  const m = await mountSale(CheckoutPanel, {
    props: { orderId: 'o1', lineIds: [], orderVersion: 3, customer: null, staffId: null, ...options.props },
    locale: options.locale,
    session: options.session,
  });
  await m.live();
  const subs = (op: string) => m.client.stream.subscriptions(op as never);
  /** Pushes `data` to the subscription of `op` whose params satisfy `match`. */
  async function push(op: string, data: unknown, match: (params: Record<string, unknown>) => boolean = () => true) {
    const sub = subs(op).find((s) => match(s.params as Record<string, unknown>));
    if (!sub) throw new Error(`no subscription to ${op}`);
    m.net.lastStream().push(resultFrame(sub.id, data, 1));
    await flush();
  }
  if (options.preview !== null) await push(PREVIEW_OP, options.preview ?? preview());
  if (options.methods !== null) await push(METHODS_OP, options.methods ?? METHODS);
  if (options.settings !== null) await push(SETTINGS_OP, options.settings ?? SETTINGS);

  /** What a hook reads: its parts (label, amount…) joined by a space, or its text. */
  const text = (testid: string) => {
    const el = m.find(testid).element;
    const parts = [...el.children].map((child) => child.textContent?.trim()).filter(Boolean);
    return plain(parts.length ? parts.join(' ') : (el.textContent ?? '')).replace(/\s+/g, ' ').trim();
  };
  const confirm = () => m.find('sale-checkout-confirm').element as HTMLElement & { disabled?: boolean };
  const label = () => plain(confirm().textContent ?? '').trim();
  const type = async (...keys: string[]) => {
    for (const key of keys) await click(m.find(`sale-checkout-keypad-${key}`).element);
  };
  /** Answers each API call by path, in order; none left → no answer (a network failure). */
  function replies(byPath: Record<string, Response[]>): void {
    m.net.onApi(({ url }) => {
      const next = byPath[new URL(url, 'http://a.localhost').pathname]?.shift();
      if (!next) throw new TypeError('Failed to fetch');
      return next;
    });
  }
  const charges = () => m.sent().filter((c) => c.method === 'POST');
  const body = () => charges().at(-1)?.body as CompleteIn;
  return { ...m, subs, push, text, confirm, label, type, replies, charges, body };
}

describe('CheckoutPanel: what it reads', () => {
  it('follows the preview of the check, the methods and the till settings', async () => {
    const s = await setup();
    expect(s.params(PREVIEW_OP)).toEqual([{ order_id: 'o1' }]);
    expect(s.params(METHODS_OP)).toEqual([{ limit: 100 }]);
    expect(s.params(SETTINGS_OP)).toEqual([{}]);
  });

  it('while the total is worked out: says so, and «Charge» cannot be pressed', async () => {
    const s = await setup({ preview: null });
    expect(s.text('sale-checkout-total')).toBe('Working out the total…');
    expect([s.label(), s.confirm().disabled]).toEqual(['Charge', true]);
  });

  it('while the methods load: says so', async () => {
    const s = await setup({ methods: null });
    expect(s.text('sale-checkout-methods-loading')).toBe('Loading the payment methods…');
    expect(s.confirm().disabled).toBe(true);
  });

  it('with no method to charge with: says so, and cannot charge', async () => {
    const s = await setup({ methods: { rows: [TRANSFER], total: 1, limit: 100, offset: 0 } });
    expect(s.text('sale-checkout-no-methods')).toBe('This business has no payment method to charge with.');
    expect(s.confirm().disabled).toBe(true);
  });

  it('a read that fails says the server’s words with «Retry», and cannot charge', async () => {
    const s = await setup({ preview: null });
    s.net.lastStream().push(errorFrame(s.subId(PREVIEW_OP), 'sale.no_tax_rule'));
    await flush();
    expect(s.find('sale-checkout-read-error').text()).toContain('msg sale.no_tax_rule');
    expect(s.confirm().disabled).toBe(true);
    const streams = s.net.streams.length;
    await click(s.find('sale-checkout-retry').element);
    await s.reopen();
    expect(s.net.streams.length).toBe(streams + 1);
  });
});

describe('CheckoutPanel: cash (SALE-F01)', () => {
  it('the server’s total, big; cash first; asks for the amount tendered until it is typed', async () => {
    const s = await setup();
    expect(s.text('sale-checkout-total')).toBe('€42.50');
    expect(s.find('sale-checkout-method-m-cash').attributes('aria-pressed')).toBe('true');
    expect(s.find('sale-checkout-method-m-transfer').exists()).toBe(false);
    expect(s.text('sale-checkout-block-reason')).toBe('Enter the amount tendered on the keypad');
    expect([s.label(), s.confirm().getAttribute('aria-disabled')]).toEqual(['Charge €42.50', 'true']);
  });

  it('short of the total says so; enough shows the change, big', async () => {
    const s = await setup();
    await s.type('4', '0');
    expect(s.label()).toBe('The amount tendered does not cover the total');
    await s.type('clear', '5', '0');
    expect(s.text('sale-checkout-change')).toBe('Change €7.50');
    expect([s.label(), s.confirm().getAttribute('aria-disabled')]).toEqual(['Charge €42.50', null]);
  });

  it('a tap while it cannot charge answers with the reason and sends nothing', async () => {
    const s = await setup();
    await click(s.confirm());
    expect(toast).toHaveBeenCalledWith('Enter the amount tendered on the keypad', 'warning');
    expect(s.charges()).toEqual([]);
  });

  it('charges the check with what was handed over and this attempt’s key, and finishes', async () => {
    const s = await setup({ props: { staffId: 'st1' } });
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await s.type('5', '0');
    await click(s.confirm());
    expect(s.charges().map((c) => c.path)).toEqual(['/api/sale/sales']);
    expect(s.body()).toEqual({
      order_id: 'o1',
      order_version: 3,
      payments: [{ method_id: 'm-cash', tendered: 5000 }],
      document_type: 'ticket',
      ...BLANK_RECIPIENT,
      staff_id: 'st1',
      idempotency_key: expect.stringMatching(/^sale-/),
    });
    expect(s.wrapper.emitted('charged')).toEqual([[SALE]]);
  });

  it('says it is busy while charging, and the button says «Charging…»', async () => {
    const s = await setup();
    let answer!: (r: Response) => void;
    s.net.onApi(() => new Promise<Response>((resolve) => (answer = resolve)));
    await s.type('5', '0');
    await click(s.confirm());
    expect([s.label(), s.confirm().disabled]).toEqual(['Charging…', true]);
    expect(s.wrapper.emitted('busy')).toEqual([[true]]);
    answer(Response.json(SALE));
    await flush();
    expect(s.wrapper.emitted('busy')).toEqual([[true], [false]]);
  });
});

describe('CheckoutPanel: card and other methods (SALE-F02)', () => {
  it('a card charges the exact amount: the hint, and «Charge … by card»', async () => {
    const s = await setup();
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.text('sale-checkout-hint')).toBe('Charge €42.50 on the card terminal, then confirm.');
    expect(s.label()).toBe('Charge €42.50 by card');
    await click(s.confirm());
    expect(s.body().payments).toEqual([{ method_id: 'm-card' }]);
  });

  it('a refusal stays in the sheet, in the server’s words', async () => {
    const s = await setup();
    const message = 'That payment method is not available in this business.';
    s.replies({ '/api/sale/sales': [Response.json({ error: { code: 'sale.payment_method_not_available', message } }, { status: 409 })] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
    expect(s.text('sale-checkout-error')).toBe(message);
    expect(s.wrapper.emitted('charged')).toBeUndefined();
  });
});

describe('CheckoutPanel: split (SALE-F03)', () => {
  it('legs until nothing is left, the change out of cash, one payment per leg', async () => {
    const s = await setup();
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-split').element);
    expect(s.text('sale-checkout-remaining')).toBe('Remaining €42.50');
    expect(s.label()).toBe('€42.50 still to cover');
    await click(s.find('sale-checkout-method-m-card').element);
    await s.type('2', '0');
    await click(s.find('sale-checkout-add-leg').element);
    expect(s.text('sale-checkout-remaining')).toBe('Remaining €22.50');
    await click(s.find('sale-checkout-method-m-cash').element);
    await s.type('3', '0');
    expect(s.text('sale-checkout-change')).toBe('Change €7.50');
    await click(s.find('sale-checkout-add-leg').element);
    expect(s.find('sale-checkout-remaining').attributes('data-covered')).toBe('true');
    expect(s.label()).toBe('Charge €42.50');
    await click(s.confirm());
    expect(s.body().payments).toEqual([
      { method_id: 'm-card', amount: 2000 },
      { method_id: 'm-cash', amount: 2250, tendered: 3000 },
    ]);
  });
});

describe('CheckoutPanel: the legal limits', () => {
  it('from the cash limit on, cash is unavailable: the sheet starts on card and a tap on cash says why', async () => {
    const s = await setup({ preview: preview({ total: 120000 }) });
    expect(s.find('sale-checkout-method-m-cash').attributes('aria-disabled')).toBe('true');
    expect(s.find('sale-checkout-method-m-card').attributes('aria-pressed')).toBe('true');
    await click(s.find('sale-checkout-method-m-cash').element);
    expect(toast).toHaveBeenCalledWith('The law does not allow cash for sales of €1,000.00 or more. Charge it by card or Bizum.', 'warning');
    expect(s.find('sale-checkout-method-m-card').attributes('aria-pressed')).toBe('true');
  });

  it('above the ticket limit: no Receipt, the customer’s details, and «Charge» waits for them', async () => {
    const s = await setup({ preview: preview({ total: 350000 }) });
    expect(s.find('sale-checkout-doc').exists()).toBe(false);
    expect(s.find('sale-checkout-recipient').attributes('data-reason')).toBe('limit');
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.label()).toBe("Enter the customer's details");
    await click(s.confirm());
    expect(toast).toHaveBeenCalledWith("Enter the customer's details", 'warning');
    expect(s.charges()).toEqual([]);
  });
});

describe('CheckoutPanel: receipt or invoice (SALE-F04)', () => {
  it('starts on the settings’ default document', async () => {
    const s = await setup({ settings: { ...SETTINGS, default_document_type: 'invoice' } });
    expect(s.find('sale-checkout-doc-invoice').attributes('aria-pressed')).toBe('true');
    expect(s.wrapper.findComponent(CheckoutSide).props('open')).toBe(true);
  });

  it('starts on Invoice when the settings say so and the customer has a tax id, prefilled', async () => {
    const s = await setup({ props: { customer: CUSTOMER }, settings: { ...SETTINGS, auto_invoice_with_tax_id: true } });
    expect(s.find('sale-checkout-doc-invoice').attributes('aria-pressed')).toBe('true');
    expect(s.find('sale-checkout-recipient').attributes('data-done')).toBe('true');
    const plainCustomer = await setup({ props: { customer: { ...CUSTOMER, customer_tax_id: '' } }, settings: { ...SETTINGS, auto_invoice_with_tax_id: true } });
    expect(plainCustomer.find('sale-checkout-doc-ticket').attributes('aria-pressed')).toBe('true');
  });

  it('an invoice waits for the three details, then charges with them and the customer', async () => {
    const s = await setup({ props: { customer: { ...CUSTOMER, customer_tax_id: '' } } });
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.find('sale-checkout-doc-invoice').element);
    expect(s.label()).toBe("Enter the customer's details");
    await ionValue(s.inDoc('sale-checkout-recipient-tax-id'), 'B12345678', 'ionInput');
    expect(s.label()).toBe('Charge €42.50 by card');
    await click(s.confirm());
    expect(s.body()).toMatchObject({
      document_type: 'invoice',
      customer_id: 'c1',
      customer_name: 'Bar Pepe SL',
      customer_tax_id: 'B12345678',
      customer_address: 'Calle Mayor 1, 28001 Madrid, España',
      customer_country: '',
      customer_id_type: '',
    });
  });

  it('a customer from abroad: country and kind of document travel', async () => {
    const s = await setup({ props: { customer: { ...CUSTOMER, customer_country: 'PT', customer_tax_id: 'PT123456789' } } });
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.find('sale-checkout-doc-invoice').element);
    await ionValue(s.inDoc('sale-checkout-recipient-id-type'), '04');
    await click(s.confirm());
    expect(s.body()).toMatchObject({ document_type: 'invoice', customer_country: 'PT', customer_id_type: '04' });
  });

  it('a blocked tap on an invoice opens the details', async () => {
    const s = await setup({ settings: { ...SETTINGS, default_document_type: 'invoice' } });
    s.wrapper.findComponent(CheckoutSide).vm.$emit('update:open', false);
    await flush();
    await click(s.confirm());
    expect(s.wrapper.findComponent(CheckoutSide).props('open')).toBe(true);
  });
});

describe('CheckoutPanel: a business that requires a customer (SALE-F05)', () => {
  it('without one, says so and does not charge', async () => {
    const s = await setup({ settings: { ...SETTINGS, require_customer: true } });
    await click(s.find('sale-checkout-method-m-card').element);
    expect(s.label()).toBe('Customer required');
    expect(s.text('sale-checkout-block-reason')).toBe('This business requires a customer on every sale. Choose one to carry on with the charge.');
  });
});

describe('CheckoutPanel: a lost answer (SALE-F06)', () => {
  it('nobody knows: says check it in Sales, and «Check in Sales» goes there and closes', async () => {
    const s = await setup();
    s.replies({});
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
    await s.clock.advance(RECOVERY_DELAY_MS);
    await flush();
    expect(s.text('sale-checkout-error')).toBe("We couldn't confirm whether this charge went through. Check it in Sales before charging again.");
    await click(s.find('sale-checkout-check-sales').element);
    expect(s.router.currentRoute.value.path).toBe('/sale/sales');
    expect(s.wrapper.emitted('close')).toEqual([[]]);
  });

  it('charged after all: finishes as a charge', async () => {
    const s = await setup();
    s.replies({ '/api/sale/sales/by_key': [Response.json({ found: true, sale: SALE })] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
    expect(s.wrapper.emitted('charged')).toEqual([[SALE]]);
  });
});

describe('CheckoutPanel: part of the check (SALE-F22)', () => {
  it('values only the lines marked and says how many of the whole check', async () => {
    const s = await setup({ props: { lineIds: ['l1', 'l2'] }, preview: null });
    expect(s.params(PREVIEW_OP)).toEqual([{ order_id: 'o1', line_ids: ['l1', 'l2'] }, { order_id: 'o1' }]);
    await s.push(PREVIEW_OP, preview({ total: 1800, lines_count: 2 }), (p) => 'line_ids' in p);
    await s.push(PREVIEW_OP, preview({ total: 8000, lines_count: 5 }), (p) => !('line_ids' in p));
    expect(s.text('sale-checkout-total')).toBe('€18.00');
    expect(s.text('sale-checkout-partial')).toBe('Paying 2 lines of €80.00');
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
    expect(s.body()).toMatchObject({ order_id: 'o1', line_ids: ['l1', 'l2'] });
  });

  it('one line: «Paying 1 line of …»', async () => {
    const s = await setup({ props: { lineIds: ['l1'] }, preview: null });
    await s.push(PREVIEW_OP, preview({ total: 900, lines_count: 1 }), (p) => 'line_ids' in p);
    await s.push(PREVIEW_OP, preview({ total: 8000 }), (p) => !('line_ids' in p));
    expect(s.text('sale-checkout-partial')).toBe('Paying 1 line of €80.00');
  });
});

describe('CheckoutPanel: the head', () => {
  it('«Charge» and a close button that closes, not while charging', async () => {
    const s = await setup();
    expect(s.text('sale-checkout-title')).toBe('Charge');
    const close = s.find('sale-checkout-close');
    expect(close.attributes('aria-label')).toBe('Close');
    await click(close.element);
    expect(s.wrapper.emitted('close')).toEqual([[]]);
  });

  it('an employee charges too', async () => {
    const s = await setup({ session: EMPLOYEE });
    s.replies({ '/api/sale/sales': [Response.json(SALE)] });
    await click(s.find('sale-checkout-method-m-card').element);
    await click(s.confirm());
    expect(s.wrapper.emitted('charged')).toEqual([[SALE]]);
  });
});

describe('CheckoutPanel: Spanish', () => {
  it('uses the old words', async () => {
    const s = await setup({ locale: 'es', props: { lineIds: ['l1', 'l2'] }, preview: null });
    expect(s.text('sale-checkout-total')).toBe('Calculando el total…');
    await s.push(PREVIEW_OP, preview({ total: 1800 }), (p) => 'line_ids' in p);
    await s.push(PREVIEW_OP, preview({ total: 8000 }), (p) => !('line_ids' in p));
    expect([s.text('sale-checkout-title'), s.text('sale-checkout-total'), s.text('sale-checkout-partial')]).toEqual([
      'Cobrar',
      '18,00 €',
      'Cobrando 2 líneas de 80,00 €',
    ]);
    expect(s.text('sale-checkout-block-reason')).toBe('Marca en el teclado el importe entregado');
    await click(s.find('sale-checkout-split').element);
    expect(s.text('sale-checkout-remaining')).toBe('Restante 18,00 €');
  });
});
