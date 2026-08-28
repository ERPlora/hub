// TDD (hub#1212): the shell paints dates in the BUSINESS clock, not in the browser's.
//
// The runtime already resolves the hub timezone (`settings::timezone_of`, hub#731) and binds it as
// `:timezone` in every query, command and `cron` trigger. The shell then threw that away: every
// `toLocale*` call formatted in whatever zone the laptop happens to sit in, so the same hub read
// from Madrid and from Las Palmas showed two different times for the same instant.
//
// Two guards here, and they are different in kind:
//   1. The BEHAVIOUR test — the same instant under two hub zones must render two different wall
//      clocks, with the values of THOSE zones. It is written with absolute expectations so it
//      proves the same thing on a laptop in Madrid and on a runner in UTC.
//   2. The PATTERN guard — no source file outside this helper may call `toLocale{String,Date,Time}`.
//      Without it the bug comes back in the next component somebody writes, which is exactly how it
//      reached 16 call sites.
import { afterEach, describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

import { publishHubTimezone } from './hub-settings';
import { formatDate, formatDateTime, formatLocale, formatTime, hubDayKey } from './format-datetime';

/** Clears the published zone so each case states its own premise. */
function unpublishHubTimezone(): void {
  delete (globalThis as { __erploraTimezone?: string }).__erploraTimezone;
}

afterEach(unpublishHubTimezone);

// 2026-08-27T23:30:00Z is the instant that makes the bug visible: it is still the 27th in the
// Canaries (UTC+1 in summer) and already the 28th in Madrid (UTC+2). A hub in Las Palmas read from
// Madrid used to show tomorrow's date for last night's sale.
const INSTANT = '2026-08-27T23:30:00Z';

describe('format-datetime (hub#1212)', () => {
  it('formats_in_the_hub_timezone_not_in_the_browser_one_hub1212', () => {
    publishHubTimezone('Atlantic/Canary');

    expect(
      formatTime(INSTANT, { locale: 'en-GB', hour: '2-digit', minute: '2-digit', hour12: false }),
    ).toBe('00:30');
    expect(
      formatDate(INSTANT, { locale: 'en-GB', day: '2-digit', month: '2-digit', year: 'numeric' }),
    ).toBe('28/08/2026');

    // Control: the SAME instant, the SAME machine, a different business clock. If the browser zone
    // were still deciding, both blocks would print the same string and this would pass by accident.
    publishHubTimezone('Europe/Madrid');

    expect(
      formatTime(INSTANT, { locale: 'en-GB', hour: '2-digit', minute: '2-digit', hour12: false }),
    ).toBe('01:30');
    expect(
      formatDate(INSTANT, { locale: 'en-GB', day: '2-digit', month: '2-digit', year: 'numeric' }),
    ).toBe('28/08/2026');

    // And a zone far from both, so a machine that happens to sit in Madrid cannot make this green.
    publishHubTimezone('Pacific/Honolulu');

    expect(
      formatTime(INSTANT, { locale: 'en-GB', hour: '2-digit', minute: '2-digit', hour12: false }),
    ).toBe('13:30');
    expect(
      formatDate(INSTANT, { locale: 'en-GB', day: '2-digit', month: '2-digit', year: 'numeric' }),
    ).toBe('27/08/2026');
  });

  it('formatDateTime carries date AND time, both in the business clock', () => {
    publishHubTimezone('Pacific/Honolulu');

    expect(
      formatDateTime(INSTANT, {
        locale: 'en-GB',
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      }),
    ).toBe('27/08/2026, 13:30');
  });

  it('hubDayKey answers the calendar day of the BUSINESS, not of Greenwich', () => {
    // Grouping "what changed yesterday" is a question about the owner's day. At 23:30Z it is still
    // the 27th in the Canaries and already the 28th in Madrid.
    publishHubTimezone('Atlantic/Canary');
    expect(hubDayKey(INSTANT)).toBe('2026-08-28');

    publishHubTimezone('Pacific/Honolulu');
    expect(hubDayKey(INSTANT)).toBe('2026-08-27');
  });

  it('accepts a Date, an ISO string or an epoch, and returns null for anything unreadable', () => {
    publishHubTimezone('Atlantic/Canary');
    const opts = { locale: 'en-GB', hour: '2-digit', minute: '2-digit', hour12: false } as const;

    expect(formatTime(new Date(INSTANT), opts)).toBe('00:30');
    expect(formatTime(Date.parse(INSTANT), opts)).toBe('00:30');
    // `null` and not a fallback string: every call site already knows what to paint instead (the
    // raw value it was given). A helper that invents "—" would take that decision away from them.
    expect(formatTime('no-es-una-fecha', opts)).toBeNull();
    expect(formatDate('', opts)).toBeNull();
    expect(formatDateTime(null, opts)).toBeNull();
    expect(hubDayKey('no-es-una-fecha')).toBeNull();
  });

  it('before the boot seeds the zone it falls back to the BROWSER zone, never to UTC', () => {
    // Declared edge case of the issue. `hubTimezone()` degrades to 'UTC', which in Spain is an hour
    // wrong ten months a year — a confident lie. Until `bootHubContext` publishes the real zone the
    // honest render is the one the browser was already producing before this change: no regression,
    // and no new wrong hour invented on the boot screens.
    unpublishHubTimezone();
    const machineZone = new Intl.DateTimeFormat().resolvedOptions().timeZone;
    const expected = new Date(INSTANT).toLocaleTimeString('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: machineZone,
    });

    expect(
      formatTime(INSTANT, { locale: 'en-GB', hour: '2-digit', minute: '2-digit', hour12: false }),
    ).toBe(expected);
  });

  it('the app locale decides the language, never the browser (#273, centralised here)', () => {
    // #273 was «the date mixes Spanish and English»: `toLocaleDateString(undefined, …)` falls back
    // to the BROWSER's locale. Each screen then hardcoded `locale.value === 'en' ? 'en-GB' : 'es-ES'`
    // fifteen times; that ternary now lives here, so this is the half of #273 that used to be
    // asserted by grepping DashboardPage.
    expect(formatLocale('en')).toBe('en-GB');
    expect(formatLocale('es')).toBe('es-ES');
    // Bare `en` would be US order (8/27/2026) — wrong for a product sold in ES/PT.
    expect(
      formatDate(INSTANT, { locale: 'en', day: '2-digit', month: '2-digit', year: 'numeric' }),
    ).toBe(
      formatDate(INSTANT, { locale: 'en-GB', day: '2-digit', month: '2-digit', year: 'numeric' }),
    );
    // A tag that already carries a region is honoured as given.
    expect(formatLocale('pt-PT')).toBe('pt-PT');
  });

  it('a zone this engine cannot read degrades instead of throwing', () => {
    // `timezone` was writable through `PUT /api/settings` long before the selector existed, so a
    // hub can hold a name from a newer tzdb than this browser carries. A RangeError there would
    // blank the whole screen; the wrong-but-rendered hour is recoverable, a white page is not.
    publishHubTimezone('Mars/Olympus_Mons');

    expect(
      formatTime(INSTANT, { locale: 'en-GB', hour: '2-digit', minute: '2-digit', hour12: false }),
    ).toMatch(/^\d{2}:\d{2}$/);
  });
});

