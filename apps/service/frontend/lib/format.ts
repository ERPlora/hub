// How the service screens paint money, discounts and days (pages never format by hand), always with the
// page language's own format (Intl). Money is whole minor units of the business's currency (flow
// service-business-currency; `useBusinessMoney`, the platform's: its country's currency with the decimals the
// server counts it in, never the browser's Intl, which gives the forint none): 1500 is ¥1,500 in Japan and
// 15,00 € in Spain, as Sales charges it, written with the platform's `formatMoney`: its thousands grouped from four
// digits on, as every screen writes them. Until the business answers an amount is a figure without a symbol, never
// the euro by default. A percentage discount travels in basis points (1050 = 10,50 %): the form writes and reads
// it as a percentage with at most two decimals.
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { formatMoney, useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while the currency is unknown. */
const UNKNOWN_DECIMALS = 2;

/** The decimals of an amount in `money` (2 in EUR and HUF, 0 in JPY): its minor unit; two while it is unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? UNKNOWN_DECIMALS;

const formats = new Map<string, Intl.NumberFormat>();
const days = new Map<string, Intl.DateTimeFormat>();

function numberFormat(locale: string, kind: 'percent' | 'plain'): Intl.NumberFormat {
  const key = `${locale}|${kind}`;
  let found = formats.get(key);
  if (!found) {
    const options: Record<typeof kind, Intl.NumberFormatOptions> = {
      percent: { style: 'percent', maximumFractionDigits: 2 },
      plain: { maximumFractionDigits: 2, useGrouping: false },
    };
    found = new Intl.NumberFormat(locale, options[kind]);
    formats.set(key, found);
  }
  return found;
}

/** Basis points as a percentage in `locale` («10,5 %», «10.5%»). */
export function formatPercentBp(bp: number, locale: string): string {
  return numberFormat(locale, 'percent').format(bp / 10000);
}

/** Basis points for a percentage field, in the page format, ungrouped («10,5»). */
export function percentFieldText(bp: number, locale: string): string {
  return numberFormat(locale, 'plain').format(bp / 100);
}

/** What a percentage field holds, in basis points (empty = 0); `null` when it is not 0–100 with ≤ 2 decimals. */
export function readPercentBp(text: string): number | null {
  const raw = text.replace(/[%\s]/g, '').replace(',', '.');
  if (raw === '') return 0;
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(raw)) return null;
  const bp = Math.round(Number(raw) * 100);
  return bp <= 10000 ? bp : null;
}

/** The day of a moment in `locale` («13 oct 2026», «Oct 13, 2026»); `''` for nothing. */
export function formatDate(value: string | null | undefined, locale: string, timeZone?: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const key = `${locale}|${timeZone ?? ''}`;
  let found = days.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeZone });
    days.set(key, found);
  }
  return found.format(date);
}
