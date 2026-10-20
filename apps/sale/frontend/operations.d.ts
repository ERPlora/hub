// Types of the sale app's operations for the SDK (`useLive`, `useCommand`), from apps/sale/schemas.py.
// Written by hand, as the other apps' are, until V3 generates them from `/api/openapi.json`. Keep it in
// step with schemas.py and with `frontend/generated/operations.json`. One input per operation (ninja's
// parity): no path parameters, ids travel in the input. Money is whole cents (numbers); decimals
// (quantities, percentages, rates) are JSON strings on the way out («2.000», «21.00»); dates ISO.
import type { Page } from '../../../frontend/sdk-types';
import type { TerritoryTaxKind } from '../../tax/frontend/operations';

export type SortDir = 'asc' | 'desc';
export type DocumentType = 'ticket' | 'invoice';
export type MethodType = 'cash' | 'card' | 'transfer' | 'other';
export type SaleStatus = 'completed' | 'voided' | 'refunded';
export type OrderStatus = 'open' | 'completed' | 'voided';
export type IdType = '' | '02' | '03' | '04' | '05' | '06' | '07';

interface PageIn {
  limit?: number;
  offset?: number;
}

// ── Settings ─────────────────────────────────────────────────────────────────────────────────────

export interface SettingsFields {
  allow_cash: boolean;
  allow_card: boolean;
  allow_transfer: boolean;
  show_products: boolean;
  show_services: boolean;
  require_customer: boolean;
  allow_discounts: boolean;
  /** 0–100; 100 = no cap. */
  max_discount_percent: number;
  enable_parked_tickets: boolean;
  default_tax_included: boolean;
  auto_invoice_with_tax_id: boolean;
  default_document_type: DocumentType;
  receipt_header: string;
  receipt_footer: string;
  receipt_footer_image: string;
  receipt_marketing_url: string;
  receipt_marketing_text: string;
}

export interface SettingsOut extends SettingsFields {
  /** Empty while the factory values apply. */
  updated_at: string | null;
}

export type SettingsPatchIn = Partial<SettingsFields>;

// ── Payment methods ──────────────────────────────────────────────────────────────────────────────

export interface PaymentMethodListIn extends PageIn {
  search?: string;
}

export interface PaymentMethodOut {
  id: string;
  name: string;
  /** In the reader's language (the factory ones are translated). */
  display_name: string;
  type: MethodType;
  sort_order: number;
  /** Cash: asks what was handed over and gives change. */
  requires_change: boolean;
  /** Whether the till settings let it charge today. */
  allowed: boolean;
}

export interface PaymentMethodIn {
  name: string;
  type?: MethodType;
  sort_order?: number;
}

// ── Departments and quick notes ──────────────────────────────────────────────────────────────────

export interface DepartmentListIn extends PageIn {
  search?: string;
  sort?: 'sort_order' | 'name';
  dir?: SortDir;
}

export interface DepartmentOut {
  id: string;
  name: string;
  tax_category_key: string;
  tax_category_name: string;
  /** Today's rate in the business's country; null without a rule. */
  tax_rate_pct: string | null;
  sort_order: number;
}

export interface DepartmentIn {
  name: string;
  /** Its key, its name or an alias. */
  tax_category_key: string;
  sort_order?: number;
}

/** Which department: its id or its name. */
export interface DepartmentRefIn {
  id?: string;
  department?: string;
}

export interface DepartmentUpdateIn extends DepartmentRefIn {
  name?: string;
  tax_category_key?: string;
  sort_order?: number;
}

export interface QuickNoteListIn extends PageIn {
  search?: string;
  sort?: 'sort_order' | 'text';
  dir?: SortDir;
}

export interface QuickNoteOut {
  id: string;
  text: string;
  sort_order: number;
}

export interface QuickNoteIn {
  text: string;
  sort_order?: number;
}

export interface QuickNoteRefIn {
  id?: string;
  quick_note?: string;
}

export interface QuickNoteUpdateIn extends QuickNoteRefIn {
  text?: string;
  sort_order?: number;
}

