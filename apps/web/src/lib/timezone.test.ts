// The business clock, as the Settings screen has to show it (hub#1154).
//
// 🔴 Why these assertions look paranoid: THIS MACHINE RUNS IN `Europe/Madrid`. A test that asked
// for the Madrid time of an instant would stay green even if `zoneClock` threw its `zone` argument
// away and formatted with the system zone — which is precisely the bug this screen must not ship,
// because the whole point of the setting is the shop that is NOT in Madrid. So every case below
// either uses a zone the machine is not in, or crosses a calendar day, or both, and one case pins
// three zones against each other so that ignoring `zone` cannot pass under ANY machine zone.
import { describe, expect, it } from 'vitest';

import { COUNTRY_ZONES, zoneClock, zoneOptions } from './timezone';

// 23:30 UTC in winter: already tomorrow in Madrid (UTC+1), still today in the Canaries (UTC+0).
const WINTER_NIGHT = new Date('2026-01-15T23:30:00Z');
// 23:30 UTC in summer: Madrid is UTC+2 and the Canaries UTC+1 — the offsets MOVE with the tzdb.
const SUMMER_NIGHT = new Date('2026-07-15T23:30:00Z');

describe('zoneClock — the same instant, read by each zone clock', () => {
  it('splits the CALENDAR DAY between the two zones of Spain (this is the whole issue)', () => {
    // One country, one instant, two different dates. A shop in Las Palmas closing "today" is not
    // closing the same day as a shop in Madrid, and the cron of a flow has to agree with the till.
    expect(zoneClock('Europe/Madrid', WINTER_NIGHT)).toEqual({
      date: '2026-01-16',
      time: '00:30',
      offset: 'UTC+01:00',
    });
    expect(zoneClock('Atlantic/Canary', WINTER_NIGHT)).toEqual({
      date: '2026-01-15',
      time: '23:30',
      offset: 'UTC+00:00',
    });
  });

  it('follows the DAYLIGHT SAVING rules instead of a frozen offset', () => {
    // Same two zones, six months later: both offsets shifted by an hour. A hardcoded `+01:00`
    // would have passed the winter case above and would be an hour wrong all summer.
    expect(zoneClock('Europe/Madrid', SUMMER_NIGHT)).toEqual({
      date: '2026-07-16',
      time: '01:30',
      offset: 'UTC+02:00',
    });
    expect(zoneClock('Atlantic/Canary', SUMMER_NIGHT)).toEqual({
      date: '2026-07-16',
      time: '00:30',
      offset: 'UTC+01:00',
    });
  });

  it('reads a zone FAR from the machine, on both sides of UTC', () => {
    // +14 and -11: the widest pair the tzdb has. Whatever the machine zone is, it is not both.
    expect(zoneClock('Pacific/Kiritimati', WINTER_NIGHT)).toEqual({
      date: '2026-01-16',
      time: '13:30',
      offset: 'UTC+14:00',
    });
    expect(zoneClock('Pacific/Midway', WINTER_NIGHT)).toEqual({
      date: '2026-01-15',
      time: '12:30',
      offset: 'UTC-11:00',
    });
  });

  it('cannot pass while IGNORING its zone argument, under any machine zone', () => {
    // The mutant this kills: `zoneClock = (_zone, at) => format(at)`. It would answer the same
    // thing three times. The assertion is on the DIFFERENCE, so it holds wherever this runs.
    const seen = ['Europe/Madrid', 'Atlantic/Canary', 'Pacific/Kiritimati'].map(
      (z) => JSON.stringify(zoneClock(z, WINTER_NIGHT)),
    );
    expect(new Set(seen).size).toBe(3);
  });

  it('degrades to null on a zone the browser does not know, it does not throw', () => {
    // A zone set by hand through `PUT /api/settings` on an older tzdb must not take the screen
    // down: the row falls back to the plain name and the rest of Settings keeps working.
    expect(zoneClock('Not/AZone', WINTER_NIGHT)).toBeNull();
    expect(zoneClock('CEST', WINTER_NIGHT)).toBeNull();
    expect(zoneClock('+02:00', WINTER_NIGHT)).toBeNull();
  });
});

describe('zoneOptions — what the selector offers', () => {
  it('offers the zones of the hub country, most populated first', () => {
    // Mirrors the runtime tie-breaker (`crates/runtime/src/settings.rs::zone_for_country`), which
    // stays the authority: it deduces and it validates. This list only decides what is OFFERED.
    expect(zoneOptions('ES', null)).toEqual(['Europe/Madrid', 'Atlantic/Canary']);
    expect(zoneOptions('PT', null)).toEqual([
      'Europe/Lisbon',
      'Atlantic/Azores',
      'Atlantic/Madeira',
    ]);
  });

  it('never drops the zone the hub already has, even if the country does not list it', () => {
    // `timezone` was writable by API long before this screen existed. Opening Settings must not
    // silently offer to overwrite a value it simply failed to render.
    expect(zoneOptions('ES', 'America/New_York')).toEqual([
      'Europe/Madrid',
      'Atlantic/Canary',
      'America/New_York',
    ]);
    expect(zoneOptions('ES', 'Atlantic/Canary')).toEqual(['Europe/Madrid', 'Atlantic/Canary']);
  });

  it('is empty for a country with no curated list, so the row shows only «automatic»', () => {
    expect(zoneOptions('US', null)).toEqual([]);
    expect(zoneOptions('US', 'America/New_York')).toEqual(['America/New_York']);
    expect(zoneOptions('', null)).toEqual([]);
  });

  it('takes the country case-insensitively, like the rest of the settings store', () => {
    expect(zoneOptions('es', null)).toEqual(['Europe/Madrid', 'Atlantic/Canary']);
  });

  it('only lists zones the browser can actually read a clock from', () => {
    // Guards the table itself: a typo in COUNTRY_ZONES would ship a dead option that renders
    // without a time and saves a value the runtime would then reject with a 422.
    for (const zones of Object.values(COUNTRY_ZONES)) {
      for (const zone of zones) {
        expect(zoneClock(zone, WINTER_NIGHT), zone).not.toBeNull();
      }
    }
  });
});
