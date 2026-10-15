// How the kitchen paints numbers and moments: the card's clock and its border, quantities, money and the
// History's moments in the business's zone. Pure functions: the pages pass the language and the zone.
import type { SettingsOut } from '../operations';

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

/** Cents as euros, in the reader's language. */
export function formatMoney(cents: number, locale: string): string {
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'EUR' }).format(cents / 100);
}

/** A moment, short date and time, in the business's zone; empty for none. */
export function formatDateTime(iso: string | null | undefined, locale: string, timeZone: string): string {
  if (!iso) return '';
  return new Intl.DateTimeFormat(locale, { dateStyle: 'short', timeStyle: 'short', timeZone }).format(new Date(iso));
}
