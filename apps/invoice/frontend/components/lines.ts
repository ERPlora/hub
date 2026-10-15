// The lines of a manual invoice (INVOICE-F03) as the form keeps them (what is typed: «1,5», «12,50», «21»)
// and as `invoice.invoice.create` takes them: the quantity as a decimal with a dot, the price WITHOUT VAT in
// cents, the VAT %. The server computes the VAT, closed once per rate; the form only checks that each line
// can be sent.
import { centsFromEuros } from '../lib/format';
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

/** One unit at 21 %, as the old form started a line. */
export function blankLine(uid: number): DraftLine {
  return { uid, description: '', quantity: '1', price: '', taxRate: '21' };
}

function quantityOf(text: string): number | undefined {
  const trimmed = text.trim();
  return QUANTITY.test(trimmed) ? Number(trimmed.replace(',', '.')) : undefined;
}

/** Every line has a description, a quantity above zero and a price written. */
export function linesReady(lines: readonly DraftLine[]): boolean {
  return (
    lines.length > 0 &&
    lines.every((line) => line.description.trim() !== '' && (quantityOf(line.quantity) ?? 0) > 0 && line.price.trim() !== '')
  );
}

/** The 1-based number of the first line whose price is not an amount, or `null`. */
export function unreadablePrice(lines: readonly DraftLine[]): number | null {
  const index = lines.findIndex((line) => centsFromEuros(line.price) === undefined);
  return index === -1 ? null : index + 1;
}

/** A line as the command takes it (call it once `unreadablePrice` found none). */
export function linePayload(line: DraftLine): ManualLineIn {
  return {
    description: line.description.trim(),
    quantity: line.quantity.trim().replace(',', '.'),
    unit_price: centsFromEuros(line.price) ?? 0,
    tax_rate: line.taxRate.trim().replace(',', '.'),
  };
}
