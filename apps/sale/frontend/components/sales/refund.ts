// The arithmetic of the Refund window (SALE-F31). None of it is the authority: what each tender charged,
// gave back and has left, and each line's units, come from `sale.refund.options`, and `sale.sale.refund`
// decides everything again. This is the PROPOSAL the person edits and the reason the button says «not
// yet» while they type, written so that it never invents nor loses a cent:
//   - a marked line proposes its share, `round(total·min(prev+q, qty)/qty) − round(total·prev/qty)`, so
//     the refunds of a line add up to its total;
//   - the amount is split across the tenders by what each has left (largest remainder, ties to the
//     earlier tender); a tender that cannot go back its own way still takes its share and asks where
//     the money goes instead (`to_method_id`);
//   - nothing marked proposes all that is left.
import { centsFromEuros } from '../../lib/format';
import type { AllocationIn, LineOption, RefundLineIn, TenderOption } from '../../operations';

/** Units picked per line, in thousandths of a unit (quantities carry up to 3 decimals). */
export type Picked = Readonly<Record<string, number>>;
/** Cents per tender (`NaN`: what was typed is not an amount). */
export type Amounts = Readonly<Record<string, number>>;
/** The method chosen per tender that cannot go back its own way. */
export type Destinations = Readonly<Record<string, string>>;

/** Why the refund cannot be confirmed yet, in the order it matters to the person. */
export type RefundBlock =
  | { kind: 'invalid'; tender: TenderOption }
  | { kind: 'nothing' }
  | { kind: 'overCap'; tender: TenderOption; amount: number }
  | { kind: 'needsDestination'; tender: TenderOption }
  | { kind: 'reason' };

/** A decimal quantity («2.000», «0.532») in thousandths of a unit. */
export function milli(quantity: string | number): number {
  return Math.round(Number(quantity) * 1000) || 0;
}

/** The whole units left of a line (what a stepper walks); 0 when what is left is not whole. */
export function wholeLeft(line: LineOption): number {
  const left = milli(line.left);
  return left > 0 && left % 1000 === 0 ? left / 1000 : 0;
}

/** What `units` (thousandths) of `line` cost after what already went back: rounded from its total. */
export function lineShare(line: LineOption, units: number): number {
  const quantity = milli(line.quantity);
  const previous = milli(line.returned);
  const going = Math.max(0, Math.min(units, milli(line.left)));
  if (quantity <= 0) return going > 0 ? line.line_total : 0;
  const upTo = (n: number): number => Math.round((line.line_total * Math.min(n, quantity)) / quantity);
  return upTo(previous + going) - upTo(previous);
}

/** What the marked units cost: the amount the window proposes. */
export function pickedAmount(lines: readonly LineOption[], picked: Picked): number {
  return lines.reduce((sum, line) => sum + (picked[line.line_id] ? lineShare(line, picked[line.line_id]) : 0), 0);
}

/** The money that can still go back: what the tenders have left, not what they charged. */
export function refundableTotal(tenders: readonly TenderOption[]): number {
  return tenders.reduce((sum, tender) => sum + Math.max(0, tender.remaining), 0);
}

const inTicketOrder = (tenders: readonly TenderOption[]): TenderOption[] => [...tenders].sort((a, b) => a.position - b.position);

/** `amount` split across the tenders by what each has left, by largest remainder (ties: the earlier). */
export function splitByRemaining(amount: number, tenders: readonly TenderOption[]): Record<string, number> {
  const split: Record<string, number> = Object.fromEntries(tenders.map((tender) => [tender.payment_id, 0]));
  const weights = tenders.map((tender) => Math.max(0, tender.remaining));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const share = Math.min(Math.max(0, Math.round(amount)), total);
  if (share <= 0) return split;
  const remainders = tenders.map((tender, index) => {
    const numerator = share * weights[index];
    split[tender.payment_id] = Math.floor(numerator / total);
    return { rest: numerator % total, index };
  });
  let left = share - Object.values(split).reduce((sum, cents) => sum + cents, 0);
  remainders.sort((a, b) => b.rest - a.rest || a.index - b.index);
  for (const { index } of remainders) {
    if (left <= 0) break;
    split[tenders[index].payment_id] += 1;
    left -= 1;
  }
  return split;
}

/** The proposal: the marked lines' share (or everything left, with nothing marked), split by tender. */
export function proposal(tenders: readonly TenderOption[], lines: readonly LineOption[], picked: Picked): Record<string, number> {
  const marked = Object.values(picked).some((units) => units > 0);
  return splitByRemaining(marked ? pickedAmount(lines, picked) : refundableTotal(tenders), tenders);
}

/** Cents as the person edits them: the reader's decimal separator, no grouping (it reads back the same). */
export function amountInput(cents: number, locale: string): string {
  const digits = String(Math.max(0, Math.round(cents))).padStart(3, '0');
  let separator = '.';
  try {
    separator = new Intl.NumberFormat(locale).formatToParts(1.1).find((part) => part.type === 'decimal')?.value ?? '.';
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
  }
  return `${digits.slice(0, -2)}${separator}${digits.slice(-2)}`;
}

/** What was typed, in cents: blank is 0; anything that is not an amount is `NaN`. */
export function parseAmount(text: string): number {
  if (!text.trim()) return 0;
  return centsFromEuros(text) ?? Number.NaN;
}

/** Why it cannot be confirmed yet, or `null`. */
export function refundBlock(tenders: readonly TenderOption[], amounts: Amounts, destinations: Destinations, reason: string): RefundBlock | null {
  const ordered = inTicketOrder(tenders);
  const amountOf = (tender: TenderOption): number => amounts[tender.payment_id] ?? 0;
  const invalid = ordered.find((tender) => Number.isNaN(amountOf(tender)));
  if (invalid) return { kind: 'invalid', tender: invalid };
  if (ordered.reduce((sum, tender) => sum + amountOf(tender), 0) <= 0) return { kind: 'nothing' };
  const over = ordered.find((tender) => amountOf(tender) > tender.remaining);
  if (over) return { kind: 'overCap', tender: over, amount: amountOf(over) };
  const homeless = ordered.find((tender) => amountOf(tender) > 0 && !tender.refundable && !destinations[tender.payment_id]);
  if (homeless) return { kind: 'needsDestination', tender: homeless };
  if (!reason.trim()) return { kind: 'reason' };
  return null;
}

/** The tenders with money, in the ticket's order; the destination only where the tender needs one. */
export function allocations(tenders: readonly TenderOption[], amounts: Amounts, destinations: Destinations): AllocationIn[] {
  return inTicketOrder(tenders).flatMap((tender) => {
    const amount = amounts[tender.payment_id] ?? 0;
    if (!(amount > 0)) return [];
    const to = tender.refundable ? undefined : destinations[tender.payment_id];
    return [{ payment_id: tender.payment_id, amount, ...(to ? { to_method_id: to } : {}) }];
  });
}

/** The marked lines with the units that go back (never more than is left). */
export function refundLines(lines: readonly LineOption[], picked: Picked): RefundLineIn[] {
  return lines.flatMap((line) => {
    const units = Math.min(picked[line.line_id] ?? 0, milli(line.left));
    return units > 0 ? [{ line_id: line.line_id, quantity: (units / 1000).toFixed(3) }] : [];
  });
}

/** A new attempt's key: a retry with it never refunds twice (`AttemptKey`: 8–128 of [A-Za-z0-9_.:-]). */
export function attemptKey(saleId: string): string {
  return `refund-${saleId}-${crypto.randomUUID()}`;
}
