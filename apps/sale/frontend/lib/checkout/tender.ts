// The tender of the charge sheet (SALE-F01, F02, F03): the keypad's text, the legs of a split payment,
// the change and the `payments` of `sale.sale.complete`. Only the arithmetic of what the person types
// lives here: the amount to charge is the server's preview (`sale.checkout.preview`), and the server
// re-checks every leg (`sale.payments_do_not_match_total`, `sale.insufficient_tendered`). Money is whole
// cents; the keypad types euros with '.' as its separator, whatever the page's language shows.
import type { PaymentIn, PaymentMethodOut } from '../../operations';

/** What the tender needs of a payment method. */
export type TenderMethod = Pick<PaymentMethodOut, 'id' | 'display_name' | 'type' | 'requires_change'>;

/** One leg of a split payment: its method, what it pays and what was handed over (cash gives change). */
export interface Leg {
  id: string;
  method: TenderMethod;
  amount: number;
  tendered: number;
}

const DECIMALS = 2;
const MAX_TYPED = 9;

/** The keypad: digits, one '.' and two decimals at most, nine characters; 'C' clears. */
export function pushKey(typed: string, key: string): string {
  if (key === 'C') return '';
  if (key === '.') return typed.includes('.') ? typed : `${typed || '0'}.`.slice(0, MAX_TYPED);
  const dot = typed.indexOf('.');
  if (dot >= 0 && typed.length - dot - 1 >= DECIMALS) return typed;
  return `${typed}${key}`.slice(0, MAX_TYPED);
}

/** The keypad's text as cents, from its digits (no float rounding); nothing typed is 0. */
export function typedCents(typed: string): number {
  const [whole = '', fraction = ''] = typed.split('.');
  const digits = `${whole || '0'}${fraction.padEnd(DECIMALS, '0').slice(0, DECIMALS)}`;
  return /^\d+$/.test(digits) ? Number.parseInt(digits, 10) : 0;
}

/** Cents back to the text the keypad reads (1250 → «12.50»): a leg brought back to be edited. */
export function centsToTyped(cents: number): string {
  const digits = String(Math.max(0, Math.round(cents))).padStart(DECIMALS + 1, '0');
  return `${digits.slice(0, -DECIMALS)}.${digits.slice(-DECIMALS)}`;
}

/** Cash asks what was handed over and gives change; any other method charges the exact amount. */
export function needsTendered(method: TenderMethod | undefined): boolean {
  return !!method?.requires_change;
}

/** What is left to cover once the legs are taken; never below 0. */
export function remainingCents(total: number, legs: readonly Leg[]): number {
  return Math.max(0, total - legs.reduce((sum, leg) => sum + leg.amount, 0));
}

/** The leg «Add this payment» would take now: what was typed (all that is left if nothing), up to what
 *  is left; cash handed over beyond it is kept as tendered, so the change shows before it is taken. */
export function planLeg(
  method: TenderMethod | undefined,
  typed: number,
  remaining: number,
): { amount: number; tendered: number } | undefined {
  if (!method || remaining <= 0) return undefined;
  const amount = typed > 0 ? Math.min(typed, remaining) : remaining;
  return { amount, tendered: needsTendered(method) && typed > amount ? typed : amount };
}

/** The change of the legs: it comes out of cash only and is never shared out. */
export function changeDue(legs: readonly Leg[]): number {
  return legs.reduce((sum, leg) => sum + (needsTendered(leg.method) ? Math.max(0, leg.tendered - leg.amount) : 0), 0);
}

export interface PaymentsState {
  /** The server's total of this charge. */
  total: number;
  method: TenderMethod | undefined;
  /** What the keypad holds, in cents. */
  typed: number;
  splitting: boolean;
  legs: readonly Leg[];
}

/** The `payments` of the charge. One method: cash sends what was handed over and the server works out
 *  the amount (its own total); any other, just the method. Split: one payment per leg with its amount. */
export function paymentsIn(state: PaymentsState): PaymentIn[] {
  if (state.total <= 0) return [];
  if (state.splitting || state.legs.length) {
    return state.legs.map((leg) => ({
      method_id: leg.method.id,
      amount: leg.amount,
      ...(needsTendered(leg.method) && leg.tendered > leg.amount ? { tendered: leg.tendered } : {}),
    }));
  }
  if (!state.method) return [];
  return [needsTendered(state.method) ? { method_id: state.method.id, tendered: state.typed } : { method_id: state.method.id }];
}
