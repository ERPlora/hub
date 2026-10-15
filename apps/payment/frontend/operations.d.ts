// Types of the payment app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/payment/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py (tests/test_queries.py compares the list inputs)
// and `frontend/generated/operations.json`. One input per operation (ninja's parity): no path
// parameters, an id travels in the input. On the wire: money in whole minor units of its currency,
// days `YYYY-MM-DD`, moments ISO 8601.
import type { Page } from '../../../frontend/sdk-types';

export type MethodType = 'cash' | 'transfer' | 'card' | 'sepa' | 'check' | 'other';
export type PaymentStatus = 'draft' | 'approved' | 'sent' | 'completed' | 'cancelled';

export interface PageIn {
  limit?: number;
  offset?: number;
}

// ── Methods ────────────────────────────────────────────────────────────────────────────────────

export interface MethodRefIn {
  id?: string | null;
  method?: string | null;
}

export interface MethodListIn extends PageIn {
  search?: string;
  method_type?: MethodType;
  is_active?: boolean;
  /** A column, `-` first for descending. */
  sort?: string;
}

export interface MethodIn {
  name: string;
  method_type?: MethodType;
  bank_account_ref?: string;
}

/** Only the fields sent change. */
export interface MethodPatchIn extends MethodRefIn {
  name?: string | null;
  method_type?: MethodType | null;
  bank_account_ref?: string | null;
}

export interface MethodOut {
  id: string;
  name: string;
  method_type: MethodType;
  /** Masked in the list; whole only from `payment.method.get`. */
  bank_account_ref: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ── Payments ───────────────────────────────────────────────────────────────────────────────────

export interface PaymentRefIn {
  id?: string | null;
  reference?: string | null;
}

export interface CancelIn extends PaymentRefIn {
  reason: string;
}

export interface PaymentListIn extends PageIn {
  search?: string;
  reference?: string;
  beneficiary_name?: string;
  concept?: string;
  method_id?: string;
  method?: string;
  status?: PaymentStatus;
  currency?: string;
  beneficiary_iban?: string;
  supplier_invoice_ref?: string;
  /** `YYYY-MM-DD`, both ends inclusive. */
  payment_date_from?: string;
  payment_date_to?: string;
  /** Minor units, both ends inclusive. */
  amount_min?: number;
  amount_max?: number;
  /** A column, `-` first for descending; by default `-payment_date`. */
  sort?: string;
}

export interface PaymentIn {
  method_id?: string | null;
  method?: string | null;
  /** `YYYY-MM-DD`. */
  payment_date: string;
  /** Minor units, above 0. */
  amount: number;
  beneficiary_name: string;
  beneficiary_iban?: string;
  concept?: string;
  supplier_invoice_ref?: string;
  currency?: string | null;
}

export interface PaymentOut {
  id: string;
  reference: string;
  method_id: string;
  method_name: string;
  /** `YYYY-MM-DD`. */
  payment_date: string;
  amount: number;
  currency: string;
  beneficiary_name: string;
  /** Masked in a list (`ES** **** **** **** **** 1332`); whole only from `payment.payment.get`. */
  beneficiary_iban: string;
  concept: string;
  status: PaymentStatus;
  supplier_invoice_ref: string;
  cancel_reason: string;
  /** Who approved it; empty until approved. */
  approved_by: string;
  approved_at: string | null;
  sent_at: string | null;
  completed_at: string | null;
  cancelled_by: string;
  cancelled_at: string | null;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'payment.payment.list': { input: PaymentListIn; output: Page<PaymentOut> };
    'payment.payment.get': { input: PaymentRefIn; output: PaymentOut };
    'payment.payment.create': { input: PaymentIn; output: PaymentOut };
    'payment.payment.approve': { input: PaymentRefIn; output: PaymentOut };
    'payment.payment.mark_sent': { input: PaymentRefIn; output: PaymentOut };
    'payment.payment.mark_completed': { input: PaymentRefIn; output: PaymentOut };
    'payment.payment.cancel': { input: CancelIn; output: PaymentOut };
    'payment.method.list': { input: MethodListIn; output: Page<MethodOut> };
    'payment.method.get': { input: MethodRefIn; output: MethodOut };
    'payment.method.create': { input: MethodIn; output: MethodOut };
    'payment.method.update': { input: MethodPatchIn; output: MethodOut };
    'payment.method.deactivate': { input: MethodRefIn; output: MethodOut };
    'payment.method.activate': { input: MethodRefIn; output: MethodOut };
  }
}
