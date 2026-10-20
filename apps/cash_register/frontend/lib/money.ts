// Money of the drawer screens. The server keeps money in whole cents; a person reads it in the page's
// language and types it as she reads it. Until `@erplora/ui/components/format` has a money formatter
// (UI-REQUESTS.md), this is the one place the app turns cents into text (`Intl.NumberFormat`) and what is
// typed into cents. Every money field goes through `readMoney`: empty, an amount, or why it is not one.

const CURRENCY = 'EUR';
const FALLBACK_LOCALE = 'en';

const cache = new Map<string, Intl.NumberFormat>();

function formatter(locale: string, key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const id = `${locale}|${key}`;
  let found = cache.get(id);
  if (!found) {
    try {
      found = new Intl.NumberFormat(locale, options);
    } catch (error) {
      if (!(error instanceof RangeError) || locale === FALLBACK_LOCALE) throw error;
      found = formatter(FALLBACK_LOCALE, key, options);
    }
    cache.set(id, found);
  }
  return found;
}

const missing = (value: unknown): boolean => value === null || value === undefined || Number.isNaN(Number(value));

/** The decimals of `currency` as CLDR knows them (2 in EUR, 0 in JPY, 3 in KWD): its minor unit. */
export function currencyDecimals(currency: string = CURRENCY): number {
  return formatter(FALLBACK_LOCALE, `money-${currency}`, { style: 'currency', currency }).resolvedOptions().maximumFractionDigits ?? 2;
}

/** Minor units as money of `currency` in `locale` («150,50 €», «€150.50», «¥5,003»); nothing is «—». */
export function formatMoney(cents: number | null | undefined, locale: string, currency = CURRENCY): string {
  if (missing(cents)) return '—';
  return formatter(locale, `money-${currency}`, { style: 'currency', currency }).format((cents as number) / 10 ** currencyDecimals(currency));
}

/** A note or coin of the count as money of `currency` («500 €», «0,50 €»): a whole face value without decimals
 *  (the old count, Square and Lightspeed), a coin of cents with the currency's own. */
export function formatFace(face: string, locale: string, currency = CURRENCY): string {
  const value = Number(face);
  const whole = Number.isInteger(value);
  const decimals = whole ? 0 : currencyDecimals(currency);
  return formatter(locale, `face-${currency}-${decimals}`, {
    style: 'currency',
    currency,
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** A difference with its sign: «+5,10 €» over, «-4,90 €» short, zero without sign. */
export function formatSignedMoney(cents: number | null | undefined, locale: string, currency = CURRENCY): string {
  if (missing(cents)) return '—';
  const money = formatMoney(cents, locale, currency);
  return (cents as number) > 0 ? `+${money}` : money;
}

/** Minor units as a money field holds them: ungrouped, with the reader's decimal sign («1250,50»). */
export function moneyFieldText(cents: number, locale: string, decimals = 2): string {
  const sign = formatter(locale, 'decimal-sign', { minimumFractionDigits: 1 }).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
  return (cents / 10 ** decimals).toFixed(decimals).replace('.', sign);
}

/** The text with Intl's no-break spaces as plain ones (what a test or a search compares). */
export function plain(text: string): string {
  return text.replace(/[\u00a0\u202f]/g, ' ');
}

export type MoneyRead =
  | { ok: true; cents: number | null }
  | { ok: false; reason: 'notAnAmount' | 'negative' }
  | { ok: false; reason: 'ambiguous'; typed: string; grouped: number; decimal: number };

const WHOLE = /^\d+$/;
const GROUPED = /^\d{1,3}(?:([.,])\d{3}){2,}$/;
const GROUPED_DECIMAL = /^(\d{1,3}(?:([.,])\d{3})+)([.,])(\d+)$/;
const ONE_GROUP = /^(\d{1,3})[.,](\d{3})$/;
const DECIMAL = /^(\d+)[.,](\d+)$/;

/** `whole` major units and `fraction` digits as minor units, the fraction rounded half up to `decimals`. */
function minor(whole: string, fraction: string, decimals: number): number {
  const kept = fraction.slice(0, decimals).padEnd(decimals, '0');
  const up = fraction.length > decimals && Number(fraction[decimals]) >= 5 ? 1 : 0;
  return Number(whole) * 10 ** decimals + Number(kept || '0') + up;
}

/** What a person typed in a money field, read once for every field of the app, in minor units of a
 *  currency of `decimals` (2 in EUR). Empty is no amount; «1.250» in euros reads two ways and says so. */
export function readMoney(raw: string | number | null | undefined, decimals = 2): MoneyRead {
  const typed = String(raw ?? '').trim();
  const text = typed.replace(/[\s\u00a0\u202f]/g, '').replace(/€$/, '');
  if (text === '') return { ok: true, cents: null };
  if (/^[-\u2212]/.test(text)) return { ok: false, reason: 'negative' };
  if (WHOLE.test(text)) return { ok: true, cents: minor(text, '', decimals) };
  if (GROUPED.test(text) && new Set(text.replace(/\d/g, '')).size === 1) {
    return { ok: true, cents: minor(text.replace(/[.,]/g, ''), '', decimals) };
  }
  let match = GROUPED_DECIMAL.exec(text);
  if (match && match[2] !== match[3] && decimals > 0 && match[4].length <= decimals) {
    return { ok: true, cents: minor(match[1].replace(/[.,]/g, ''), match[4], decimals) };
  }
  match = ONE_GROUP.exec(text);
  if (match) {
    // No decimals: a separator only groups. A leading zero never groups: «0,515» is a fraction.
    if (decimals === 0) return { ok: true, cents: minor(`${match[1]}${match[2]}`, '', 0) };
    if (Number(match[1]) === 0 && decimals >= 3) return { ok: true, cents: minor(match[1], match[2], decimals) };
    return {
      ok: false,
      reason: 'ambiguous',
      typed,
      grouped: minor(`${match[1]}${match[2]}`, '', decimals),
      decimal: minor(match[1], match[2], decimals),
    };
  }
  match = DECIMAL.exec(text);
  if (match && decimals > 0 && match[2].length <= decimals) return { ok: true, cents: minor(match[1], match[2], decimals) };
  return { ok: false, reason: 'notAnAmount' };
}

/** Why a money field cannot be sent, in the app's words; `null` when it is an amount or empty. */
export function moneyRefusal(
  read: MoneyRead,
  t: (key: string, named?: Record<string, unknown>) => string,
  locale: string,
  currency = CURRENCY,
): string | null {
  if (read.ok) return null;
  if (read.reason === 'ambiguous') {
    return t('cash_register.money.ambiguous', {
      typed: read.typed,
      grouped: formatMoney(read.grouped, locale, currency),
      decimal: formatMoney(read.decimal, locale, currency),
    });
  }
  return t(`cash_register.money.${read.reason}`);
}
