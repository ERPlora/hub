// Money of the customer screens: the server keeps minor units (WORKBOOK «Reglas que no se rompen»), a person
// reads and types them in the business's currency (`useBusinessMoney`, the platform's: its country's, with the
// decimals the server counts it in, never the browser's Intl, which gives the forint none). Until the business
// answers an amount is a figure without a symbol, never the euro by default. A record that kept its own currency
// (a purchase) is painted in it. Until `@erplora/ui/components/format` has a money formatter (UI-REQUESTS.md),
// this is the one place the app turns minor units into text and what a person types into minor units.
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

const FALLBACK_LOCALE = 'en';
/** The decimals of an amount while the currency is unknown. */
const UNKNOWN_DECIMALS = 2;

const formatters = new Map<string, Intl.NumberFormat>();

function formatter(locale: string, money: Money | undefined): Intl.NumberFormat {
  const decimals = money?.decimals ?? UNKNOWN_DECIMALS;
  const key = `${locale}|${money?.currency ?? ''}|${decimals}`;
  let found = formatters.get(key);
  if (!found) {
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    // The symbol a till of that country prints («zł», «¥»); until the business is known, the figure alone.
    const style: Intl.NumberFormatOptions = money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol' } : {};
    try {
      found = new Intl.NumberFormat(locale, { ...style, ...digits });
    } catch (error) {
      if (!(error instanceof RangeError) || locale === FALLBACK_LOCALE) throw error;
      found = formatter(FALLBACK_LOCALE, money);
    }
    formatters.set(key, found);
  }
  return found;
}

/** Minor units in `money`, in `locale` («zł 1,234.56», «1234,56 €», «¥1,250»; «1,234.56» while it is unknown);
 *  nothing to show is «—». */
export function formatMoney(cents: number | null | undefined, locale: string, money?: Money): string {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return '—';
  return formatter(locale, money).format(cents / 10 ** (money?.decimals ?? UNKNOWN_DECIMALS));
}

/** The money of a record: the currency it kept, with the decimals the server says, else the business's. */
export function recordMoney(record: { currency?: unknown; currency_decimals?: number | null }, business?: Money): Money | undefined {
  const { currency, currency_decimals: decimals } = record;
  return typeof currency === 'string' && currency && typeof decimals === 'number' ? { currency, decimals } : business;
}

/** What an amount typed by a person says. */
export type AmountReading = { kind: 'blank' } | { kind: 'invalid' } | { kind: 'amount'; cents: number };

const marks = new Map<string, string[]>();

/** How `currency` is written around an amount: its code, its symbol and its narrow symbol («PLN», «zł»), longest
 *  first. */
function currencyMarks(currency: string): string[] {
  let found = marks.get(currency);
  if (!found) {
    const written = (['code', 'symbol', 'narrowSymbol'] as const).map(
      (currencyDisplay) =>
        new Intl.NumberFormat(FALLBACK_LOCALE, { style: 'currency', currency, currencyDisplay }).formatToParts(1).find((part) => part.type === 'currency')
          ?.value ?? currency,
    );
    found = [...new Set(written)].sort((a, b) => b.length - a.length);
    marks.set(currency, found);
  }
  return found;
}

/** `text` without the code or symbol of `money` before or after the figure. */
function withoutMark(text: string, money: Money | undefined): string {
  const upper = text.toUpperCase();
  for (const mark of money ? currencyMarks(money.currency) : []) {
    if (upper.startsWith(mark.toUpperCase())) return text.slice(mark.length);
    if (upper.endsWith(mark.toUpperCase())) return text.slice(0, -mark.length);
  }
  return text;
}

const GROUPED = (separator: string) => new RegExp(`^[1-9]\\d{0,2}(?:\\${separator}\\d{3})+$`);

/** The whole units of `integer` written with `group` as thousands separator, or `null`. */
function wholeUnits(integer: string, group: string | null): number | null {
  if (/^\d+$/.test(integer)) return Number(integer);
  if (group && GROUPED(group).test(integer)) return Number(integer.split(group).join(''));
  return null;
}

/**
 * An amount as a person types it, in either convention and in `money` («1.000», «1.000,50», «1,000.50», «12,5»,
 * «2 500», «12,50 zł»): its code or symbol around the figure is no part of it, another currency's is. A separator
 * followed by exactly three digits groups thousands; with both, the last one is the decimal one; at most the
 * currency's decimals (none in yen). While the money is unknown, two decimals and no symbol. Negative or anything
 * else is not an amount.
 */
export function readAmount(value: string | number | null | undefined, money?: Money): AmountReading {
  if (value === null || value === undefined) return { kind: 'blank' };
  const text = withoutMark(String(value).replace(/[\s\u00a0\u202f]/g, ''), money);
  if (!text) return { kind: 'blank' };
  if (!/^\d[\d.,]*$/.test(text)) return { kind: 'invalid' };
  const decimals = money?.decimals ?? UNKNOWN_DECIMALS;
  const fits = (fraction: string) => fraction.length >= 1 && fraction.length <= decimals;
  const lastDot = text.lastIndexOf('.');
  const lastComma = text.lastIndexOf(',');
  let whole: number | null;
  let fraction = '';
  if (lastDot >= 0 && lastComma >= 0) {
    const decimal = lastDot > lastComma ? '.' : ',';
    const at = text.lastIndexOf(decimal);
    fraction = text.slice(at + 1);
    if (!fits(fraction)) return { kind: 'invalid' };
    whole = wholeUnits(text.slice(0, at), decimal === '.' ? ',' : '.');
  } else if (lastDot >= 0 || lastComma >= 0) {
    const separator = lastDot >= 0 ? '.' : ',';
    whole = wholeUnits(text, separator);
    const parts = text.split(separator);
    if (whole === null && parts.length === 2 && fits(parts[1])) {
      whole = wholeUnits(parts[0], null);
      fraction = parts[1];
    }
  } else {
    whole = wholeUnits(text, null);
  }
  if (whole === null) return { kind: 'invalid' };
  return { kind: 'amount', cents: whole * 10 ** decimals + Number(fraction.padEnd(decimals, '0') || '0') };
}

/** An amount as typed → whole minor units of `money`; blank or not an amount → no bound. */
export function centsFromAmount(value: string | number | null | undefined, money?: Money): number | undefined {
  const reading = readAmount(value, money);
  return reading.kind === 'amount' ? reading.cents : undefined;
}
