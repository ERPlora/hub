// Money in the reader's language (pages never format by hand): whole cents of euros — the Hub has no
// currency setting and every ERPlora business invoices in euros.

const CURRENCY = 'EUR';
const formats = new Map<string, Intl.NumberFormat>();

/** Whole cents as euros in `locale` («22,50 €», «€22.50»). */
export function formatMoney(cents: number, locale: string): string {
  let found = formats.get(locale);
  if (!found) {
    try {
      found = new Intl.NumberFormat(locale, { style: 'currency', currency: CURRENCY });
    } catch {
      found = new Intl.NumberFormat('en', { style: 'currency', currency: CURRENCY });
    }
    formats.set(locale, found);
  }
  return found.format(cents / 100);
}