// ── Open checks ──────────────────────────────────────────────────────────────────────────────────

interface LineFields {
  /** In the product's unit («0.532»); 1 by default. */
  quantity?: string | number;
  notes?: string;
  staff_id?: string | null;
  is_gift?: boolean;
  gift_reason?: string;
}

/** A catalog line: its id, or its SKU or name. */
export interface ProductLineIn extends LineFields {
  product_id?: string;
  product?: string;
  /** SALE-F11: the options of Modifiers chosen, in the order chosen (one chosen twice, twice). */
  option_ids?: string[];
}

/** An open-price line: the amount typed and a department (or a tax category without departments). */
export interface OpenLineIn extends LineFields {
  unit_price: number;
  department_id?: string;
  department?: string;
  tax_category_key?: string;
  name?: string;
}

/**
 * A service of the Services app: its id or its name; `unit_price` only when it has no fixed price. A fixed
 * price is the professional's own (`staff_id`) or the service's. `booked_price`: what the check's
 * appointment booked, checked against it (lower only with the open-price right).
 */
export interface ServiceLineIn extends LineFields {
  service_id?: string;
  service?: string;
  unit_price?: number;
  booked_price?: number;
}

/** SALE-F12: a dish picked in a menu of Menus, by the choice's id (or its product and course). */
export interface ComboChoiceIn {
  option_id?: string;
  product?: string;
  group?: string;
  /** Picks of it in one menu. */
  quantity?: number;
}

/** SALE-F12: a menu of Menus with its dishes; Menus checks and prices it on the server. */
export interface ComboLineIn extends LineFields {
  combo_id?: string;
  combo?: string;
  choices: ComboChoiceIn[];
}

export interface OrderOpenIn {
  label?: string;
  notes?: string;
  appointment_id?: string | null;
  lines?: ProductLineIn[];
  open_lines?: OpenLineIn[];
  service_lines?: ServiceLineIn[];
  combo_lines?: ComboLineIn[];
}

export interface OrderRefIn {
  order_id: string;
}

export interface OrderAddLineIn extends ProductLineIn {
  order_id: string;
}

export interface OrderAddOpenLineIn extends OpenLineIn {
  order_id: string;
}

export interface OrderAddServiceLineIn extends ServiceLineIn {
  order_id: string;
}

export interface OrderAddComboLineIn extends ComboLineIn {
  order_id: string;
}

export interface OrderLineRefIn {
  order_id: string;
  line_id: string;
}

/** SALE-F27: one session of the customer's voucher (Services) pays the line. */
export interface OrderApplyVoucherIn extends OrderLineRefIn {
  grant_id: string;
}

export interface OrderUpdateLineIn extends OrderLineRefIn {
  quantity?: string | number;
  is_gift?: boolean;
  gift_reason?: string;
  /** Empty text clears it; absent keeps it. */
  notes?: string;
}

export interface OrderSetLineStaffIn extends OrderLineRefIn {
  staff_id: string | null;
}

export interface OrderVoidLineIn extends OrderLineRefIn {
  reason: string;
}

export interface OrderSplitIn {
  order_id: string;
  line_ids?: string[];
  label?: string;
}

export interface OrderMergeIn {
  from_order_id: string;
  to_order_id: string;
}

export interface OrderSetDiscountIn {
  order_id: string;
  discount_percent: string | number;
  /** Cents; absent keeps the one the check has. */
  discount_amount?: number;
}

export interface OrderSetLineDiscountIn extends OrderLineRefIn {
  discount_percent: string | number;
}

export interface OrderSetLabelIn {
  order_id: string;
  label: string;
}

export interface OrderSetAppointmentIn {
  order_id: string;
  appointment_id: string | null;
}

export interface OrderFireIn {
  order_id: string;
  label?: string;
  channel?: 'dine_in' | 'takeaway' | 'delivery';
  priority?: string;
}

export interface OrderListIn extends PageIn {
  /** open by default. */
  status?: OrderStatus | null;
  search?: string;
}

