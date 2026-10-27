// How the kitchen paints numbers and moments: the card's clock and its border, quantities, money and the
// History's moments in the business's zone. Pure functions: the pages pass the language, the zone and the money.
// The money is the business's (`useBusinessMoney`, the platform's: its country's currency and the decimals the server
// counts it in); until it is known an amount is a figure without a symbol, never the euro by default. Its decimals come
// from the server, never from the browser's Intl (which gives none to the forint).
import type { Money } from '../../../../base/frontend/lib/home';
import type { SettingsOut } from '../operations';

export type { Money };
export { useBusinessMoney } from '../../../../base/frontend/lib/money';

/** The decimals of an amount while the business's currency is unknown. */
const NO_MONEY_DECIMALS = 2;

export type Semaphore = 'ok' | 'warning' | 'critical' | 'off';

/** m:ss, or h:mm:ss past the hour. The clock never stops and never goes below zero. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}

/** The border of a card: green, amber from the amber minutes, red from the red ones; off without colours. */
export function semaphore(elapsedMs: number, settings: Pick<SettingsOut, 'color_coding' | 'warning_minutes' | 'critical_minutes'>): Semaphore {
  if (!settings.color_coding) return 'off';
  const minutes = elapsedMs / 60_000;
  if (minutes >= settings.critical_minutes) return 'critical';
  if (minutes >= settings.warning_minutes) return 'warning';
  return 'ok';
}

/** A quantity as a cook reads it: `2`, `0,5` (the server sends `"2.000"`). */
export function formatQuantity(quantity: string | number, locale: string): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 3 }).format(Number(quantity));
}

/** Minor units as `money` in the reader's language («24,50 zł», «€24.50», «¥2,450»); «24,50» while it is unknown. */
export function formatMoney(cents: number, locale: string, money?: Money): string {
  const decimals = money?.decimals ?? NO_MONEY_DECIMALS;
  const digits = { minimumFractionDigits: decimals, maximumFractionDigits: decimals };
  const options: Intl.NumberFormatOptions = money ? { style: 'currency', currency: money.currency, currencyDisplay: 'narrowSymbol', ...digits } : digits;
  return new Intl.NumberFormat(locale, options).format(cents / 10 ** decimals);
}

/** A moment, short date and time, in the business's zone; empty for none. */
export function formatDateTime(iso: string | null | undefined, locale: string, timeZone: string): string {
  if (!iso) return '';
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short', timeZone }).format(new Date(iso));
}
