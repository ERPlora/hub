// The business clock, for the Settings screen (hub#1154).
//
// The AUTHORITY on the hub timezone is the runtime: `crates/runtime/src/settings.rs` deduces it
// (`zone_for_country`, which also breaks the ES-CN / PT-20 / PT-30 tie) and validates whatever is
// stored (`validate_timezone`, against the tzdb — no abbreviations, no offsets). Nothing here
// re-decides any of that: this module only answers the two questions a SELECTOR has, which the
// runtime has no opinion about — which zones to OFFER, and what time it is in each one right now.
//
// That last one is the point. A shop owner cannot audit `Atlantic/Canary` as a string, but can
// audit a clock: the row that reads 23:30 next to a wall clock that reads 23:30 is right, and the
// one that reads 00:30 is not. It is the cheapest correct answer to "which of these two is mine".

/**
 * Zones a hub can legitimately sit in, per fiscal country, most populated first.
 *
 * Deliberately short: the country selector offers ES and PT, so those are the countries a hub can
 * actually be in, and Spain (2 zones) and Portugal (3) are exactly the countries where the
 * deduction from the country alone cannot be right for everyone. This is a list of OPTIONS, not a
 * second source of truth — the runtime still deduces the default and still rejects a bad value.
 * When the country selector grows, this table grows with it in the same change.
 */
export const COUNTRY_ZONES: Record<string, readonly string[]> = {
  ES: ['Europe/Madrid', 'Atlantic/Canary'],
  PT: ['Europe/Lisbon', 'Atlantic/Azores', 'Atlantic/Madeira'],
};

/** What a zone's clock reads at a given instant. `date` is ISO so it never depends on a locale. */
export interface ZoneClock {
  /** Calendar day IN THAT ZONE, `YYYY-MM-DD`. Not the UTC day: they differ every single night. */
  date: string;
  /** Wall clock in that zone, `HH:mm`, 24h. */
  time: string;
  /** Offset in force AT THAT INSTANT, `UTC±HH:MM` — daylight saving included, never a constant. */
  offset: string;
}

/**
 * An IANA name is `Area/Location` (or the bare `UTC`). Checked by shape BEFORE handing it to
 * `Intl`, because engines disagree about the junk they tolerate: some accept `+02:00` as a zone.
 * An offset is precisely what must NOT be accepted — it carries no daylight-saving rule, so it is
 * right for half the year and an hour wrong for the other half. The runtime rejects it too.
 */
function isIanaName(zone: string): boolean {
  if (zone === 'UTC') return true;
  return /^[A-Za-z][A-Za-z0-9_+-]*(?:\/[A-Za-z0-9_+-]+)+$/.test(zone);
}

/** `GMT+01:00` → `UTC+01:00`; the bare `GMT` that engines emit at zero offset → `UTC+00:00`. */
function normalizeOffset(timeZoneName: string): string {
  const signed = timeZoneName.replace(/^(GMT|UTC)/, '');
  return `UTC${signed || '+00:00'}`;
}

/**
 * What `zone`'s clock reads at `at` — or `null` if this browser cannot read that zone.
 *
 * `null` rather than a throw, and rather than falling back to the machine zone: Settings must
 * survive a value written straight through `PUT /api/settings` on a newer tzdb than the browser
 * has, and a silent fallback would print a confident time from the WRONG clock, which is worse
 * than printing none. The caller shows the plain zone name instead.
 */
export function zoneClock(zone: string, at: Date): ZoneClock | null {
  const name = typeof zone === 'string' ? zone.trim() : '';
  if (!name || !isIanaName(name)) return null;
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: name,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZoneName: 'longOffset',
    }).formatToParts(at);
    const part = (type: Intl.DateTimeFormatPartTypes): string =>
      parts.find((p) => p.type === type)?.value ?? '';
    const [year, month, day, minute] = [
      part('year'),
      part('month'),
      part('day'),
      part('minute'),
    ];
    // `hour12: false` still yields "24" for midnight in some engines; the ISO day is already the
    // NEXT one there, so the hour is the only thing to bring back into range.
    const hour = part('hour') === '24' ? '00' : part('hour');
    if (!year || !month || !day || !hour || !minute) return null;
    return {
      date: `${year}-${month}-${day}`,
      time: `${hour}:${minute}`,
      offset: normalizeOffset(part('timeZoneName')),
    };
  } catch {
    // RangeError: a well-shaped name this engine's tzdb does not carry. Same verdict as above.
    return null;
  }
}

/**
 * The zones the selector offers for `countryCode`, with `current` appended when the hub already
 * holds a zone the country's list does not carry.
 *
 * That last part is not a nicety: `timezone` was writable through `PUT /api/settings` long before
 * this screen existed, so a hub can legitimately be on a zone from outside the table. Dropping it
 * from the options would leave the row rendering a value it cannot select — and the first save of
 * anything else on the screen would look like it silently changed the shop's clock.
 */
export function zoneOptions(countryCode: string, current?: string | null): string[] {
  const country = (countryCode ?? '').trim().toUpperCase();
  const options = [...(COUNTRY_ZONES[country] ?? [])];
  const held = typeof current === 'string' ? current.trim() : '';
  if (held && !options.includes(held)) options.push(held);
  return options;
}
