// What the charge sheet and the steps other apps add to it tell each other (SALE-F39; the tip of Tips is one). A step
// is a component of its app, named by `sale.checkout.steps` and mounted between the amount and the tenders, that Sales
// knows only by this contract: it gets the charge's total, what its discounts took off, the payment method chosen and
// whether the sale is already charged (`locked`); it says what it adds (`update:added`); and once the sale is charged
// it records its own part (`afterCharge`, with the charge's attempt key, so a retry records it once). What it adds is
// charged with the sale on its one payment but kept apart from it: never its price, never taxed.
import type { PaymentIn, SaleOut } from '../../operations';
import type { ChargeBlock } from './blocks';
import type { TenderMethod } from './tender';

export interface StepProps {
  /** The sale's total of this charge, in cents. */
  total: number;
  /** What its discounts took off it, in cents. */
  discount: number;
  method: TenderMethod;
  /** The sale is charged: nothing changes any more. */
  locked: boolean;
}

/** What a step adds: in cents, its name on the paper (`extra_label`) and, when it cannot be charged yet, why. */
export interface Added {
  amount: number;
  label: string;
  issue: string;
}

export const NOTHING_ADDED: Added = Object.freeze({ amount: 0, label: '', issue: '' });

/** What a step's component exposes: recording its part of a charged sale; it throws with its own words. */
export interface StepHandle {
  afterCharge: (sale: SaleOut, attemptKey: string) => Promise<void>;
}

/** What all the steps add together, named by those that add something. */
export function allAdded(each: readonly Added[]): Added {
  const adding = each.filter((added) => added.amount > 0);
  return {
    amount: adding.reduce((sum, added) => sum + added.amount, 0),
    label: adding.map((added) => added.label).join(', '),
    issue: each.find((added) => added.issue)?.issue ?? '',
  };
}

/** The payments with what the steps add, on the one payment of a charge that is not split. */
export function withAdded(payments: PaymentIn[], added: Added): PaymentIn[] {
  if (added.amount <= 0 || payments.length !== 1) return payments;
  return [{ ...payments[0], extra: added.amount, extra_label: added.label }];
}

/** A step that cannot be charged as it stands (an amount that does not read) stops the charge with its words. */
export function stepBlock(added: Added): ChargeBlock | null {
  return added.issue ? { kind: 'step', message: added.issue } : null;
}
