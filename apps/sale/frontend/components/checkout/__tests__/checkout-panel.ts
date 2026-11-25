// Test helper of the charge sheet's content (CheckoutPanel): what the server answers it — the preview of the check, the
// payment methods and the till settings — and its mount with what every test of it reads and presses.
import type { CustomerSnapshot } from '../../../../../customer/frontend/components/CustomerSearch.vue';
import { click, flush, type MountOptions, mountSale, resultFrame } from '../../../__tests__/mount-sale';
import { plain } from '../../../lib/format';
import type { CompleteIn, PaymentMethodOut, PreviewOut, SaleOut, SettingsOut } from '../../../operations';
import CheckoutPanel from '../CheckoutPanel.vue';
import { method } from './methods';

export const PREVIEW_OP = 'sale.checkout.preview';
export const METHODS_OP = 'sale.payment_method.list';
export const SETTINGS_OP = 'sale.pos_settings.get';

export const preview = (over: Partial<PreviewOut> = {}): PreviewOut => ({
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
  limits_currency: 'EUR',
  ...over,
  operation_total: over.operation_total ?? over.total ?? 4250,
});

export const CARD = method('m-card', 'card', 'Card');
export const CASH = method('m-cash', 'cash', 'Cash');
export const TRANSFER: PaymentMethodOut = { ...method('m-transfer', 'transfer', 'Transfer'), allowed: false };
export const METHODS = { rows: [CARD, CASH, TRANSFER], total: 3, limit: 100, offset: 0 };

export const SETTINGS: SettingsOut = {
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

export const CUSTOMER: CustomerSnapshot = {
  customer_id: 'c1',
  customer_name: 'Bar Pepe SL',
  customer_tax_id: 'B12345674',
  customer_address: 'Calle Mayor 1, 28001 Madrid, España',
  customer_country: 'ES',
};

export const SALE = { id: 's1', number: '20261014-0001', total: 4250, already: false } as SaleOut;

export const BLANK_RECIPIENT = { customer_name: '', customer_tax_id: '', customer_address: '', customer_country: '', customer_id_type: '' };

export interface Setup {
  props?: Record<string, unknown>;
  locale?: MountOptions['locale'];
  session?: MountOptions['session'];
  preview?: PreviewOut | null;
  methods?: typeof METHODS | null;
  settings?: SettingsOut | null;
  business?: MountOptions['business'];
}

export async function setup(options: Setup = {}) {
  const m = await mountSale(CheckoutPanel, {
    props: { orderId: 'o1', lineIds: [], orderVersion: 3, customer: null, staffId: null, ...options.props },
    locale: options.locale,
    session: options.session,
    business: options.business,
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