// ── Pattern guard ────────────────────────────────────────────────────────────────────────────────

const SRC = fileURLToPath(new URL('..', import.meta.url));
const HELPER = 'lib/format-datetime.ts';
const SCANNED = /\.(ts|tsx|mts|js|mjs|vue)$/;
const SKIPPED = /\.(test|spec)\.(ts|tsx|mts|js|mjs)$/;
/** `toLocaleUpperCase`/`toLocaleLowerCase` are fine — only the three date/time ones are the bug. */
const OFFENDER = /\.toLocale(?:String|DateString|TimeString)\s*\(/;

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const item of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, item.name);
    if (item.isDirectory()) {
      if (item.name === 'node_modules') continue;
      sourceFiles(full, found);
    } else if (SCANNED.test(item.name) && !SKIPPED.test(item.name)) {
      found.push(full);
    }
  }
  return found;
}

describe('nobody formats a date outside the helper (hub#1212)', () => {
  it('no_tolocale_datetime_call_outside_format_datetime_hub1212', () => {
    const offenders: string[] = [];
    for (const file of sourceFiles(SRC)) {
      const rel = relative(SRC, file).split(/[\\/]/).join('/');
      if (rel === HELPER) continue;
      readFileSync(file, 'utf8')
        .split('\n')
        .forEach((line, i) => {
          if (OFFENDER.test(line)) offenders.push(`${rel}:${i + 1}`);
        });
    }

    expect(
      offenders,
      'toLocaleString/toLocaleDateString/toLocaleTimeString format in the BROWSER zone (hub#1212). ' +
        'Use formatDateTime/formatDate/formatTime from lib/format-datetime, which pass the hub ' +
        'timezone. For numbers use lib/money or Intl.NumberFormat.',
    ).toEqual([]);
  });

  it('the guard catches the positive: a planted call is reported with its file and line', () => {
    // A guard that has never seen a red is a guard nobody has tested. This plants the exact shape
    // it hunts for and proves the scanner names it — without touching the tree.
    const planted = ['const a = 1;', "const s = d.toLocaleDateString('es-ES');"];
    const hits = planted
      .map((line, i) => (OFFENDER.test(line) ? `planted.vue:${i + 1}` : ''))
      .filter(Boolean);

    expect(hits).toEqual(['planted.vue:2']);
    expect(OFFENDER.test("name.toLocaleUpperCase('es-ES')")).toBe(false);
  });
});
