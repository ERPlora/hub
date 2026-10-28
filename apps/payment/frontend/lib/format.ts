// How the payment screens paint money, days and statuses (pages never format by hand), always in the
// page language's own format (Intl). An amount is whole minor units of a money: a payment's own currency, with the
// decimals the server counts it in (`currency_decimals`: 2 in EUR and in the forint, 0 in JPY, 3 in KWD), never the
// browser's Intl decimals (which give the forint none); what a person types is in the business's money
// (`useBusinessMoney`: its country's currency). While it is unknown, a figure without a symbol, never the euro by
// default. A payment date is a calendar day (`YYYY-MM-DD`), painted in UTC so the browser's time zone never moves it
// a day.
import type { StatusPillTone } from '@erplora/ui/components';

import type { Money } from '../../../../base/frontend/lib/home';
import type { PaymentOut, PaymentStatus } from '../operations';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while its money is unknown. */
const NO_MONEY_DECIMALS = 2;

const money = new Map<string, Intl.NumberFormat>();
const days = new Map<string, Intl.DateTimeFormat>();
const decimalMarks = new Map<string, string>();

/** The decimals of `value` (2 in EUR and HUF, 0 in JPY): its minor unit; two while unknown. */
export const moneyDecimals = (value?: Money): number => value?.decimals ?? NO_MONEY_DECIMALS;

function moneyFormat(locale: string, value: Money | undefined): Intl.NumberFormat {
  const decimals = moneyDecimals(value);
  const key = `${locale}|${value?.currency ?? ''}|${decimals}`;
  let found = money.get(key);
  if (!found) {
    // Grouped always: Spanish CLDR waits for five digits (minimumGroupingDigits 2) and would paint
    // «1234,56 €» here beside «1.234,56 €» in the other screens (hub#1090). The symbol a till of that country
    // prints («zł», «Ft»); until the money is known, the figure alone.
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' as const };
    found = new Intl.NumberFormat(
      locale,
      value ? { style: 'currency', currency: value.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits,
    );
    money.set(key, found);
  }
  return found;
}

/** Whole minor units of `value` in `locale` («12,50 €», «€12.50», «zł 12.50», «¥1,999»; «12,50» while unknown). */
export function formatMoney(minor: number, locale: string, value?: Money): string {
  return moneyFormat(locale, value).format(minor / 10 ** moneyDecimals(value));
}

/** The money of a payment: the currency it was recorded in, with the decimals the server says for it. */
export function paymentMoney(payment: Pick<PaymentOut, 'currency' | 'currency_decimals'>): Money {
  return { currency: payment.currency, decimals: payment.currency_decimals };
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

/** A calendar day (or the date half of a moment) as `locale` writes it («13/07/2026»); anything else as is. */
export function formatDay(value: string | null | undefined, locale: string): string {
  const raw = value ?? '';
  const iso = raw.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return raw;
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return raw;
  let found = days.get(locale);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
    days.set(locale, found);
  }
  return found.format(date);
}

/** The device's own day as `YYYY-MM-DD` (a date field's value), never the UTC one. */
export function localDay(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** The tone of each status's pill: inert, in progress, waiting on the bank, done, stopped. */
export const STATUS_TONE: Readonly<Record<PaymentStatus, StatusPillTone>> = Object.freeze({
  draft: 'neutral',
  approved: 'info',
  sent: 'warning',
  completed: 'success',
  cancelled: 'danger',
});
