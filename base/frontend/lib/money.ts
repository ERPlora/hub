// The business's currency for the Home's amounts, as this hub's `base.business.get` says it, never a call to
// erplora.com. One subscription serves the whole tab however many pieces ask (the SDK shares it). Until the business
// answers an amount is a dash, never euros by default nor guessed decimals.
import { type DataTableFilters, formatMoney as writeMoney, moneyExamples, parseMoney } from '@erplora/ui/components';
import { type ApiError, useLive } from '@erplora/ui/sdk';
import { computed, type ComputedRef, type Ref } from 'vue';

import type { Money } from './home';

/** Minor units in `money`, in `locale`, its thousands grouped («1.234,50 €», «€22.50», «¥1,500»; «—» while it is
 *  unknown): the platform's way of writing an amount, for the screens whose amount is always a number. */
export const formatMoney: (cents: number, locale: string, money?: Money) => string = writeMoney;

/** How an amount end of a table filter is read: `signed` takes a minus (a difference); any other end cannot be
 *  negative, like a price. */
export interface FilterAmountOptions {
  signed?: boolean;
}

/** Minor units of an amount end typed in a table filter, read like the money field (`parseMoney`) in `money`;
 *  nothing when it is empty or cannot be read, so that end does not filter (never «from 0»; hub#924). Every list
 *  reads its amount filter with it (hub#1196). */
export function filterCents(text: string | undefined, money?: Money, options: FilterAmountOptions = {}): number | undefined {
  if (!text) return undefined;
  const read = parseMoney(text, { money, signed: options.signed });
  return read.ok && read.cents !== null ? read.cents : undefined;
}

/** What a list says an amount end with: its translator and language, the business's money (unknown until it
 *  answers) and the ends that take a minus. */
export interface AmountFilterSay {
  t: (key: string, named?: Record<string, unknown>) => string;
  locale: string;
  money?: Money;
  signed?: readonly string[];
}

/** What the table says under each of `ends` typed in `values` that is no amount of the business's money: the money
 *  field's own words (`MoneyInput`) — not an amount, with its example in that money («12,50», «12» in yen),
 *  negative, or «1.000» that reads two ways, with both readings — so every list says it alike (hub#1196). An empty
 *  end or an amount says nothing, and nothing is judged while the money is unknown, as the money field does not
 *  (hub#945). */
export function amountFilterErrors(values: DataTableFilters, ends: readonly string[], say: AmountFilterSay): Record<string, string> {
  const errors: Record<string, string> = {};
  const { money, t, locale } = say;
  if (!money) return errors;
  for (const end of ends) {
    const typed = values[end] ?? '';
    const read = parseMoney(typed, { money, signed: say.signed?.includes(end) });
    if (read.ok) continue;
    if (read.reason === 'not_amount') errors[end] = t('base.money.filter.notAmount', { amount: moneyExamples(locale, money).amount });
    else if (read.reason === 'negative') errors[end] = t('base.money.filter.negative');
    else {
      const grouped = writeMoney(read.grouped, locale, money);
      errors[end] = t('base.money.filter.ambiguous', { typed: typed.trim(), grouped, decimal: writeMoney(read.decimal, locale, money) });
    }
  }
  return errors;
}

export function useBusinessMoney(): ComputedRef<Money | undefined> {
  return useBusinessMoneyRead().money;
}

/** The read of the business's money as a window that waits for it needs it (hub#938): the money (unknown until the
 *  business answers), the read's `error` (an error frame of `base.business.get`, such as `base.hub_busy`; the money is
 *  kept if it was known) and `retry`, which reopens the tab's stream so the server answers again. `BusinessMoneyError`
 *  says it in the window; the money alone is `useBusinessMoney`. */
export interface BusinessMoneyRead {
  money: ComputedRef<Money | undefined>;
  error: Readonly<Ref<ApiError | null>>;
  retry: () => void;
}

export function useBusinessMoneyRead(): BusinessMoneyRead {
  const { data, error, refresh } = useLive('base.business.get', {});
  const money = computed(() => (data.value ? { currency: data.value.currency, decimals: data.value.currency_decimals } : undefined));
  return { money, error, retry: refresh };
}
