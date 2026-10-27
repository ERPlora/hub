// The lines of a manual invoice (INVOICE-F03) as the form keeps them (what is typed: «1,5», «12,50», «7»)
// and as `invoice.invoice.create` takes them: the quantity as a decimal with a dot, the price WITHOUT the tax
// in cents, the rate %, declared with the tax of the business's territory (VAT, IGIC or IPSI; TAX-F11). The
// server computes the tax, closed once per rate; the form only checks that each line can be sent.
import { centsFromAmount, type Money } from '../lib/format';
import type { ManualLineIn } from '../operations';

/** A line on screen; `uid` names its hooks (`invoice-line-<uid>-…`) and survives removing another line. */
export interface DraftLine {
  uid: number;
  description: string;
  quantity: string;
  price: string;
  taxRate: string;
}

const QUANTITY = /^\d+(?:[.,]\d{1,3})?$/;

/** One unit at `taxRate` (the territory's general rate, as typed; blank while it is not known or the
 *  territory has no rule of its own tax), as the old form started a line at 21. */
export function blankLine(uid: number, taxRate = ''): DraftLine {
  return { uid, description: '', quantity: '1', price: '', taxRate };
}

function quantityOf(text: string): number | undefined {
  const trimmed = text.trim();
  return QUANTITY.test(trimmed) ? Number(trimmed.replace(',', '.')) : undefined;
}

/** Every line has a description, a quantity above zero, a price and a rate written. */
export function linesReady(lines: readonly DraftLine[]): boolean {
  return (
    lines.length > 0 &&
    lines.every(
      (line) => line.description.trim() !== '' && (quantityOf(line.quantity) ?? 0) > 0 && line.price.trim() !== '' && line.taxRate.trim() !== '',
    )
  );
}

/** The 1-based number of the first line whose price is not an amount of the business's `money`, or `null`. */
export function unreadablePrice(lines: readonly DraftLine[], money?: Money): number | null {
  const index = lines.findIndex((line) => centsFromAmount(line.price, money) === undefined);
  return index === -1 ? null : index + 1;
}

/** A line as the command takes it, its price in minor units of the business's `money` (call it once
 *  `unreadablePrice` found none). */
export function linePayload(line: DraftLine, money?: Money): ManualLineIn {
  return {
    description: line.description.trim(),
    quantity: line.quantity.trim().replace(',', '.'),
    unit_price: centsFromAmount(line.price, money) ?? 0,
    tax_rate: line.taxRate.trim().replace(',', '.'),
  };
}
