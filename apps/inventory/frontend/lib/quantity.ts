// Quantities of the inventory screens: what a person types into the exact decimal the API takes,
// with the server's rules (services.parse_quantity): at most three decimals (a gram in a kilo),
// never negative, and with both marks the rightmost one is the decimal one. Whether a quantity fits
// its unit's step is the server's to say. Arithmetic is exact, in thousandths (BigInt), never floats.

/** Thousandths: the finest step of any unit. */
const PLACES = 3;
const SCALE = 10n ** BigInt(PLACES);

export type QuantityRead = { ok: true; value: string | null } | { ok: false };

/** The decimal mark of a typed figure normalised to a point, or `null` when it cannot be one. */
function withDecimalPoint(raw: string): string | null {
  const lastComma = raw.lastIndexOf(',');
  const lastDot = raw.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    return lastComma > lastDot ? raw.replaceAll('.', '').replace(',', '.') : raw.replaceAll(',', '');
  }
  if (lastComma >= 0) return raw.indexOf(',') === lastComma ? raw.replace(',', '.') : null;
  return raw;
}

/** What a quantity field holds: `{ ok, value }` with the API decimal (`null` when empty), or `{ ok: false }`. */
export function readQuantity(text: string): QuantityRead {
  const raw = text.trim().replaceAll(' ', '');
  if (raw === '') return { ok: true, value: null };
  const normalized = withDecimalPoint(raw);
  if (normalized === null || !/^\d+(\.\d{1,3})?$/.test(normalized)) return { ok: false };
  return { ok: true, value: normalized };
}

/** A decimal string («-2.250», «4.5») in thousandths. */
function toThousandths(value: string): bigint {
  const negative = value.trim().startsWith('-');
  const [whole, fraction = ''] = value.trim().replace(/^[-+]/, '').split('.');
  const amount = BigInt(whole || '0') * SCALE + BigInt((fraction + '000').slice(0, PLACES) || '0');
  return negative ? -amount : amount;
}

/** Thousandths back to the shortest decimal string («-0.5», «12.25», «0»). */
function fromThousandths(amount: bigint): string {
  const negative = amount < 0n;
  const absolute = negative ? -amount : amount;
  const whole = absolute / SCALE;
  const fraction = (absolute % SCALE).toString().padStart(PLACES, '0').replace(/0+$/, '');
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`;
}

/** The count's «Difference»: what was counted minus what the system says, exact and signed. */
export function quantityDifference(counted: string, current: string): string {
  return fromThousandths(toThousandths(counted) - toThousandths(current));
}
