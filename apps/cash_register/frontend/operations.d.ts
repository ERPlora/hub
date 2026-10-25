// Types of the cash register app's operations for the SDK (`useLive`, `useCommand`), from
// apps/cash_register/schemas.py. Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3
// generates them from `/api/openapi.json`. Keep it in step with schemas.py and with
// `frontend/generated/operations.json`. One input per operation (ninja's parity): no path parameters.
// Money is whole cents; dates and times are ISO 8601 strings.
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type MethodType = 'cash' | 'card' | 'transfer' | 'other';
export type SessionStatus = 'open' | 'closed';
export type MovementType = 'in' | 'out' | 'sale' | 'refund' | 'void';
export type ManualType = 'in' | 'out';
export type CountType = 'opening' | 'closing';

interface PageIn {
  limit?: number;
  offset?: number;
}

type EmptyIn = Record<string, never>;

// ── Settings ─────────────────────────────────────────────────────────────────────────────────

export interface SettingsFields {
  enable_cash_register: boolean;
  require_opening_balance: boolean;
  require_closing_balance: boolean;
  allow_negative_balance: boolean;
  require_blind_count: boolean;
  auto_close_enabled: boolean;
  /** «04:00»: a whole hour. */
  auto_close_time: string;
}

export interface SettingsOut extends SettingsFields {
  updated_at: string | null;
}

export type SettingsPatchIn = Partial<SettingsFields>;

// ── Drawers ──────────────────────────────────────────────────────────────────────────────────

export interface RegisterListIn extends PageIn {
  search?: string;
  is_active?: boolean;
}

export interface RegisterOut {
  id: string;
  name: string;
  is_active: boolean;
}

export interface RegisterIn {
  name: string;
}

export interface RegisterUpdateIn {
  register_id?: string;
  register_name?: string;
  name?: string;
  is_active?: boolean;
}

// ── Sessions ─────────────────────────────────────────────────────────────────────────────────

export interface SessionRefIn {
  session_id?: string;
  session?: string;
}

export interface SessionListIn extends PageIn {
  search?: string;
  number?: string;
  status?: SessionStatus;
  register_id?: string;
  opened_from?: string;
  opened_to?: string;
  opening_min?: number;
  opening_max?: number;
  expected_min?: number;
  expected_max?: number;
  counted_min?: number;
  counted_max?: number;
  difference_min?: number;
  difference_max?: number;
  sort?: 'opened_at' | 'number' | 'status' | 'opening_balance' | 'expected_balance' | 'closing_balance' | 'difference' | 'closed_at';
  dir?: SortDir;
}

export interface SessionRow {
  id: string;
  number: string;
  business_day: string;
  status: SessionStatus;
  register_id: string | null;
  register_name: string;
  opened_at: string;
  opened_by: string;
  opening_balance: number;
  closed_at: string | null;
  closed_by: string;
  closing_balance: number | null;
  /** Live while open (null when a blind count hides it), frozen once closed. */
  expected_balance: number | null;
  difference: number | null;
  auto_closed: boolean;
  expected_hidden: boolean;
  auto_close_due: boolean;
}

export interface SessionSummary {
  movement_count: number;
  opening_balance: number;
  total_sales: number | null;
  cash_sales: number | null;
  card_sales: number | null;
  other_sales: number | null;
  total_refunds: number | null;
  total_cash_in: number | null;
  total_cash_out: number | null;
  total_gifts: number | null;
  expected_cash: number | null;
  counted: number | null;
  difference: number | null;
}

export interface SessionOut extends SessionRow {
  opening_notes: string;
  closing_notes: string;
  summary: SessionSummary;
}

export interface CurrentOut {
  required: boolean;
  session: SessionRow | null;
  auto_close_at: string | null;
  unassigned_count: number;
  unassigned_cash: number;
}

/** «Print» of a session's report (CASH_REGISTER-F16): x while open, z once closed. */
export interface SessionPrintOut {
  report: 'x' | 'z';
  /** It went to the receipt printer's queue; false = Printing is not on here: the browser prints it. */
  queued: boolean;
  job_id: string | null;
  /** The printer that prints it; null = the first device with a receipt printer. */
  printer: string | null;
}

export interface SessionGetIn {
  session_id?: string;
  session?: string;
}

