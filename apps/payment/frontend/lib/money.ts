// The amount field of «New payment» and the amount filter of the list (PAYMENT-F02; the old pm#521):
// what a person types or pastes, read into whole cents (the euro sign and
// spaces around are noise; with both marks the rightmost one is the decimal one; at most two decimals).
// A negative amount says it cannot be negative; one mark followed by three digits («1.250») can be
// 1.250 € or 1,25 €: it is not guessed, the field says so. On leaving the field it is rewritten in
// the page format. (The same reader as the inventory's forms; an app never imports another's code.)
import { decimalMark } from './format';

export type MoneyRead =
  | { ok: true; cents: number | null }
  | { ok: false; reason: 'not_amount' }
  | { ok: false; reason: 'negative' }
  | { ok: false; reason: 'ambiguous'; grouped: number; decimal: number };

const NOT_AMOUNT: MoneyRead = { ok: false, reason: 'not_amount' };
/** Far above any price, still exact in a double. */
const MAX_DIGITS = 15;

const cents = (whole: string, fraction = ''): number => Number(whole || '0') * 100 + Number(fraction.padEnd(2, '0') || '0');

/** «1.234.567» (one mark, repeated): thousands groups, or `null` when the groups are broken. */
function grouped(raw: string, mark: string): number | null {
  const [head, ...groups] = raw.split(mark);
  if (!/^[1-9]\d{0,2}$/.test(head) || groups.some((group) => !/^\d{3}$/.test(group))) return null;
  return cents(head + groups.join(''));
}

/** What a money field holds: cents (`null` when empty), or why it is not an amount. */
export function parseMoney(text: string): MoneyRead {
  const raw = text.replace(/[€\s  ]|EUR/gi, '');
  if (raw === '') return { ok: true, cents: null };
  if (raw.startsWith('-')) {
    const positive = parseMoney(raw.slice(1));
    return positive.ok && positive.cents !== null ? { ok: false, reason: 'negative' } : NOT_AMOUNT;
  }
  if (!/^[\d.,]+$/.test(raw) || !/^\d/.test(raw) || raw.replace(/\D/g, '').length > MAX_DIGITS) return NOT_AMOUNT;
  const lastComma = raw.lastIndexOf(',');
  const lastDot = raw.lastIndexOf('.');
  if (lastComma >= 0 && lastDot >= 0) {
    const decimal = lastComma > lastDot ? ',' : '.';
    const at = Math.max(lastComma, lastDot);
    const whole = raw.slice(0, at);
    const fraction = raw.slice(at + 1);
    if (whole.includes(decimal) || !/^\d{1,2}$/.test(fraction)) return NOT_AMOUNT;
    return { ok: true, cents: cents(whole.replace(/[.,]/g, ''), fraction) };
  }
  const mark = lastComma >= 0 ? ',' : lastDot >= 0 ? '.' : '';
  if (!mark) return { ok: true, cents: cents(raw) };
  const parts = raw.split(mark);
  if (parts.length > 2) {
    const value = grouped(raw, mark);
    return value === null ? NOT_AMOUNT : { ok: true, cents: value };
  }
  const [whole, fraction] = parts;
  if (/^\d{1,2}$/.test(fraction)) return { ok: true, cents: cents(whole, fraction) };
  if (!/^\d{3}$/.test(fraction)) return NOT_AMOUNT;
  // Three digits after one mark: thousands, or a third decimal a price cannot have unless it is 0.
  const asGroups = grouped(raw, mark);
  const asDecimal = fraction.endsWith('0') ? cents(whole, fraction.slice(0, 2)) : null;
  if (asGroups !== null && asDecimal !== null) return { ok: false, reason: 'ambiguous', grouped: asGroups, decimal: asDecimal };
  if (asGroups !== null) return { ok: true, cents: asGroups };
  return asDecimal === null ? NOT_AMOUNT : { ok: true, cents: asDecimal };
}

/** Cents as the field shows them: the page's decimal mark, two decimals, ungrouped; `''` for none. */
export function moneyFieldText(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined) return '';
  const whole = Math.trunc(value / 100);
  const fraction = String(Math.abs(value % 100)).padStart(2, '0');
  return `${whole}${decimalMark(locale)}${fraction}`;
}

/** The field once the person leaves it: the page format when readable, as typed when not. */
export function normaliseMoneyText(text: string, locale: string): string {
  const read = parseMoney(text);
  return read.ok && read.cents !== null ? moneyFieldText(read.cents, locale) : text;
}
