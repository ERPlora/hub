// Why the charge sheet cannot charge yet, one reason at a time, in the old screen's order (sales#159,
// #222, #297, #309, #498): the customer the business requires, the invoice recipient (complete, its tax
// ID checking and, abroad, its kind of document: `sale.invoice_recipient_incomplete`, 422 on
// `customer_tax_id` / `customer_id_type`), cash over the
// legal limit, what a split has left, cash with nothing tendered, cash short. Every one of them is also
// refused by the server (`sale.customer_required`, `sale.invoice_recipient_incomplete`,
// `sale.cash_limit_exceeded`, `sale.payments_do_not_match_total`, `sale.insufficient_tendered`): the
// screen only says it before the tap. The button stays tappable and answers with the reason.
import type { DocumentType } from '../../operations';
import { cashOverLimit, isCash } from './methods';
import type { RecipientIssue } from './taxId';
import { type Leg, needsTendered, remainingCents, type TenderMethod } from './tender';

export type ChargeBlock =
  | { kind: 'customerRequired' }
  | { kind: 'recipient' }
  | { kind: RecipientIssue }
  | { kind: 'cashLimit'; limit: number }
  | { kind: 'remaining'; amount: number }
  | { kind: 'tenderedMissing' }
  | { kind: 'tenderedShort' };

export interface BlockState {
  /** The till settings' «Require a customer on every sale». */
  requireCustomer: boolean;
  hasCustomer: boolean;
  documentType: DocumentType;
  recipientComplete: boolean;
  /** What is wrong with the recipient's tax ID (`recipientIssue`); none when nothing. */
  recipientIssue?: RecipientIssue | null;
  /** The server's total of this charge. */
  total: number;
  /** What the cash limit looks at: the whole operation (`operation_total`); `total` without it. */
  operationTotal?: number;
  cashLimit: number | null;
  method: TenderMethod | undefined;
  /** What the keypad holds, in cents. */
  typed: number;
  splitting: boolean;
  legs: readonly Leg[];
}

/** The first reason this charge cannot go through as it stands; `null` when it can. */
export function chargeBlock(state: BlockState): ChargeBlock | null {
  if (state.requireCustomer && !state.hasCustomer) return { kind: 'customerRequired' };
  if (state.documentType === 'invoice' && !state.recipientComplete) return { kind: 'recipient' };
  if (state.documentType === 'invoice' && state.recipientIssue) return { kind: state.recipientIssue };
  const split = state.splitting || state.legs.length > 0;
  if (cashOverLimit(state.cashLimit, state.operationTotal ?? state.total)) {
    const cashLeg = state.legs.some((leg) => isCash(leg.method));
    if (cashLeg || (!split && isCash(state.method))) return { kind: 'cashLimit', limit: state.cashLimit as number };
  }
  if (split) {
    const remaining = remainingCents(state.total, state.legs);
    return remaining > 0 ? { kind: 'remaining', amount: remaining } : null;
  }
  if (needsTendered(state.method) && state.total > 0) {
    if (state.typed === 0) return { kind: 'tenderedMissing' };
    if (state.typed < state.total) return { kind: 'tenderedShort' };
  }
  return null;
}
