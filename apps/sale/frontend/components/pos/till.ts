// The till's small rules, kept pure (the product's `pos-cart.ts`, `park-label` and quick-note helpers):
// the tile's initials and gradient, the time a check is parked under, the quick-note chips, the line a
// second tap on a product raises. Money and totals are never worked out here: the server's operations
// say them; the words of a refusal are `lib/refusal.ts`'s.
import type { OrderLineOut } from '../../operations';

// The initials over the name's colour are the till's and every list's stand-in for a missing photo (INVENTORY-F32):
// one source, in base.
export { initials, tileGradient } from '../../../../../base/frontend/lib/item-image';

const timeFormats = new Map<string, Intl.DateTimeFormat>();

/** The hour and minutes in the reader's language («9:05», «9:05 AM»): a parked check's default title. */
export function shortTime(value: Date | string, locale: string): string {
  let format = timeFormats.get(locale);
  if (!format) {
    try {
      format = new Intl.DateTimeFormat(locale, { timeStyle: 'short' });
    } catch {
      format = new Intl.DateTimeFormat('en', { timeStyle: 'short' });
    }
    timeFormats.set(locale, format);
  }
  return format.format(value instanceof Date ? value : new Date(value));
}

const parts = (note: string): string[] =>
  note
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);

/** Whether `chip` is one of the note's comma-separated parts. */
export function noteHasChip(note: string, chip: string): boolean {
  return parts(note).includes(chip.trim());
}

/** Adds `chip` after a comma, or takes that part out: never twice. */
export function toggleNoteChip(note: string, chip: string): string {
  const current = parts(note);
  const text = chip.trim();
  return (current.includes(text) ? current.filter((part) => part !== text) : [...current, text]).join(', ');
}

/** The pending line a second tap on `productId` raises: same professional, no note, discount, comp or options
 *  (a line with options of Modifiers is a dish of its own, SALE-F11). */
export function mergeableLine(lines: readonly OrderLineOut[], productId: string, staffId: string | null): OrderLineOut | undefined {
  return lines.find(
    (line) =>
      line.product_id === productId &&
      !line.modifiers.length &&
      !line.fired_at &&
      !line.notes &&
      !line.is_gift &&
      Number(line.discount_percent) === 0 &&
      (line.staff_id ?? null) === staffId,
  );
}

/** The value of the «Services» chip of the category strip (a category id is a UUID: never this). */
export const SERVICES = 'services';

/** The pending line a second tap of a service raises (SALE-F38): as a product's, never one a voucher pays. */
export function mergeableServiceLine(lines: readonly OrderLineOut[], serviceId: string, staffId: string | null): OrderLineOut | undefined {
  return lines.find(
    (line) =>
      line.service_id === serviceId &&
      !line.paid_by_voucher &&
      !line.fired_at &&
      !line.notes &&
      !line.is_gift &&
      Number(line.discount_percent) === 0 &&
      (line.staff_id ?? null) === staffId,
  );
}

/** One more unit of a decimal quantity («0.532» → «1.532»), as the line's stepper sends it. */
export function plusOne(quantity: string): string {
  return String(Math.round((Number(quantity) + 1) * 1000) / 1000);
}
