// How the inventory screens paint money, counts, quantities and rates (pages never format by hand),
// always with the page language's own number format (Intl). Money is whole cents of euros: the Hub
// has no currency setting yet and every ERPlora business invoices in euros (queries.CURRENCY).
// Quantities are exact decimals from the API («2.500», at most three decimals): painted ungrouped
// and without trailing zeros, as the server's CSV writes them (queries.quantity_text).

const CURRENCY = 'EUR';

const formats = new Map<string, Intl.NumberFormat>();
const decimalMarks = new Map<string, string>();

function numberFormat(locale: string, kind: 'money' | 'count' | 'quantity' | 'percent'): Intl.NumberFormat {
  const key = `${locale}|${kind}`;
  let found = formats.get(key);
  if (!found) {
    const options: Record<typeof kind, Intl.NumberFormatOptions> = {
      money: { style: 'currency', currency: CURRENCY },
      count: {},
      quantity: { maximumFractionDigits: 3, useGrouping: false },
      percent: { style: 'percent', maximumFractionDigits: 2 },
    };
    found = new Intl.NumberFormat(locale, options[kind]);
    formats.set(key, found);
  }
  return found;
}

/** The decimal mark of `locale` («,» in Spanish, «.» in English). */
export function decimalMark(locale: string): string {
  let found = decimalMarks.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
    decimalMarks.set(locale, found);
  }
  return found;
}

/** Whole cents as euros in `locale` («2,20 €», «€2.20»). */
export function formatMoney(cents: number, locale: string): string {
  return numberFormat(locale, 'money').format(cents / 100);
}

/** A count («12.345» products in Spanish). */
export function formatCount(value: number, locale: string): string {
  return numberFormat(locale, 'count').format(value);
}

/** An exact decimal as the person reads it: «2.500» → «2,5» (es), «3.000» → «3»; a non-figure as it came. */
export function formatQuantity(value: string | number, locale: string): string {
  const text = String(value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text;
  // `+ 0` turns a negative zero («-0.000») into 0.
  return numberFormat(locale, 'quantity').format(Number(text) + 0);
}

/** A movement's quantity with its sign: «+2» in, «-1,5» out, «0». */
export function formatSignedQuantity(value: string | number, locale: string): string {
  const painted = formatQuantity(value, locale);
  return /^\d/.test(painted) && painted !== '0' ? `+${painted}` : painted;
}

/** A tax rate in % («21.00») as the language writes it: «21 %» (es), «21%» (en). */
export function formatPercent(rate: string | number, locale: string): string {
  return numberFormat(locale, 'percent').format(Number(rate) / 100);
}