export interface OrderLineOut {
  id: string;
  position: number;
  product_id: string | null;
  department_id: string | null;
  name: string;
  sku: string;
  is_service: boolean;
  unit: string;
  quantity: string;
  /** Frozen price in cents, per `price_quantity` of `pricing_unit`. */
  unit_price: number;
  price_quantity: string;
  pricing_unit: string;
  tax_category_key: string;
  discount_percent: string;
  discount_approved: boolean;
  is_gift: boolean;
  gift_reason: string;
  notes: string;
  staff_id: string | null;
  /** Services' service, if it is one. */
  service_id: string | null;
  /** A session of a customer's voucher pays it: charged at 0. */
  paid_by_voucher: boolean;
  voucher_session_id: string | null;
  voucher_grant_id: string | null;
  /** The voucher's name, as it was applied. */
  voucher_name: string;
  /** Sessions the voucher had left after this one when applied; null = unlimited. */
  voucher_remaining: number | null;
  /** Until when the session stays held for the line. */
  voucher_hold_until: string | null;
  /** Provisional, before the ticket discount. */
  line_total: number;
  /** Kitchen round; 0 = pending. */
  round_no: number;
  fired_at: string | null;
  /** SALE-F11: the options chosen, frozen when it was ordered, in the order chosen. */
  modifiers: ModifierPickOut[];
  /** The options of another tax category, each charged on a child line of its own. */
  modifier_lines: ModifierLineOut[];
  /** What the kitchen reads under the dish. */
  kitchen_text: string;
  /** SALE-F12: a menu of Menus, its dishes and how it is charged, frozen when it was ordered. */
  combo: ComboLineOut | null;
}

export interface ComboDishOut {
  option_id: string;
  group_name: string;
  product_id: string;
  product_name: string;
  category_id: string | null;
  is_service: boolean;
  /** Picks of it in one menu. */
  quantity: number;
  price_delta: number;
  tax_category_key: string | null;
  /** Its part of one menu's amount, in cents, when the menu is split. */
  amount: number | null;
}

export interface ComboLineOut {
  combo_id: string;
  kitchen_name: string;
  supply_kind: 'service' | 'goods';
  /** Charged as one line per dish, each at its own VAT. */
  split: boolean;
  components: ComboDishOut[];
}

export interface ModifierPickOut {
  option_id: string;
  group_id: string;
  group_name: string;
  name: string;
  kitchen_name: string;
  price_delta: number;
  tax_category_key: string | null;
  own_line: boolean;
}

export interface ModifierLineOut {
  option_id: string;
  name: string;
  tax_category_key: string;
  unit_price: number;
  /** How many per unit of the dish. */
  quantity: number;
}

export interface OrderOut {
  id: string;
  status: OrderStatus;
  label: string;
  notes: string;
  appointment_id: string | null;
  discount_percent: string;
  discount_amount: number;
  discount_approved: boolean;
  provisional_total: number;
  /** Send it with the charge: a newer one refuses the charge. */
  version: number;
  lines_count: number;
  created_at: string;
  updated_at: string;
  /** The lines left to charge. */
  lines: OrderLineOut[];
  /** Opening the check of an appointment that already had one answers that one (nothing added). */
  already: boolean;
}

