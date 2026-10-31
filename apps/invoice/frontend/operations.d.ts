// Types of the invoice app's operations for the SDK (`useLive`, `useCommand`), from apps/invoice/schemas.py.
// Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and with `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an invoice's id or number travels in the
// input. Money is whole cents with a sign (a rectifying invoice is negative); decimals (`quantity`,
// rates) are JSON strings on the way out («2.000», «21.00»); dates are ISO `YYYY-MM-DD`.
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';

/** F1 invoice, F2 simplified (ticket), F3 replaces a ticket, R1–R5 rectifying. */
export type InvoiceType = 'F1' | 'F2' | 'F3' | 'R1' | 'R2' | 'R3' | 'R4' | 'R5';
export type InvoiceStatus = 'issued' | 'paid' | 'cancelled';
export type InvoiceSource = 'sale' | 'manual' | 'substitution' | 'rectification' | 'refund' | 'void';
/** The AEAT's IDType of a foreign recipient; '' = a Spanish NIF. */
export type IdType = '' | '02' | '03' | '04' | '05' | '06' | '07';
export type RectificationType = 'R1' | 'R2' | 'R3' | 'R4';

interface PageIn {
  limit?: number;
  offset?: number;
}

/** An invoice by its id or its number. */
export interface InvoiceRefIn {
  invoice_id?: string;
  number?: string;
}

export interface RecipientIn {
  customer_id?: string;
  customer?: string;
  customer_name?: string;
  customer_country?: string;
  customer_id_type?: IdType;
  customer_tax_id?: string;
  customer_address?: string;
}

// ── Invoices ───────────────────────────────────────────────────────────────────────────────────

export interface InvoiceListIn extends PageIn {
  search?: string;
  status?: InvoiceStatus;
  invoice_type?: InvoiceType;
  series_code?: string;
  source_type?: InvoiceSource;
  customer_id?: string;
  issue_date_from?: string;
  issue_date_to?: string;
  total_amount_from?: number;
  total_amount_to?: number;
  sort?: 'issued_at' | 'issue_date' | 'number' | 'customer_name' | 'total_amount' | 'status' | 'invoice_type' | 'series_code';
  dir?: SortDir;
}

export interface BreakdownOut {
  tax: string;
  regime: string;
  qualification: 'subject' | 'subject_reverse' | 'exempt' | 'not_subject' | 'not_subject_location';
  exempt_reason: string;
  rate: string;
  surcharge_rate: string;
  base: number;
  quota: number;
  surcharge_quota: number;
}

export interface InvoiceLineOut {
  id: string;
  position: number;
  description: string;
  quantity: string;
  /** Unit price WITHOUT VAT and before any discount, in cents with two decimals («1000.00»). */
  unit_price: string;
  /** The line's discount WITHOUT VAT, in cents, with its sign (0 = none). */
  discount_amount: number;
  tax_rate: string;
  surcharge_rate: string;
  tax_category_key: string;
  base_amount: number;
  tax_amount: number;
  total_amount: number;
  product_id: string | null;
}

export interface InvoiceLinkOut {
  id: string;
  number: string;
  invoice_type: InvoiceType;
  status: InvoiceStatus;
  issue_date: string;
  total_amount: number;
}

export interface InvoiceRowOut {
  id: string;
  number: string;
  invoice_type: InvoiceType;
  series_code: string;
  year: number;
  issue_date: string;
  issued_at: string;
  customer_name: string;
  customer_tax_id: string;
  base_amount: number;
  tax_amount: number;
  total_amount: number;
  currency: string;
  /** The decimals of its currency as the server counts them (2 in EUR, 0 in JPY): its amounts' minor unit. */
  currency_decimals: number;
  status: InvoiceStatus;
  source_type: InvoiceSource;
  rectifies_id: string | null;
  rectifies_number: string;
  substituted: boolean;
  can_mark_paid: boolean;
  can_rectify: boolean;
  can_substitute: boolean;
}

export interface InvoiceOut extends InvoiceRowOut {
  series_id: string;
  sequence: number;
  operation_date: string;
  issuer_name: string;
  issuer_tax_id: string;
  issuer_address: string;
  issuer_country: string;
  customer_id: string | null;
  customer_address: string;
  customer_country: string;
  customer_id_type: string;
  description: string;
  notes: string;
  tax_breakdown: BreakdownOut[];
  rectification_kind: string;
  sale_id: string | null;
  sale_number: string;
  refund_id: string | null;
  rectifies: InvoiceLinkOut | null;
  substitutes: InvoiceLinkOut | null;
  substituted_by: InvoiceLinkOut | null;
  rectifications: InvoiceLinkOut[];
  remaining: number;
  paid_at: string | null;
  created_by: string;
  lines: InvoiceLineOut[];
  /** What VeriFactu did with it, only in the answer of the operation that issued it. */
  verifactu_status?: VerifactuStatus | null;
}

