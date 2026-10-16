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
    found = new Intl.NumberFormat(locale, { style: 'currency', currency });
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

/** A money bound typed in the major unit («12», «12,5») → minor units of `currency`; nothing when it
 *  is not an amount (never «from 0»). */
export function toMinor(text: string | undefined, currency: string = CURRENCY): number | undefined {
  const raw = (text ?? '').trim();
  if (!/^\d+([.,]\d+)?$/.test(raw)) return undefined;
  return Math.round(Number(raw.replace(',', '.')) * 10 ** currencyDecimals(currency));
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