export interface SessionOpenIn {
  register_id?: string;
  register_name?: string;
  opening_balance?: number;
  opening_notes?: string;
}

export interface SessionCloseIn extends SessionRefIn {
  closing_balance?: number;
  closing_notes?: string;
}

export interface ClosingSummaryIn extends SessionRefIn {
  closing_balance?: number;
}

/** What is still open when the drawer closes (CASH_REGISTER-F08). */
export interface ShiftReviewOut {
  open_checks: number;
  open_check_labels: string[];
  unserved: number;
  unserved_labels: string[];
  prints: number;
  print_usages: string[];
  incomplete: boolean;
}

/** The close's summary before it runs (CASH_REGISTER-F09): the expected and the difference are null for whoever a
 *  blind count hides them from. */
export interface ClosingSummaryOut {
  session_id: string;
  number: string;
  register_name: string;
  opened_at: string;
  opened_by: string;
  opening_balance: number;
  closing_balance: number | null;
  expected_balance: number | null;
  difference: number | null;
  expected_hidden: boolean;
  require_closing_balance: boolean;
  pending: ShiftReviewOut;
}

export interface AutoCloseOut {
  closed: SessionRow[];
}

// ── Movements and counts ─────────────────────────────────────────────────────────────────────

export interface MovementListIn extends PageIn {
  session_id?: string;
  session?: string;
  unassigned?: boolean;
  search?: string;
  type?: MovementType;
  method_type?: MethodType;
  amount_min?: number;
  amount_max?: number;
  sort?: 'created_at' | 'amount' | 'type' | 'method_type';
  dir?: SortDir;
}

export interface MovementRow {
  key: string;
  session_id: string | null;
  type: MovementType;
  amount: number;
  signed_amount: number;
  method_type: MethodType;
  method_name: string;
  description: string;
  sale_id: string | null;
  sale_number: string;
  document_type: string;
  gift_total: number;
  created_at: string;
  created_by: string;
}

export interface MovementAddIn extends SessionRefIn {
  type: ManualType;
  amount: number;
  method_type?: MethodType;
  description?: string;
}

export interface Denominations {
  bills?: Record<string, number>;
  coins?: Record<string, number>;
}

export interface CountListIn extends PageIn {
  session_id?: string;
  session?: string;
  sort?: 'counted_at' | 'total' | 'type';
  dir?: SortDir;
}

export interface CountOut {
  id: string;
  session_id: string;
  type: CountType;
  total: number;
  denominations: Denominations;
  notes: string;
  counted_at: string;
  counted_by: string;
}

export interface CountAddIn extends SessionRefIn {
  type?: CountType;
  denominations?: Denominations;
  total?: number;
  notes?: string;
}

export interface CurrencyOut {
  currency: string;
  decimals: number;
  bills: string[];
  coins: string[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'cash_register.settings.get': { input: EmptyIn; output: SettingsOut };
    'cash_register.settings.update': { input: SettingsPatchIn; output: SettingsOut };
    'cash_register.register.list': { input: RegisterListIn; output: Page<RegisterOut> };
    'cash_register.register.create': { input: RegisterIn; output: RegisterOut };
    'cash_register.register.update': { input: RegisterUpdateIn; output: RegisterOut };
    'cash_register.session.list': { input: SessionListIn; output: Page<SessionRow> };
    'cash_register.session.current': { input: EmptyIn; output: CurrentOut };
    'cash_register.session.get': { input: SessionGetIn; output: SessionOut };
    'cash_register.session.print': { input: SessionGetIn; output: SessionPrintOut };
    'cash_register.session.open': { input: SessionOpenIn; output: SessionRow };
    'cash_register.session.closing_summary': { input: ClosingSummaryIn; output: ClosingSummaryOut };
    'cash_register.session.close': { input: SessionCloseIn; output: SessionRow };
    'cash_register.session.auto_close': { input: EmptyIn; output: AutoCloseOut };
    'cash_register.movement.list': { input: MovementListIn; output: Page<MovementRow> };
    'cash_register.movement.add': { input: MovementAddIn; output: MovementRow };
    'cash_register.count.list': { input: CountListIn; output: Page<CountOut> };
    'cash_register.count.add': { input: CountAddIn; output: CountOut };
    'cash_register.currency.get': { input: EmptyIn; output: CurrencyOut };
  }
}
