// Fixtures of the till's tests: what the server answers (a product of Inventory, an open check with its
// lines, a preview, the till settings, a page) and the browser's localStorage the test environment lacks.
import type { CategoryOut, ProductOut } from '../../../../../inventory/frontend/operations';
import type { ServiceSaleOut } from '../../../../../service/frontend/operations';
import type { OrderLineOut, OrderOut, OrderRow, PreviewOut, SettingsOut } from '../../../operations';

export const product = (over: Partial<ProductOut> = {}): ProductOut => ({
  id: 'p1',
  name: 'Café con leche',
  sku: 'CAF-1',
  ean13: null,
  description: '',
  product_type: 'physical',
  price: 150,
  cost: 40,
  stock: '10.000',
  low_stock_threshold: '0.000',
  unit: 'ud',
  price_quantity: '1.000',
  pricing_unit: 'ud',
  tax_category_id: 't1',
  tax_category_key: 'food',
  needs_tax_setup: false,
  track_stock: null,
  tracks_stock: false,
  is_active: true,
  category_ids: [],
  created_at: '2026-10-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
  ...over,
});

/** A service of the Services app, as `service.service.list_for_sale` answers it (SALE-F38). */
export const service = (over: Partial<ServiceSaleOut> = {}): ServiceSaleOut => ({
  id: 'sv1',
  name: 'Corte de pelo',
  pricing_type: 'fixed',
  price: 2500,
  min_price: null,
  max_price: null,
  duration_minutes: 45,
  buffer_before: 0,
  buffer_after: 0,
  is_bookable: true,
  allow_online_booking: true,
  category_id: null,
  category_name: null,
  tax_category_id: 't9',
  tax_category_key: 'service.generic',
  needs_tax_setup: false,
  ...over,
});

export const category = (over: Partial<CategoryOut> = {}): CategoryOut => ({
  id: 'c1',
  name: 'Drinks',
  slug: 'drinks',
  description: '',
  icon: '',
  color: '',
  order: 0,
  tax_category_id: null,
  tax_category_key: null,
  product_count: 2,
  ...over,
});

export const line = (over: Partial<OrderLineOut> = {}): OrderLineOut => ({
  id: 'l1',
  position: 1,
  product_id: 'p1',
  department_id: null,
  name: 'Café con leche',
  sku: 'CAF-1',
  is_service: false,
  unit: 'ud',
  quantity: '1.000',
  unit_price: 150,
  price_quantity: '1.000',
  pricing_unit: 'ud',
  tax_category_key: 'food',
  discount_percent: '0.00',
  discount_approved: false,
  is_gift: false,
  gift_reason: '',
  notes: '',
  staff_id: null,
  service_id: null,
  paid_by_voucher: false,
  voucher_session_id: null,
  voucher_grant_id: null,
  voucher_name: '',
  voucher_remaining: null,
  voucher_hold_until: null,
  line_total: 150,
  round_no: 0,
  fired_at: null,
  ...over,
});

export const order = (over: Partial<OrderOut> = {}): OrderOut => {
  const lines = over.lines ?? [line()];
  return {
    id: 'o1',
    status: 'open',
    label: '',
    notes: '',
    appointment_id: null,
    discount_percent: '0.00',
    discount_amount: 0,
    discount_approved: false,
    provisional_total: lines.reduce((sum, l) => sum + l.line_total, 0),
    version: 1,
    lines_count: lines.length,
    created_at: '2026-10-14T09:05:00Z',
    updated_at: '2026-10-14T09:05:00Z',
    already: false,
    ...over,
    lines,
  };
};

export const orderRow = (over: Partial<OrderRow> = {}): OrderRow => ({
  id: 'o2',
  status: 'open',
  label: 'Ana — terrace',
  provisional_total: 1250,
  lines_count: 3,
  appointment_id: null,
  created_at: '2026-10-14T08:30:00',
  updated_at: '2026-10-14T08:30:00',
  ...over,
});

export const preview = (over: Partial<PreviewOut> = {}): PreviewOut => ({
  order_id: 'o1',
  order_version: 1,
  lines_count: 1,
  tax_included: true,
  subtotal: 136,
  tax_total: 14,
  discount_amount: 0,
  discount_percent: '0.00',
  ticket_discount_amount: 0,
  gift_total: 0,
  total: 150,
  breakdown: [{ rate_pct: '10.00', label: 'IVA', tax_type: 'vat', regime: '01', qualification: 'subject', exempt_reason: '', base: 136, tax: 14 }],
  lines: [],
  cash_limit: 100000,
  ticket_limit: 300000,
  ...over,
  operation_total: over.operation_total ?? over.total ?? 150,
});

export const settings = (over: Partial<SettingsOut> = {}): SettingsOut => ({
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
  ...over,
});

/** A page of a list, as every `*.list` answers. */
export const page = <T>(rows: T[], total = rows.length, limit = 100, offset = 0) => ({ rows, total, limit, offset });

/** The browser's localStorage (the test environment has none): `vi.stubGlobal('localStorage', memoryStorage())`. */
export function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() {
      return items.size;
    },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => [...items.keys()][index] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, String(value)),
  };
}

/** A promise answered from the test, to see the screen while a write is in flight. */
export function deferred<T = Response>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

/** The server's refusal envelope. */
export const refused = (code: string, message: string, status = 409) => Response.json({ error: { code, message } }, { status });
