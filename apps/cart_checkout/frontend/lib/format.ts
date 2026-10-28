// How the cart_checkout screens paint money, quantities and statuses (pages never format by hand), always
// in the page language's own format (Intl), and how a range filter typed in the unit the column shows
// reaches the server. An amount is whole minor units of a currency with the decimals the server counts it in
// (`currency_decimals`: 2 in PLN and in HUF, 0 in JPY), never the browser's Intl (which gives the forint none): a
// cart or an order in its own currency (a record is never rewritten), what a person types in the business's
// (`useBusinessMoney`, the platform's: its country's; flow cart-checkout-business-currency). Until the business
// answers an amount is a figure without a symbol, never the euro by default. A quantity is a decimal string from
// the server (`"2.500"`), painted without decorative zeros.
import type { StatusPillTone } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';
import type { CartStatus, OrderStatus } from '../operations';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while its currency is unknown. */
const UNKNOWN_DECIMALS = 2;

const money = new Map<string, Intl.NumberFormat>();
const quantities = new Map<string, Intl.NumberFormat>();

function moneyFormat(locale: string, of: Money | undefined, symbol = true): Intl.NumberFormat {
  const decimals = of?.decimals ?? UNKNOWN_DECIMALS;
  const key = `${locale}|${symbol ? (of?.currency ?? '') : ''}|${decimals}`;
  let found = money.get(key);
  if (!found) {
    // The symbol a till of that country prints («zł», «¥»); until the currency is known, the figure alone.
    const style: Intl.NumberFormatOptions = of && symbol ? { style: 'currency', currency: of.currency, currencyDisplay: 'narrowSymbol' } : {};
    // `always`: Spanish CLDR leaves a four-digit amount ungrouped («1234,56 €» above «12.345,60 €»);
    // Odoo and Business Central group it, and so did the old hub (hub#1090).
    found = new Intl.NumberFormat(locale, { ...style, minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' });
    money.set(key, found);
  }
  return found;
}

/** Whole minor units in `of`, in `locale` («42,50 zł», «€31.50», «¥1,999»; «31,50» while it is unknown). */
export function formatMoney(minor: number, locale: string, of?: Money): string {
  return moneyFormat(locale, of).format(minor / 10 ** (of?.decimals ?? UNKNOWN_DECIMALS));
}

/** The money of a cart or an order: its own currency, with the decimals the server counts it in. */
export function recordMoney(record: { currency: string; currency_decimals: number }): Money {
  return { currency: record.currency, decimals: record.currency_decimals };
}

/** The amount the hint under an unreadable Total shows, with the decimals of `of` («12.50», «12», «12,500»). */
export function amountExample(locale: string, of?: Money): string {
  const decimals = of?.decimals ?? UNKNOWN_DECIMALS;
  return moneyFormat(locale, of, false).format(decimals === 0 ? 12 : 12.5);
}

/** A quantity in `locale`, without decorative zeros («2», «0,5»); anything else as is. */
export function formatQuantity(value: string | number, locale: string): string {
  const number = Number(value);
  if (value === '' || Number.isNaN(number)) return String(value);
  let found = quantities.get(locale);
  if (!found) {
    found = new Intl.NumberFormat(locale, { maximumFractionDigits: 3, useGrouping: false });
    quantities.set(locale, found);
  }
  return found.format(number);
}

/** Far above any total, still exact in a double. */
const MAX_DIGITS = 15;

/** Whole units and their decimals (as typed) → minor units with `decimals` places. */
const minor = (whole: string, fraction: string, decimals: number): number =>
  Number(whole || '0') * 10 ** decimals + Number(fraction.padEnd(decimals, '0') || '0');

/** «1.234.567» (one mark, repeated): its thousands groups as whole units, or nothing when broken. */
function grouped(raw: string, mark: string): string | undefined {
  const [head, ...groups] = raw.split(mark);
  if (!/^[1-9]\d{0,2}$/.test(head) || groups.some((group) => !/^\d{3}$/.test(group))) return undefined;
  return head + groups.join('');
}

const marks = new Map<string, string[]>();

/** How `currency` is written around an amount: its code, its symbol and its narrow symbol («PLN», «zł»), longest
 *  first. */
function currencyMarks(currency: string): string[] {
  let found = marks.get(currency);
  if (!found) {
    const written = (['code', 'symbol', 'narrowSymbol'] as const).map(
      (currencyDisplay) =>
        new Intl.NumberFormat('en', { style: 'currency', currency, currencyDisplay }).formatToParts(1).find((part) => part.type === 'currency')?.value ??
        currency,
    );
    found = [...new Set(written)].sort((a, b) => b.length - a.length);
    marks.set(currency, found);
  }
  return found;
}

/** `raw` without the code or symbol of `of` before or after the figure; another currency's stays (no amount). */
function withoutMark(raw: string, of: Money | undefined): string {
  const upper = raw.toUpperCase();
  for (const mark of of ? currencyMarks(of.currency) : []) {
    if (upper.startsWith(mark.toUpperCase())) return raw.slice(mark.length);
    if (upper.endsWith(mark.toUpperCase())) return raw.slice(0, -mark.length);
  }
  return raw;
}

/** A money bound typed or pasted in the major unit of `of` («12», «12,5», «1.250,50», «12,50 zł») → its minor
 *  units; nothing when it is not an amount of it (never «from 0»), another currency's symbol included. The same
 *  reading as a money field (pm#521): with both marks the rightmost is the decimal one; one mark repeated groups
 *  thousands; one mark and three digits are thousands unless the currency has three decimals, and when they end in
 *  0 in a currency with decimals («1.250»: 1.250 zł or 1,25 zł) the bound is not guessed. While the business has
 *  not answered, two decimals and no symbol. */
export function toMinor(text: string | undefined, of?: Money): number | undefined {
  const raw = withoutMark((text ?? '').replace(/[\s\u00a0\u202f]/g, ''), of);
  if (!/^\d[\d.,]*$/.test(raw) || raw.replace(/\D/g, '').length > MAX_DIGITS) return undefined;
  const decimals = of?.decimals ?? UNKNOWN_DECIMALS;
  const decimal = (whole: string, fraction: string): number | undefined =>
    fraction.length >= 1 && fraction.length <= decimals && /^\d+$/.test(fraction) ? minor(whole, fraction, decimals) : undefined;
  const at = Math.max(raw.lastIndexOf(','), raw.lastIndexOf('.'));
  if (at < 0) return minor(raw, '', decimals);
  const mark = raw[at];
  const other = mark === ',' ? '.' : ',';
  const head = raw.slice(0, at);
  const fraction = raw.slice(at + 1);
  if (head.includes(other)) {
    // Both marks: the rightmost is the decimal one, the other one groups thousands.
    const whole = head.includes(mark) ? undefined : grouped(head, other);
    return whole === undefined ? undefined : decimal(whole, fraction);
  }
  if (head.includes(mark)) {
    const whole = grouped(raw, mark);
    return whole === undefined ? undefined : minor(whole, '', decimals);
  }
  if (fraction.length !== 3 || decimals >= 3) return decimal(head, fraction);
  const whole = grouped(raw, mark);
  return whole === undefined || (decimals > 0 && fraction.endsWith('0')) ? undefined : minor(whole, '', decimals);
}

/** The two ends of the Total filter, as the table names them. */
export const TOTAL_BOUNDS = ['total_amount_from', 'total_amount_to'] as const;

/** The ends of the Total filter typed but not readable as an amount of `of`: they filter nothing and say so. */
export function unreadableTotals(filters: Readonly<Record<string, unknown>>, of?: Money): string[] {
  return TOTAL_BOUNDS.filter((name) => {
    const text = filters[name];
    return typeof text === 'string' && text.trim() !== '' && toMinor(text, of) === undefined;
  });
}

/** A quantity bound typed by a person («2», «0,5») → the decimal the server reads; nothing when it is
 *  not a quantity of at most three decimals. */
export function toQuantity(text: string | undefined): string | undefined {
  const raw = (text ?? '').trim().replace(',', '.');
  return /^\d+(\.\d{1,3})?$/.test(raw) ? raw : undefined;
}

/** The tone of each cart status's pill: open, set aside, done, gone stale. */
export const CART_TONE: Readonly<Record<CartStatus, StatusPillTone>> = Object.freeze({
  active: 'info',
  abandoned: 'warning',
  converted: 'success',
  expired: 'neutral',
});

/** The tone of each order status's pill: waiting, marked paid, failed, done. */
export const ORDER_TONE: Readonly<Record<OrderStatus, StatusPillTone>> = Object.freeze({
  initiated: 'neutral',
  paid: 'info',
  failed: 'danger',
  completed: 'success',
});
