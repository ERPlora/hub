// Date/time formatting for the shell (hub#1212). Mirror of `lib/money.ts`: ONE entry point, one
// source of truth, so no screen has to remember the rule.
//
// The rule is the business clock. The runtime already works in it — `settings::timezone_of`
// (hub#731) resolves the hub zone and binds it as `:timezone` in every query, command and `cron`
// trigger, so "tomorrow at 09:00" is the shop's 09:00. Storage is `TIMESTAMPTZ`, i.e. UTC instants.
// The chain was right end to end until the shell painted it: `toLocaleString()` and friends format
// in whatever zone the BROWSER sits in, so a hub in `Atlantic/Canary` opened from Madrid showed
// every timestamp an hour ahead of what the runtime computed, and the same hub read from two
// places showed two different times for one instant. Invisible to anyone developing in the same
// zone as the business, which is why it reached 16 call sites.
//
// Formatting by hand in each component is what let those 16 drift, so a pattern guard
// (`format-datetime.test.ts`) fails the suite on any `toLocale{String,Date,Time}String` outside
// this file. For numbers use `lib/money.ts` or `Intl.NumberFormat`.
import { getLocale } from '../i18n';
import { publishedHubTimezone } from './hub-settings';
import { zoneClock } from './timezone';

/** Anything a screen can hold for an instant: the runtime sends ISO-8601, tests build `Date`s. */
export type DateLike = Date | string | number | null | undefined;

/**
 * `Intl.DateTimeFormatOptions` minus `timeZone`, plus the locale.
 *
 * `timeZone` is deliberately NOT accepted: an override is exactly the hole this helper exists to
 * close. A screen that genuinely needs another zone (the Settings clock preview) has `zoneClock`
 * in `lib/timezone.ts`, which asks for the zone by name and says so.
 */
export interface FormatDateTimeOptions extends Omit<Intl.DateTimeFormatOptions, 'timeZone'> {
  /** BCP-47 tag. Defaults to the active shell locale, mapped by `formatLocale`. */
  locale?: string;
}

/**
 * The same defaults `toLocaleString()` / `toLocaleDateString()` / `toLocaleTimeString()` apply when
 * called with no options.
 *
 * They have to be spelled out: `new Intl.DateTimeFormat(loc, { timeZone })` — options object
 * present but carrying no component — renders the DATE ALONE, silently dropping the time. Copying
 * the native defaults keeps every migrated call site rendering what it rendered before, in the
 * right zone, instead of shipping a visual change alongside a correctness fix.
 */
const DATE_DEFAULTS: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'numeric', day: 'numeric' };
const TIME_DEFAULTS: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: 'numeric', second: 'numeric' };

/**
 * BCP-47 tag for a shell locale.
 *
 * The shell speaks `es` / `en` (i18n); the formatter needs a region, because bare `en` is US order
 * (`8/27/2026`) and this product is sold in Spain and Portugal. `en-GB` / `es-ES` is what the
 * screens already hardcoded one by one — centralised here instead of repeated fifteen times.
 * A tag that already carries a region is passed through untouched.
 */
export function formatLocale(locale?: string): string {
  const raw = (locale ?? getLocale() ?? '').trim();
  if (raw.includes('-')) return raw;
  return raw.toLowerCase() === 'en' ? 'en-GB' : 'es-ES';
}

/** The zone this browser sits in, or `UTC` if it will not say. Only ever a fallback. */
function browserTimeZone(): string {
  try {
    return new Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/**
 * The clock every screen paints in: the business zone the runtime resolved.
 *
 * **Declared edge case (hub#1212).** Until `bootHubContext` publishes it, there is no business
 * zone, and `hubTimezone()`'s own degradation — `UTC` — would be an hour wrong in Spain for ten
 * months a year: a confident lie on the boot and login screens. The honest fallback is the browser
 * zone, which is what those screens already showed before this change: no regression, and no new
 * wrong hour invented. Once the boot lands, every subsequent render is the business clock.
 */
function businessTimeZone(): string {
  return publishedHubTimezone() ?? browserTimeZone();
}

/** `null` for anything that is not a readable instant — including `''`, which screens do hold. */
function toDate(value: DateLike): Date | null {
  if (value == null || value === '') return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Split the locale out of the options and decide whether the caller stated its own components. */
function partsOf(opts: FormatDateTimeOptions | undefined, defaults: Intl.DateTimeFormatOptions) {
  const { locale, ...rest } = opts ?? {};
  return {
    locale: formatLocale(locale),
    components: Object.keys(rest).length > 0 ? (rest as Intl.DateTimeFormatOptions) : defaults,
  };
}

/**
 * Formats `date` in `zone`, falling back to the browser zone if this engine cannot read the name.
 *
 * `timezone` has been writable through `PUT /api/settings` since long before the Settings selector
 * existed, so a hub can legitimately hold a zone from a newer tzdb than the browser carries.
 * `Intl` throws `RangeError` on those, and an uncaught throw inside a computed blanks the screen —
 * a wrong-but-rendered hour is recoverable, a white page is not.
 */
function render(date: Date, zone: string, locale: string, components: Intl.DateTimeFormatOptions): string {
  try {
    return new Intl.DateTimeFormat(locale, { ...components, timeZone: zone }).format(date);
  } catch {
    return new Intl.DateTimeFormat(locale, components).format(date);
  }
}

/** Date **and** time in the business clock. Replaces `toLocaleString()`. `null` if unreadable. */
export function formatDateTime(value: DateLike, opts?: FormatDateTimeOptions): string | null {
  const date = toDate(value);
  if (!date) return null;
  const { locale, components } = partsOf(opts, { ...DATE_DEFAULTS, ...TIME_DEFAULTS });
  return render(date, businessTimeZone(), locale, components);
}

/** Calendar date in the business clock. Replaces `toLocaleDateString()`. `null` if unreadable. */
export function formatDate(value: DateLike, opts?: FormatDateTimeOptions): string | null {
  const date = toDate(value);
  if (!date) return null;
  const { locale, components } = partsOf(opts, DATE_DEFAULTS);
  return render(date, businessTimeZone(), locale, components);
}

/** Wall clock in the business clock. Replaces `toLocaleTimeString()`. `null` if unreadable. */
export function formatTime(value: DateLike, opts?: FormatDateTimeOptions): string | null {
  const date = toDate(value);
  if (!date) return null;
  const { locale, components } = partsOf(opts, TIME_DEFAULTS);
  return render(date, businessTimeZone(), locale, components);
}

/**
 * `YYYY-MM-DD` of the BUSINESS calendar day — the key you group by when the question is "what
 * changed yesterday?". Locale-free on purpose: it is an identifier, not a label.
 *
 * The owner's day is not the UTC day (they differ every single night) and not the browser's day
 * either, which is the same bug as above wearing different clothes: a hub in Las Palmas read from
 * Madrid filed a 23:30 change under tomorrow.
 */
export function hubDayKey(value: DateLike): string | null {
  const date = toDate(value);
  if (!date) return null;
  return zoneClock(businessTimeZone(), date)?.date ?? zoneClock(browserTimeZone(), date)?.date ?? null;
}
