// A money field of the combo forms (a menu's closed price, a choice's supplement): what a person types
// or pastes, read into whole minor units of the business's currency. Its code or its symbol («PLN», «zł»;
// «JPY», «¥») and the spaces around are noise, any other currency's is not; with both marks the rightmost one
// is the decimal one; at most the currency's decimals (none in yen). While the money is unknown, two decimals
// and no symbol to take away (never a euro by default). One mark followed by three digits («1.250») can be
// 1.250 zł or 1,25 zł: it is not guessed, the field says so. A price is never negative; a supplement may be
// (`signed`), a cheaper substitution. On leaving the field it is rewritten in the page format. (The reader of
// the service, inventory and modifier forms, with the sign: an app never imports another's code.)
import { decimalMark, type Money, moneyDecimals } from './format';

export type MoneyRead =
  | { ok: true; cents: number | null }
  | { ok: false; reason: 'not_amount' }
  | { ok: false; reason: 'negative' }
  | { ok: false; reason: 'ambiguous'; grouped: number; decimal: number };

export interface MoneyOptions {
  /** A negative amount is read (a supplement), instead of refused (a price). */
  signed?: boolean;
  /** The business's currency (`useBusinessMoney`); unknown while it has not answered. */
  money?: Money;
}

const NOT_AMOUNT: MoneyRead = { ok: false, reason: 'not_amount' };
/** Far above any price, still exact in a double. */
const MAX_DIGITS = 15;

const DIGITS = /^\d+$/;
const marks = new Map<string, RegExp>();

/** How `currency` is written around an amount: its code, its symbol and its narrow symbol («PLN», «zł»; «JPY», «¥»). */
function currencyMarks(currency: string): RegExp {
  let found = marks.get(currency);
  if (!found) {
    const written = (['code', 'symbol', 'narrowSymbol'] as const).map(
      (currencyDisplay) =>
        new Intl.NumberFormat('en', { style: 'currency', currency, currencyDisplay }).formatToParts(1).find((part) => part.type === 'currency')
          ?.value ?? currency,
    );
    const escaped = [...new Set(written)].sort((a, b) => b.length - a.length).map((mark) => mark.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    found = new RegExp(escaped.join('|'), 'gi');
    marks.set(currency, found);
  }
  return found;
}

/** `whole` major units and `fraction` digits (at most `decimals` of them) as minor units. */
const cents = (whole: string, fraction: string, decimals: number): number =>
  Number(whole || '0') * 10 ** decimals + Number(fraction.padEnd(decimals, '0') || '0');

/** «1.234.567» (one mark, repeated): thousands groups, or `null` when the groups are broken. */
function grouped(raw: string, mark: string, decimals: number): number | null {
  const [head, ...groups] = raw.split(mark);
  if (!/^[1-9]\d{0,2}$/.test(head) || groups.some((group) => !/^\d{3}$/.test(group))) return null;
  return cents(head + groups.join(''), '', decimals);
}

/** The reading of an amount without a sign, with at most `decimals` decimals. */
function unsigned(raw: string, decimals: number): MoneyRead {
  if (!/^[\d.,]+$/.test(raw) || !/^\d/.test(raw) || raw.replace(/\D/g, '').length > MAX_DIGITS) return NOT_AMOUNT;
  const fits = (fraction: string) => DIGITS.test(fraction) && fraction.length <= decimals;
  const lastComma = raw.lastIndexOf(',');
  const lastDot = raw.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    const decimal = lastComma > lastDot ? ',' : '.';
    const at = Math.max(lastComma, lastDot);
    const whole = raw.slice(0, at);
    const fraction = raw.slice(at + 1);
    if (whole.includes(decimal) || !fits(fraction)) return NOT_AMOUNT;
    return { ok: true, cents: cents(whole.replace(/[.,]/g, ''), fraction, decimals) };
  }
  const mark = lastComma >= 0 ? ',' : lastDot >= 0 ? '.' : '';
  if (!mark) return { ok: true, cents: cents(raw, '', decimals) };
  const parts = raw.split(mark);
  if (parts.length > 2) {
    const value = grouped(raw, mark, decimals);
    return value === null ? NOT_AMOUNT : { ok: true, cents: value };
  }
  const [whole, fraction] = parts;
  if (fits(fraction)) return { ok: true, cents: cents(whole, fraction, decimals) };
  if (!/^\d{3}$/.test(fraction)) return NOT_AMOUNT;
  // Three digits after one mark: thousands, or decimals a price cannot have unless the extra ones are 0.
  const asGroups = grouped(raw, mark, decimals);
  const asDecimal = decimals > 0 && /^0+$/.test(fraction.slice(decimals)) ? cents(whole, fraction.slice(0, decimals), decimals) : null;
  if (asGroups !== null && asDecimal !== null) return { ok: false, reason: 'ambiguous', grouped: asGroups, decimal: asDecimal };
  if (asGroups !== null) return { ok: true, cents: asGroups };
  return asDecimal === null ? NOT_AMOUNT : { ok: true, cents: asDecimal };
}

/** What a money field holds in the business's money: minor units (`null` when empty), or why it is not an amount. */
export function parseMoney(text: string, options: MoneyOptions = {}): MoneyRead {
  const spaced = text.replace(/\s/g, '');
  const raw = options.money ? spaced.replace(currencyMarks(options.money.currency), '') : spaced;
  if (raw === '') return { ok: true, cents: null };
  const decimals = moneyDecimals(options.money);
  if (raw.startsWith('-')) {
    const positive = unsigned(raw.slice(1), decimals);
    if (!positive.ok || positive.cents === null) return positive.ok ? NOT_AMOUNT : positive;
    return options.signed ? { ok: true, cents: -positive.cents } : { ok: false, reason: 'negative' };
  }
  return unsigned(raw, decimals);
}

/** Minor units as the field shows them: the page's decimal mark, the decimals of `money`, ungrouped, with its
 *  sign; `''` for none. */
export function moneyFieldText(value: number | null | undefined, locale: string, money?: Money): string {
  if (value === null || value === undefined) return '';
  const decimals = moneyDecimals(money);
  const scale = 10 ** decimals;
  const sign = value < 0 ? '-' : '';
  const absolute = Math.abs(value);
  const whole = Math.trunc(absolute / scale);
  if (!decimals) return `${sign}${whole}`;
  return `${sign}${whole}${decimalMark(locale)}${String(absolute % scale).padStart(decimals, '0')}`;
}

/** The field once the person leaves it: the page format when readable, as typed when not. */
export function normaliseMoneyText(text: string, locale: string, options: MoneyOptions = {}): string {
  const read = parseMoney(text, options);
  return read.ok && read.cents !== null ? moneyFieldText(read.cents, locale, options.money) : text;
}
