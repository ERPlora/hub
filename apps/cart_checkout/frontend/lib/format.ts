// How the cart_checkout screens paint money, quantities and statuses (pages never format by hand), always in the
// page language's own format (Intl), and how a quantity range typed in the unit the column shows reaches the server
// (the Total filter is read by the platform, as every amount filter of the Hub: `filterCents`, hub#1196). An amount is
// whole minor units of a currency with the decimals the server counts it in
// (`currency_decimals`: 2 in PLN and in HUF, 0 in JPY), never the browser's Intl (which gives the forint none): a
// cart or an order in its own currency (a record is never rewritten), what a person types in the business's
// (`useBusinessMoney`, the platform's: its country's; flow cart-checkout-business-currency). Until the business
// answers an amount is a dash, never the euro by default nor guessed decimals. A quantity is a decimal string from
// the server (`"2.500"`), written with the platform's `formatQuantity`: without decorative zeros and grouped from four
// digits on («1.500»), as the till and the stock write it (hub#974).
import type { StatusPillTone } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';
import { formatMoney as writeMoney } from '../../../../base/frontend/lib/money';
import type { CartStatus, OrderStatus } from '../operations';

export type { Money };
export { amountFilterErrors, filterCents, useBusinessMoney } from '../../../../base/frontend/lib/money';
export { formatQuantity } from '@erplora/ui/components';

/** Whole minor units in `of`, in `locale` («42,50 zł», «€31.50», «¥1,999»; «—» while it is unknown). */
export function formatMoney(minor: number, locale: string, of?: Money): string {
  return writeMoney(minor, locale, of);
}

/** The money of a cart or an order: its own currency, with the decimals the server counts it in. */
export function recordMoney(record: { currency: string; currency_decimals: number }): Money {
  return { currency: record.currency, decimals: record.currency_decimals };
}

/** The two ends of the Total filter, as the table names them. */
export const TOTAL_BOUNDS = ['total_amount_from', 'total_amount_to'] as const;

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