export interface OrderRow {
  id: string;
  status: OrderStatus;
  label: string;
  provisional_total: number;
  lines_count: number;
  appointment_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface SplitLineOut {
  order: OrderOut;
  new_line_ids: string[];
}

export interface OrderSplitOut {
  order: OrderOut;
  new_order: OrderOut;
}

export interface OrderFireOut {
  order: OrderOut;
  round_no: number;
  lines_count: number;
}

// ── Charging ─────────────────────────────────────────────────────────────────────────────────────

/** An open check (all its lines or `line_ids`) or loose lines; never both. */
export interface ChargeLinesIn {
  order_id?: string;
  line_ids?: string[];
  lines?: ProductLineIn[];
  open_lines?: OpenLineIn[];
  service_lines?: ServiceLineIn[];
  combo_lines?: ComboLineIn[];
  /** Counter sale only. */
  discount_percent?: string | number;
  /** Counter sale only, cents. */
  discount_amount?: number;
}

export type PreviewIn = ChargeLinesIn;

export interface PaymentIn {
  method_id?: string;
  /** Its name or its type (cash, card…). */
  method?: string;
  /** Cents; absent = what is left to pay. */
  amount?: number;
  /** Cash: what was handed over. */
  tendered?: number;
  reference?: string;
}

export interface CompleteIn extends ChargeLinesIn {
  /** Born when the charge sheet opens and reused on every retry. */
  idempotency_key: string;
  order_version?: number;
  payments?: PaymentIn[];
  document_type?: DocumentType;
  customer_id?: string;
  /** Name, phone or email when the id is not known. */
  customer?: string;
  customer_name?: string;
  customer_tax_id?: string;
  customer_address?: string;
  customer_country?: string;
  customer_id_type?: IdType;
  staff_id?: string | null;
  appointment_id?: string | null;
  notes?: string;
}

/** One row per fiscal key (tax, regime, qualification, exemption cause, rates) and component. */
export interface BreakdownOut {
  rate_pct: string;
  label: string;
  /** vat, surcharge, igic, ipsi… */
  tax_type: string;
  /** VAT regime key (01 = general). */
  regime: string;
  qualification: 'subject' | 'subject_reverse' | 'exempt' | 'not_subject' | 'not_subject_location' | string;
  /** E1–E8 on an exempt key. */
  exempt_reason: string;
  base: number;
  tax: number;
}

/** What Invoicing answered for the fiscal document of a write; empty on a sale charged before. */
export type FiscalStatus = '' | 'issued' | 'pending' | 'unavailable' | 'none';

export interface PreviewLineOut {
  order_line_id: string | null;
  name: string;
  quantity: string;
  unit: string;
  unit_price: number;
  discount_percent: string;
  is_gift: boolean;
  service_id: string | null;
  paid_by_voucher: boolean;
  voucher_name: string;
  voucher_remaining: number | null;
  tax_category_key: string;
  tax_rate: string;
  net_amount: number;
  tax_amount: number;
  line_total: number;
  /** The options charged inside the line. */
  modifiers: string[];
  /** An option of another tax category, charged on a line of its own under its dish. */
  is_child: boolean;
  /** SALE-F12: the menu this line charges, or a dish of (split per dish); empty otherwise. */
  combo_name: string;
  /** The dishes of a menu charged in one line. */
  components: string[];
}

export interface PreviewOut {
  order_id: string | null;
  order_version: number | null;
  lines_count: number;
  tax_included: boolean;
  subtotal: number;
  tax_total: number;
  /** Every discount given. */
  discount_amount: number;
  discount_percent: string;
  ticket_discount_amount: number;
  gift_total: number;
  total: number;
  breakdown: BreakdownOut[];
  lines: PreviewLineOut[];
  /** The whole operation the cash limit looks at: on a check charged in parts, what it already charged
   *  plus all it has left (Ley 7/2012, art. 7); otherwise `total`. */
  operation_total: number;
  /** From this operation total on, no cash at all (Spain: 100000); null = no limit. */
  cash_limit: number | null;
  /** Above this total, only an invoice (Spain: 300000); null = no limit. */
  ticket_limit: number | null;
}

export interface SaleLineOut {
  id: string;
  position: number;
  order_line_id: string | null;
  product_id: string | null;
  department_id: string | null;
  name: string;
  sku: string;
  is_service: boolean;
  unit: string;
  quantity: string;
  unit_price: number;
  price_quantity: string;
  pricing_unit: string;
  discount_percent: string;
  is_gift: boolean;
  gift_reason: string;
  notes: string;
  staff_id: string | null;
  service_id: string | null;
  /** A voucher session paid it (at 0). */
  paid_by_voucher: boolean;
  voucher_name: string;
  tax_category_key: string;
  tax_rate: string;
  tax_country_code: string;
  tax_region_code: string;
  tax_rule_id: string | null;
  net_amount: number;
  tax_amount: number;
  line_total: number;
  returned_quantity: string;
  /** The options charged inside the line (the receipt prints them under it). */
  modifiers: string[];
  /** The dish line an option of another tax category hangs from. */
  parent_line_id: string | null;
  /** SALE-F12: the menu this line charges, or a dish of; its name heads its dishes on the receipt. */
  combo_id: string | null;
  combo_name: string;
  components: SaleDishOut[];
}

export interface SaleDishOut {
  product_id: string;
  product_name: string;
  /** How many in one menu. */
  quantity: number;
}

export interface SalePaymentOut {
  id: string;
  position: number;
  method_id: string;
  method_name: string;
  method_type: MethodType;
  amount: number;
  tendered: number;
  change: number;
  reference: string;
}

export interface SaleOut {
  id: string;
  number: string;
  business_day: string;
  status: SaleStatus;
  document_type: DocumentType;
  order_id: string | null;
  customer_id: string | null;
  customer_name: string;
  staff_id: string | null;
  appointment_id: string | null;
  tax_included: boolean;
  currency: string;
  subtotal: number;
  tax_total: number;
  discount_percent: string;
  discount_amount: number;
  gift_total: number;
  total: number;
  tendered_total: number;
  change_total: number;
  refunded_total: number;
  refundable_total: number;
  /** Lines paid with a voucher whose session has not come back yet. */
  sessions_to_return: number;
  payment_method_name: string;
  breakdown: BreakdownOut[];
  notes: string;
  voided_at: string | null;
  voided_by: string;
  void_reason: string;
  created_at: string;
  created_by: string;
  lines: SaleLineOut[];
  payments: SalePaymentOut[];
  /** Its ticket (F2) or invoice (F1), issued by Invoicing in the same charge. */
  invoice_status: FiscalStatus;
  invoice_id: string | null;
  /** TICKET-2026-000001, FACT-2026-000001; empty while it has none. The paper prints it. */
  invoice_number: string;
  invoice_type: string;
  /** The rectifying invoice of its void (R5). */
  void_invoice_status: FiscalStatus;
  void_invoice_number: string;
  /** A fiscal document of it waits (its own, its void's or a refund's): «Issue now» issues it. */
  documents_pending: boolean;
  /** True: this attempt had already been charged; nothing new was recorded. */
  already: boolean;
}

/** Which sale: its id or its number. */
export interface SaleRefIn {
  sale_id?: string;
  sale?: string;
}

export interface SaleByKeyIn {
  idempotency_key: string;
}

export interface SaleByKeyOut {
  found: boolean;
  sale: SaleOut | null;
}

export interface SaleListIn extends PageIn {
  search?: string;
  status?: SaleStatus;
  payment_method_name?: string;
  customer_name?: string;
  customer_id?: string;
  staff_id?: string;
  number?: string;
  date_from?: string;
  date_to?: string;
  total_min?: number;
  total_max?: number;
  sort?: 'created_at' | 'number' | 'total' | 'customer_name' | 'status' | 'payment_method_name';
  dir?: SortDir;
}

export interface SaleRow {
  id: string;
  number: string;
  business_day: string;
  created_at: string;
  status: SaleStatus;
  document_type: DocumentType;
  customer_id: string | null;
  customer_name: string;
  payment_method_name: string;
  staff_id: string | null;
  total: number;
  tax_total: number;
  refunded_total: number;
  refundable_total: number;
  /** Lines paid with a voucher whose session has not come back yet. */
  sessions_to_return: number;
  /** It has a refund, also one of no money (a voucher's session): refunded, never voided. */
  has_refunds: boolean;
  /** Its fiscal document (issued, pending, unavailable, none; empty before Sales asked for one). */
  invoice_status: FiscalStatus;
  /** A fiscal document of it waits (its own, its void's or a refund's): «Issue now» issues it. */
  documents_pending: boolean;
}

export interface PeriodIn {
  date_from?: string;
  date_to?: string;
}

export interface StatsOut {
  count: number;
  /** Refunds taken off. */
  total_revenue: number;
  avg_ticket: number;
  net_total: number;
  tax_total: number;
  discount_total: number;
  refunded_total: number;
  voided_count: number;
  /** The tax the period's sales were declared with, what its tax figure is named by; `null` when they
   *  declared more than one (or another tax). Without sales, the business territory's. */
  tax_kind: TerritoryTaxKind | null;
}

export interface TodayOut {
  day: string;
  total: number;
  tickets: number;
}

export interface LastDaysOut {
  rows: { day: string; total: number }[];
}

export interface ByStaffOut {
  /** `refunded_total`: what refunds gave back on their lines; `total_revenue`: gross minus that, what a
   *  commission is on. One row per professional, the most revenue first. */
  rows: {
    staff_id: string;
    sales_count: number;
    gross_total: number;
    net_total: number;
    tax_total: number;
    refunded_total: number;
    total_revenue: number;
  }[];
}

export interface BusinessDayOut {
  today: string;
}

// ── Voids and refunds ────────────────────────────────────────────────────────────────────────────

export interface VoidIn extends SaleRefIn {
  reason: string;
}

export interface AllocationIn {
  payment_id: string;
  amount: number;
  to_method_id?: string;
}

export interface RefundLineIn {
  line_id: string;
  /** Units; absent = all that is left. */
  quantity?: string | number;
}

export interface RefundIn extends SaleRefIn {
  reason: string;
  note?: string;
  idempotency_key?: string;
  /** None = no money: only the session of a voucher comes back. */
  allocations?: AllocationIn[];
  lines?: RefundLineIn[];
}

export interface RefundOut {
  already: boolean;
  refund_id: string;
  sale_id: string;
  total: number;
  fully_refunded: boolean;
  /** Its rectifying invoice, issued by Invoicing in the same refund. */
  invoice_status: FiscalStatus;
  invoice_number: string;
  invoice_type: string;
}

export interface TenderOption {
  payment_id: string;
  position: number;
  method_id: string;
  method_name: string;
  method_type: MethodType;
  charged: number;
  refunded: number;
  remaining: number;
  refundable: boolean;
  reason: '' | 'already_refunded' | 'method_unavailable';
}

export interface LineOption {
  line_id: string;
  name: string;
  unit: string;
  quantity: string;
  returned: string;
  left: string;
  line_total: number;
  is_gift: boolean;
  /** A voucher session paid it: returning it gives the session back. */
  paid_by_voucher: boolean;
  voucher_name: string;
}

export interface RefundOptionsOut {
  sale_id: string;
  number: string;
  status: SaleStatus;
  total: number;
  refunded_total: number;
  refundable_total: number;
  tenders: TenderOption[];
  lines: LineOption[];
}

export interface RefundRow {
  id: string;
  sale_id: string;
  total: number;
  reason: string;
  note: string;
  created_at: string;
  created_by: string;
  /** Its rectifying invoice: issued, pending (waits: «Issue now»), unavailable or none. */
  invoice_status: FiscalStatus;
  invoice_number: string;
  invoice_type: string;
}

export interface RefundByKeyIn {
  idempotency_key: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'sale.sale.list': { input: SaleListIn; output: Page<SaleRow> };
    'sale.sale.get': { input: SaleRefIn; output: SaleOut };
    'sale.sale.by_idempotency_key': { input: SaleByKeyIn; output: SaleByKeyOut };
    'sale.sale.stats': { input: PeriodIn; output: StatsOut };
    'sale.sale.today': { input: Record<string, never>; output: TodayOut };
    'sale.sale.last_7_days': { input: Record<string, never>; output: LastDaysOut };
    'sale.sale.by_staff': { input: PeriodIn; output: ByStaffOut };
    'sale.sale.complete': { input: CompleteIn; output: SaleOut };
    'sale.sale.complete_over_limit': { input: CompleteIn; output: SaleOut };
    'sale.sale.void': { input: VoidIn; output: SaleOut };
    'sale.sale.refund': { input: RefundIn; output: RefundOut };
    'sale.sale.issue_documents': { input: SaleRefIn; output: SaleOut };
    'sale.checkout.preview': { input: PreviewIn; output: PreviewOut };
    'sale.order.list': { input: OrderListIn; output: Page<OrderRow> };
    'sale.order.get': { input: OrderRefIn; output: OrderOut };
    'sale.order.open': { input: OrderOpenIn; output: OrderOut };
    'sale.order.add_line': { input: OrderAddLineIn; output: OrderOut };
    'sale.order.add_open_line': { input: OrderAddOpenLineIn; output: OrderOut };
    'sale.order.add_service_line': { input: OrderAddServiceLineIn; output: OrderOut };
    'sale.order.add_combo_line': { input: OrderAddComboLineIn; output: OrderOut };
    'sale.order.apply_voucher': { input: OrderApplyVoucherIn; output: OrderOut };
    'sale.order.remove_voucher': { input: OrderLineRefIn; output: OrderOut };
    'sale.order.update_line': { input: OrderUpdateLineIn; output: OrderOut };
    'sale.order.set_line_staff': { input: OrderSetLineStaffIn; output: OrderOut };
    'sale.order.split_line': { input: OrderLineRefIn; output: SplitLineOut };
    'sale.order.remove_line': { input: OrderLineRefIn; output: OrderOut };
    'sale.order.void_line': { input: OrderVoidLineIn; output: OrderOut };
    'sale.order.fire': { input: OrderFireIn; output: OrderFireOut };
    'sale.order.split': { input: OrderSplitIn; output: OrderSplitOut };
    'sale.order.merge': { input: OrderMergeIn; output: OrderOut };
    'sale.order.void': { input: OrderRefIn; output: OrderOut };
    'sale.order.set_discount': { input: OrderSetDiscountIn; output: OrderOut };
    'sale.order.set_discount_over_limit': { input: OrderSetDiscountIn; output: OrderOut };
    'sale.order.set_line_discount': { input: OrderSetLineDiscountIn; output: OrderOut };
    'sale.order.set_line_discount_over_limit': { input: OrderSetLineDiscountIn; output: OrderOut };
    'sale.order.set_label': { input: OrderSetLabelIn; output: OrderOut };
    'sale.order.set_appointment': { input: OrderSetAppointmentIn; output: OrderOut };
    'sale.payment_method.list': { input: PaymentMethodListIn; output: Page<PaymentMethodOut> };
    'sale.payment_method.create': { input: PaymentMethodIn; output: PaymentMethodOut };
    'sale.settings.get': { input: Record<string, never>; output: SettingsOut };
    'sale.settings.update': { input: SettingsPatchIn; output: SettingsOut };
    'sale.pos_settings.get': { input: Record<string, never>; output: SettingsOut };
    'sale.department.list': { input: DepartmentListIn; output: Page<DepartmentOut> };
    'sale.department.create': { input: DepartmentIn; output: DepartmentOut };
    'sale.department.update': { input: DepartmentUpdateIn; output: DepartmentOut };
    'sale.department.delete': { input: DepartmentRefIn; output: DepartmentOut };
    'sale.quick_note.list': { input: QuickNoteListIn; output: Page<QuickNoteOut> };
    'sale.quick_note.create': { input: QuickNoteIn; output: QuickNoteOut };
    'sale.quick_note.update': { input: QuickNoteUpdateIn; output: QuickNoteOut };
    'sale.quick_note.delete': { input: QuickNoteRefIn; output: QuickNoteOut };
    'sale.business_day.get': { input: Record<string, never>; output: BusinessDayOut };
    'sale.refund.options': { input: SaleRefIn; output: RefundOptionsOut };
    'sale.refund.list': { input: SaleRefIn; output: { rows: RefundRow[] } };
    'sale.refund.by_idempotency_key': { input: RefundByKeyIn; output: { found: boolean; refund: RefundRow | null } };
  }
}