export type InvoiceGetIn = InvoiceRefIn;

export interface DocumentIn extends InvoiceRefIn {
  duplicate?: boolean;
}

export interface DocumentOut {
  invoice_id: string;
  number: string;
  html: string;
}

/** The A4 page asked of Printing: queued for the system printer, or not (the device prints the screen's paper). */
export interface PaperOut {
  queued: boolean;
  job_id: string | null;
  printer: string | null;
}

/** What a line of a manual invoice starts with when its rate is typed (INVOICE-F03, TAX-F11). */
export type LineDefaultsIn = Record<string, never>;

/** The tax a typed rate is declared with is the territory's, from Taxes (`tax.settings.get`'s `tax_kind`). */
export interface LineDefaultsOut {
  /** The territory's general rate («7.00»), from its own rule in Taxes; `null` without a rule of that tax. */
  tax_rate: string | null;
}

export interface BySourceIn {
  sale_id?: string;
  sale?: string;
}

export interface BySourceOut {
  found: boolean;
  invoice: InvoiceOut | null;
}

export interface ManualLineIn {
  description: string;
  /** Up to three decimals («2», «0.5»). */
  quantity: string | number;
  /** Cents, VAT not included. */
  unit_price: number;
  tax_category_key?: string;
  /** VAT % («21»), when the line has no tax category. */
  tax_rate?: string | number;
  product_id?: string;
}

export interface InvoiceCreateIn extends RecipientIn {
  series_id?: string;
  series_code?: string;
  notes?: string;
  lines: ManualLineIn[];
}

export interface FromSaleIn extends BySourceIn {
  customer_name?: string;
  customer_tax_id?: string;
  customer_address?: string;
  customer_country?: string;
  customer_id_type?: string;
}

export interface SubstituteIn extends InvoiceRefIn, RecipientIn {}

export interface RectificationPreviewIn extends InvoiceRefIn {
  reason: string;
  rectification_type?: RectificationType;
}

export interface RectifyIn extends RectificationPreviewIn {
  issue_date?: string;
}

/** The rectifying invoice a rectification would issue now, before it is issued (INVOICE-F08): its number is the
 *  series' next one, not reserved. */
export interface RectificationPreviewOut {
  original: {
    invoice_id: string;
    number: string;
    invoice_type: string;
    issue_date: string;
    customer_name: string;
    total_amount: number;
    remaining: number;
  };
  invoice_type: string;
  reason: string;
  series_code: string;
  next_number: string;
  issue_date: string;
  whole: boolean;
  base_amount: number;
  tax_amount: number;
  total_amount: number;
  currency: string;
  currency_decimals: number;
  lines: { description: string; quantity: string; tax_rate: string; base_amount: number; total_amount: number }[];
}

export interface FromRefundIn {
  refund_id: string;
}

export interface FromVoidIn {
  sale_id: string;
}

export interface RefundGetIn {
  refund_id: string;
}

/** A refund of the Sales app as Invoicing names it: the sale it gives back and what it gave back. */
export interface RefundOut {
  id: string;
  sale_id: string;
  sale_number: string;
  total: number;
  currency: string;
  currency_decimals: number;
  invoice_number: string;
  /** In the reader's language: «20261014-0003 · €5.00». */
  label: string;
}

export type MarkPaidIn = InvoiceRefIn;

/** sealed: its VeriFactu record is sealed in the same commit; unavailable: no VeriFactu in this business;
 *  pending: VeriFactu refused now and its reaction to `invoice.invoice.issued` seals it later. */
export type VerifactuStatus = 'sealed' | 'unavailable' | 'pending';

export interface IssueOut {
  issued: boolean;
  already: boolean;
  verifactu_status?: VerifactuStatus | null;
  invoice: InvoiceOut | null;
}

// ── Series ─────────────────────────────────────────────────────────────────────────────────────

export interface SeriesListIn extends PageIn {
  search?: string;
  code?: string;
  invoice_type?: InvoiceType;
  year?: number;
  is_active?: boolean;
  is_default?: boolean;
  sort?: 'code' | 'name' | 'invoice_type' | 'year' | 'current_number' | 'prefix' | 'is_active' | 'is_default';
  dir?: SortDir;
}

export interface SeriesOut {
  id: string;
  code: string;
  name: string;
  display_name: string;
  invoice_type: InvoiceType;
  year: number;
  prefix: string;
  format: string;
  current_number: number;
  next_number: string;
  format_locked: boolean;
  is_active: boolean;
  is_default: boolean;
}

