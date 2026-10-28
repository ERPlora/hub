// How the modifier screens paint a supplement and a group's rule (pages never format by hand), in the page
// language's own format (Intl). Money is whole minor units of the business's currency (`useBusinessMoney`, the
// platform's: its country's currency with the decimals the server counts it in, never the browser's Intl, which
// gives none to the forint). Until the business answers an amount is a figure without a symbol, never the euro
// by default. A supplement may be negative (a discount) and carries its sign; 0 is free.
import type { Money } from '../../../../base/frontend/lib/home';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while the currency is unknown. */
const UNKNOWN_DECIMALS = 2;

/** The decimals of an amount in `money`; two while it is unknown. */
export const moneyDecimals = (money?: Money): number => money?.decimals ?? UNKNOWN_DECIMALS;

const formats = new Map<string, Intl.NumberFormat>();
const decimalMarks = new Map<string, string>();

function moneyFormat(locale: string, signed: boolean, money: Money | undefined): Intl.NumberFormat {
  const decimals = moneyDecimals(money);
  const key = `${locale}|${signed}|${money?.currency ?? ''}|${decimals}`;
  let found = formats.get(key);
  if (!found) {
    const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
    const sign: Intl.NumberFormatOptions = signed ? { signDisplay: 'exceptZero' } : {};
    // The symbol a till of that country prints («zł», «¥»); until the business is known, the figure alone.
    const style: Intl.NumberFormatOptions = money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol' } : {};
    found = new Intl.NumberFormat(locale, { ...style, ...digits, ...sign });
    formats.set(key, found);
  }
  return found;
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

/** Minor units in `money`, in `locale` («1,50 zł», «zł 1.50», «¥150»; «1,50» while it is unknown). */
export function formatMoney(cents: number, locale: string, money?: Money): string {
  return moneyFormat(locale, false, money).format(cents / 10 ** moneyDecimals(money));
}

/** A supplement in `money` with its sign («+1,00 zł», «-0,50 zł»; «+1,00» while it is unknown); `free` for 0. */
export function formatDelta(cents: number, locale: string, free: string, money?: Money): string {
  return cents === 0 ? free : moneyFormat(locale, true, money).format(cents / 10 ** moneyDecimals(money));
}

/** What `choiceRule` reads of a group. */
export interface GroupRule {
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
}

type Translate = (key: string, named?: Record<string, unknown>) => string;

/** «Optional» or «Required (min. N)», then « · max. N» with a ceiling and « · repeats» when it repeats. */
export function choiceRule(group: GroupRule, t: Translate): string {
  const parts = [group.min_choices >= 1 ? t('modifier.rule.required', { min: group.min_choices }) : t('modifier.rule.optional')];
  if (group.max_choices > 0) parts.push(t('modifier.rule.max', { max: group.max_choices }));
  if (group.allow_repeat) parts.push(t('modifier.rule.repeat'));
  return parts.join(' · ');
}
