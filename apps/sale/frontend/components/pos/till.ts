// The till's small rules, kept pure (the product's `pos-cart.ts`, `park-label` and quick-note helpers):
// the tile's initials and gradient, the time a check is parked under, the quick-note chips, the line a
// second tap on a product raises and the words a refused write shows. Money and totals are never
// worked out here: the server's operations say them.
import { ApiError } from '@erplora/ui/sdk';

import type { CustomerSnapshot } from '../../../../customer/frontend/components/CustomerSearch.vue';
import { countryName } from '../../../../customer/frontend/lib/countries';
import type { OrderLineOut } from '../../operations';

/** The first letters of the first two words, upper case («café con leche» → «CC»). */
export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join('')
    .toUpperCase();
}

function hue(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) | 0;
  return Math.abs(hash) % 360;
}

/** The tile's stable colour, derived from its name (the same product always looks the same). */
export function tileGradient(name: string): string {
  const h = hue(name);
  return `linear-gradient(135deg, hsl(${h} 42% 38%), hsl(${(h + 38) % 360} 44% 26%))`;
}

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

/** The pending line a second tap on `productId` raises: same professional, no note, discount or comp. */
export function mergeableLine(lines: readonly OrderLineOut[], productId: string, staffId: string | null): OrderLineOut | undefined {
  return lines.find(
    (line) =>
      line.product_id === productId &&
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

/**
 * What a refused write shows: the server's own sentence when it answered with a refusal (it comes in
 * the reader's language), `fallback` when nobody answered (no network, a proxy's error page).
 */
export function refusal(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500 && error.message) return error.message;
  return fallback;
}

/** The card fields the sale copies (`customer.customer.detail`). */
export interface CustomerCard {
  id: string;
  name: string;
  tax_id: string;
  address: string;
  postal_code: string;
  city: string;
  country: string;
}

/**
 * The tax details a sale keeps of its customer, as the Customers app's search hands them over
 * («street, postal code city, country»): what a resumed check gets back from the card linked to it.
 */
export function customerSnapshot(card: CustomerCard, locale: string): CustomerSnapshot {
  const place = [card.postal_code, card.city].filter((part) => part && part.trim()).join(' ');
  const address = [card.address, place, countryName(card.country, locale)].filter((part) => part && part.trim()).join(', ');
  return {
    customer_id: card.id,
    customer_name: card.name,
    customer_tax_id: card.tax_id,
    customer_address: address,
    customer_country: card.country,
  };
}
