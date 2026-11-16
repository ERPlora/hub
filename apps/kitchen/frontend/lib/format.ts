// How the kitchen paints numbers and moments: the card's clock and its border, quantities, money and the
// History's moments in the business's zone. Pure functions: the pages pass the language, the zone and the money.
// The money is the business's (`useBusinessMoney`, the platform's: its country's currency and the decimals the server
// counts it in), written with the platform's `formatMoney`: its thousands grouped from four digits on, as every screen
// writes them; until it is known an amount is a dash, never the euro by default nor guessed decimals. Its decimals come
// from the server, never from the browser's Intl (which gives none to the forint). A quantity is written with the
// platform's `formatQuantity` («2.000» → «2», «1500.000» → «1.500»), as the till that sent it writes it.
import type { Money } from '../../../../base/frontend/lib/home';
import type { SettingsOut } from '../operations';

export type { Money };
export { formatMoney, useBusinessMoney } from '../../../../base/frontend/lib/money';
export { formatQuantity } from '@erplora/ui/components';

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

/** A moment, short date and time, in the business's zone; empty for none. */
export function formatDateTime(iso: string | null | undefined, locale: string, timeZone: string): string {
  if (!iso) return '';
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short', timeZone }).format(new Date(iso));
}
