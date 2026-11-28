// What the Tips screen sends to record a tip (`tip.tip.add`) and to adjust one (`tip.tip.update`). The amount is typed
// in the business's money and read here; what the person left empty does not travel, so the server says what is
// missing in its own words.
import { parseMoney } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/money';
import type { TipOut, TipPatchIn, TipRecordIn } from '../operations';

/** The key of the sentence under the amount when it is no tip. */
export const AMOUNT_INVALID = 'tip.form.amountInvalid';

export type Built<In> = { input: In } | { errors: { amount: string } };

export interface RecordForm {
  /** Of a sale, or cash to the pool with no ticket. */
  target: 'sale' | 'pool';
  sale: string;
  methodId: string;
  amount: string;
}

export interface AdjustForm {
  amount: string;
  memberId: string | null;
  reason: string;
}

/** The cents of `text`, or `null` when it is not an amount above zero. */
function cents(text: string, money: Money | undefined): number | null {
  const read = parseMoney(text, { money });
  return read.ok && read.cents !== null && read.cents > 0 ? read.cents : null;
}

export function recordInput(form: RecordForm, money: Money | undefined): Built<Partial<TipRecordIn>> {
  const amount = cents(form.amount, money);
  if (amount === null) return { errors: { amount: AMOUNT_INVALID } };
  if (form.target === 'pool') return { input: { pool: true, amount } };
  const sale = form.sale.trim();
  return { input: { ...(sale ? { sale } : {}), ...(form.methodId ? { method_id: form.methodId } : {}), amount } };
}

export function adjustInput(tip: TipOut, form: AdjustForm, money: Money | undefined): Built<TipPatchIn> {
  const amount = cents(form.amount, money);
  if (amount === null) return { errors: { amount: AMOUNT_INVALID } };
  return {
    input: {
      id: tip.id,
      ...(amount !== tip.amount ? { amount } : {}),
      ...(form.memberId && form.memberId !== tip.member_id ? { member_id: form.memberId } : {}),
      reason: form.reason,
    },
  };
}