export interface SeriesCreateIn {
  code: string;
  name?: string;
  invoice_type: InvoiceType;
  year: number;
  prefix?: string;
  format?: string;
  next_number?: number;
  is_active?: boolean;
  is_default?: boolean;
}

export interface SeriesUpdateIn {
  series_id: string;
  name?: string;
  prefix?: string;
  format?: string;
  next_number?: number;
  is_active?: boolean;
  is_default?: boolean;
}

export interface SeriesPeekIn {
  series_id?: string;
  code?: string;
  year?: number;
}

/** One series as the Series screen shows it, and how it is named outside it. */
export interface SeriesDetailOut extends SeriesOut {
  /** In the reader's language: «FACT · 2026 · Invoices». */
  label: string;
}

export interface SeriesPeekOut {
  series_id: string;
  code: string;
  year: number;
  next_sequence: number;
  next_number: string;
  format_locked: boolean;
}

// ── The numbering ──────────────────────────────────────────────────────────────────────────────

export type NumberingStatusIn = Record<string, never>;

export interface NumberingStatusOut {
  fiscal_year: number;
  ordinary_series: number;
  rectifying_series: number;
  default_series: number;
  total_series: number;
  configured: boolean;
}

export interface GapsIn extends PageIn {
  code?: string;
  year?: number;
}

export interface GapOut {
  series_code: string;
  year: number;
  after_sequence: number;
  missing_from: number;
  next_recorded: number;
  missing_count: number;
}

export interface AllocationsIn extends PageIn {
  search?: string;
  code?: string;
  year?: number;
}

export interface AllocationOut {
  series_code: string;
  year: number;
  sequence: number;
  number: string;
  invoice_id: string;
  invoice_type: InvoiceType;
  issued_at: string;
}

// ── The issuer ─────────────────────────────────────────────────────────────────────────────────

export type IssuerGetIn = Record<string, never>;

export interface IssuerIn {
  legal_name: string;
  country?: string;
  tax_id: string;
  address: string;
  postal_code?: string;
  city?: string;
  province?: string;
}

export interface IssuerOut {
  configured: boolean;
  legal_name: string;
  tax_id: string;
  address: string;
  postal_code: string;
  city: string;
  province: string;
  country: string;
  address_line: string;
  source: 'manual' | 'saas';
  synced_version: number | null;
  synced_at: string | null;
  updated_at: string | null;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'invoice.invoice.list': { input: InvoiceListIn; output: Page<InvoiceRowOut> };
    'invoice.invoice.get': { input: InvoiceGetIn; output: InvoiceOut };
    'invoice.invoice.by_source': { input: BySourceIn; output: BySourceOut };
    'invoice.invoice.document': { input: DocumentIn; output: DocumentOut };
    'invoice.invoice.print': { input: DocumentIn; output: PaperOut };
    'invoice.invoice.line_defaults': { input: LineDefaultsIn; output: LineDefaultsOut };
    'invoice.invoice.create': { input: InvoiceCreateIn; output: InvoiceOut };
    'invoice.invoice.create_from_sale': { input: FromSaleIn; output: IssueOut };
    'invoice.invoice.substitute': { input: SubstituteIn; output: IssueOut };
    'invoice.invoice.mark_paid': { input: MarkPaidIn; output: InvoiceOut };
    'invoice.invoice.rectification_preview': { input: RectificationPreviewIn; output: RectificationPreviewOut };
    'invoice.invoice.rectify': { input: RectifyIn; output: IssueOut };
    'invoice.invoice.rectify_from_refund': { input: FromRefundIn; output: IssueOut };
    'invoice.invoice.rectify_from_void': { input: FromVoidIn; output: IssueOut };
    'invoice.refund.get': { input: RefundGetIn; output: RefundOut };
    'invoice.series.list': { input: SeriesListIn; output: Page<SeriesOut> };
    'invoice.series.peek_next': { input: SeriesPeekIn; output: SeriesPeekOut };
    'invoice.series.get': { input: SeriesPeekIn; output: SeriesDetailOut };
    'invoice.series.create': { input: SeriesCreateIn; output: SeriesOut };
    'invoice.series.update': { input: SeriesUpdateIn; output: SeriesOut };
    'invoice.numbering.status': { input: NumberingStatusIn; output: NumberingStatusOut };
    'invoice.numbering.gaps': { input: GapsIn; output: Page<GapOut> };
    'invoice.numbering.allocations': { input: AllocationsIn; output: Page<AllocationOut> };
    'invoice.issuer.get': { input: IssuerGetIn; output: IssuerOut };
    'invoice.issuer.update': { input: IssuerIn; output: IssuerOut };
  }
}
