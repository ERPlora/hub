// How the cart_checkout screens paint money, quantities and statuses (pages never format by hand), always
// in the page language's own format (Intl), and how a range filter typed in the unit the column shows
// reaches the server. An amount is whole minor units of the row's own currency: its scale comes from
// Intl (2 decimals in EUR, 0 in JPY, 3 in KWD). A quantity is a decimal string from the server
// (`"2.500"`), painted without decorative zeros.
import type { StatusPillTone } from '@erplora/ui/components';

import type { CartStatus, OrderStatus } from '../operations';

/** The business's currency until the Hub keeps its own (the server's `business_currency()`). */
export const CURRENCY = 'EUR';

const money = new Map<string, Intl.NumberFormat>();
const quantities = new Map<string, Intl.NumberFormat>();

function moneyFormat(locale: string, currency: string): Intl.NumberFormat {
  const key = `${locale}|${currency}`;
  let found = money.get(key);
  if (!found) {
    // `always`: Spanish CLDR leaves a four-digit amount ungrouped («1234,56 €» above «12.345,60 €»);
    // Odoo and Business Central group it, and so did the old hub (hub#1090).
    found = new Intl.NumberFormat(locale, { style: 'currency', currency, useGrouping: 'always' });
    money.set(key, found);
  }
  return found;
}

/** How many decimals the minor unit of `currency` has (2 in EUR, 0 in JPY, 3 in KWD). */
export function currencyDecimals(currency: string = CURRENCY): number {
  return moneyFormat('en', currency).resolvedOptions().maximumFractionDigits ?? 2;
}

/** Whole minor units of `currency` in `locale` («31,50 €», «€31.50», «¥1,999»). */
export function formatMoney(minor: number, locale: string, currency: string = CURRENCY): string {
  return moneyFormat(locale, currency).format(minor / 10 ** currencyDecimals(currency));
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

/** A money bound typed or pasted in the major unit («12», «12,5», «1.250,50», «1.234,56 €») → minor
 *  units of `currency`; nothing when it is not an amount (never «from 0»). The same reading as a money
 *  field (pm#521): with both marks the rightmost is the decimal one; one mark repeated groups
 *  thousands; one mark and three digits are thousands unless the currency has three decimals, and when
 *  they end in 0 («1.250»: 1.250 € or 1,25 €) the bound is not guessed. */
export function toMinor(text: string | undefined, currency: string = CURRENCY): number | undefined {
  const raw = (text ?? '').replace(/[\s  €]/g, '').replace(new RegExp(currency, 'gi'), '');
  if (!/^\d[\d.,]*$/.test(raw) || raw.replace(/\D/g, '').length > MAX_DIGITS) return undefined;
  const decimals = currencyDecimals(currency);
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
  return whole === undefined || fraction.endsWith('0') ? undefined : minor(whole, '', decimals);
}


/** The two ends of the Total filter, as the table names them. */
export const TOTAL_BOUNDS = ['total_amount_from', 'total_amount_to'] as const;

/** The ends of the Total filter typed but not readable as an amount: they filter nothing and say so. */
export function unreadableTotals(filters: Readonly<Record<string, unknown>>): string[] {
  return TOTAL_BOUNDS.filter((name) => {
    const text = filters[name];
    return typeof text === 'string' && text.trim() !== '' && toMinor(text) === undefined;
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
