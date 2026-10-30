// The money of the platform. The business's currency for the Home's amounts (BASE-G98): its country's, with its
// decimals, as `base.business.get` says it — the registry of this hub, never a call to erplora.com. Followed live (a
// change on erplora.com is pushed and arrives), one subscription for the whole tab however many pieces ask (the SDK
// shares it), and unknown until the business answers: an amount is then written without a symbol, never in the euro
// by default. And how an amount is written in the whole Hub (base-money-thousands-grouping): `formatMoney`.
import { useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef } from 'vue';

/** A currency (ISO 4217) and its decimals: the business's, as `base.business.get` says them (BASE-G98), or a record's
 *  own (an invoice keeps the one it was issued in). */
export interface Money {
  currency: string;
  decimals: number;
}

export function useBusinessMoney(): ComputedRef<Money | undefined> {
  const { data } = useLive('base.business.get', {});
  return computed(() => (data.value ? { currency: data.value.currency, decimals: data.value.currency_decimals } : undefined));
}

const FALLBACK_LOCALE = 'en';
/** The decimals of an amount whose currency is not known yet. */
const UNKNOWN_DECIMALS = 2;

const formats = new Map<string, Intl.NumberFormat>();

// Grouped always (hub#1090): the Spanish CLDR waits for five digits (minimumGroupingDigits 2) and would write
// «1234,56 €» beside «12.345,67 €»; Holded, Sage, a3ERP, Odoo, Shopify and Spanish shops group from four.
function moneyFormat(locale: string, money: Money | undefined): Intl.NumberFormat {
  const decimals = money?.decimals ?? UNKNOWN_DECIMALS;
  const id = `${locale}|${money?.currency ?? ''}|${decimals}`;
  let found = formats.get(id);
  if (!found) {
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals, useGrouping: 'always' } as const;
    // The symbol a till of that country prints («zł», «€», «$»); until the currency is known, the figure alone.
    const options: Intl.NumberFormatOptions = money
      ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits }
      : digits;
    try {
      found = new Intl.NumberFormat(locale, options);
    } catch (error) {
      if (!(error instanceof RangeError) || locale === FALLBACK_LOCALE) throw error;
      found = moneyFormat(FALLBACK_LOCALE, money);
    }
    formats.set(id, found);
  }
  return found;
}

/** `minor` (the minor unit of `money`'s currency, as the server keeps every amount: 123456 is 1.234,56 €, ¥123,456
 *  has no cents) as `money` in `locale`, its thousands grouped from four digits on: «1.234,56 €», «€1,234.56»,
 *  «123.400 ¥»; «1.234,56» while the currency is unknown. Nothing to show is «—». */
export function formatMoney(minor: number | null | undefined, locale: string, money?: Money): string {
  if (minor === null || minor === undefined || Number.isNaN(minor)) return '—';
  return moneyFormat(locale, money).format(minor / 10 ** (money?.decimals ?? UNKNOWN_DECIMALS));
}
