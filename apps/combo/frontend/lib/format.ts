// How the combo screens paint money (pages never format by hand), always in the page language's own
// format (Intl). Money is whole cents of euros: the Hub has no currency setting and every ERPlora
// business invoices in euros. A supplement shows its sign, as the till does.

const CURRENCY = 'EUR';

const formats = new Map<string, Intl.NumberFormat>();
const decimalMarks = new Map<string, string>();

function moneyFormat(locale: string, signed: boolean): Intl.NumberFormat {
  const key = `${locale}|${signed}`;
  let found = formats.get(key);
  if (!found) {
    found = new Intl.NumberFormat(locale, { style: 'currency', currency: CURRENCY, ...(signed ? { signDisplay: 'exceptZero' as const } : {}) });
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

/** Whole cents as euros in `locale` («13,50 €», «€13.50»). */
export function formatMoney(cents: number, locale: string): string {
  return moneyFormat(locale, false).format(cents / 100);
}

/** A supplement with its sign («+2,00 €», «-€0.50»); `''` for none. */
export function formatDelta(cents: number, locale: string): string {
  return cents ? moneyFormat(locale, true).format(cents / 100) : '';
}
