import * as components from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { EUR, widget } from '../__tests__/home-fixtures';
import { widgetView } from './home-panels';

/** The zones a business day is read in, west to east: the day is the same in all of them. */
const ZONES = ['America/Los_Angeles', 'Europe/Madrid', 'Pacific/Kiritimati'];

/**
 * A fresh copy of this module per zone, as a page opened there: its day formats are made on first use, in the zone set
 * then, so no formatter of another zone is reused. Only this module is the page's: the UI library already loaded is
 * handed to each copy, not evaluated again. Loaded with the file, out of any test's clock: each import waits for
 * Vitest's main process, and on a busy run (the machine at load ~24) the three took 5.3 s inside the test while the
 * file's other tests ran in 4 ms.
 */
async function copiesOfHome(count: number): Promise<(typeof import('./home-panels'))[]> {
  vi.doMock('@erplora/ui/components', () => components);
  try {
    const copies: (typeof import('./home-panels'))[] = [];
    for (let made = 0; made < count; made += 1) {
      vi.resetModules();
      copies.push(await import('./home-panels'));
    }
    return copies;
  } finally {
    vi.doUnmock('@erplora/ui/components');
    vi.resetModules();
  }
}

const zoned = await copiesOfHome(ZONES.length);

describe('a chart of business days (BASE-F06)', () => {
  const WEEK = ['2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23'];
  const chart = widget('sale.last_7_days', { kind: 'chart', map: { label: 'day', value: 'total' }, options: { format: 'currency' } });
  const days = (labels: string[], total = 0) => ({ rows: labels.map((day) => ({ day, total })) });
  const barsOf = (result: unknown, locale: string) => {
    const view = widgetView(chart, result, locale, { money: EUR });
    if (view.kind !== 'chart') throw new Error(`expected a chart, got ${view.kind}`);
    return view.bars;
  };

  it("names each day of a week by its short weekday in the person's language, never the raw ISO date", () => {
    expect(barsOf(days(WEEK), 'es').map((bar) => bar.label)).toEqual(['sáb', 'dom', 'lun', 'mar', 'mié', 'jue', 'vie']);
    expect(barsOf(days(WEEK), 'en').map((bar) => bar.label)).toEqual(['Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri']);
  });

  it("says each bar's whole day and its amount in the format the panel declares", () => {
    const [bar] = barsOf({ rows: [{ day: '2026-10-23', total: 2550 }] }, 'es');
    expect(bar).toMatchObject({ key: '2026-10-23', label: 'vie', detail: 'vie, 23 oct', text: '25,50\u00a0€' });
    expect(barsOf({ rows: [{ day: '2026-10-23', total: 500 }] }, 'en')[0]).toMatchObject({ detail: 'Fri, Oct 23', text: '€5.00' });
  });

  it('a series longer than a week names each day by its date, as its weekdays would repeat', () => {
    const fortnight = ['2026-10-10', '2026-10-17', '2026-10-23'];
    expect(barsOf(days(fortnight), 'es').map((bar) => bar.label)).toEqual(['10 oct', '17 oct', '23 oct']);
    expect(barsOf(days(fortnight), 'en').map((bar) => bar.label)).toEqual(['Oct 10', 'Oct 17', 'Oct 23']);
    // Eight days already repeat a weekday (Friday the 16th and the 23rd): one day past a week is by its date.
    const eight = ['2026-10-16', ...WEEK];
    expect(barsOf(days(eight), 'es').map((bar) => bar.label)).toEqual(['16 oct', '17 oct', '18 oct', '19 oct', '20 oct', '21 oct', '22 oct', '23 oct']);
  });

  it('a business day is the same day in every time zone: a civil day, never an instant', () => {
    const zone = process.env.TZ;
    try {
      ZONES.forEach((tz, index) => {
        // A page opened in that zone: its own copy of the module (`copiesOfHome`), first used here.
        process.env.TZ = tz;
        expect(zoned[index].widgetView(chart, days(['2026-10-17']), 'es'), tz).toMatchObject({
          kind: 'chart',
          bars: [{ label: 'sáb', detail: 'sáb, 17 oct' }],
        });
      });
    } finally {
      if (zone === undefined) delete process.env.TZ;
      else process.env.TZ = zone;
    }
  });

  it('a label that is no day stays as it is', () => {
    const labels = ['Mañana', '2026-02-30', '2026-10-23T02:23:55Z', '17/10/2026'];
    expect(barsOf(days(labels), 'es').map((bar) => [bar.key, bar.label, bar.detail])).toEqual(labels.map((label) => [label, label, label]));
  });
});

// BASE-F06, BASE-F09 — a timeline's moments (Sales' «Recent activity»): the panel painted the instant as the server
// sent it, `2026-10-23T02:23:55.572622Z`. As Square, Shopify or a phone's call log: the local time alone if it was
// today, «yesterday» and the time, else the short date and the time (its year only when it is another).
describe('when a timeline entry happened (BASE-F06, BASE-F09)', () => {
  const MADRID = 'Europe/Madrid';
  /** Friday 23 Oct 2026, 12:00 in Madrid. */
  const NOW = new Date('2026-10-23T10:00:00Z');
  const recent = widget('sale.recent_activity', {
    kind: 'timeline',
    map: { title: 'number', description: 'customer_name', time: 'created_at' },
  });
  const moments = (times: unknown[], locale: string, timeZone = MADRID) => {
    const rows = times.map((created_at, index) => ({ number: `S-${index}`, customer_name: '', created_at }));
    const view = widgetView(recent, { rows }, locale, { now: NOW, timeZone });
    if (view.kind !== 'timeline') throw new Error(`expected a timeline, got ${view.kind}`);
    return view.entries.map((entry) => [entry.time, entry.datetime]);
  };

  it("says today's by its local time alone in the person's language, the instant whole as its datetime", () => {
    const at = '2026-10-23T02:23:55.572622Z';
    expect(moments([at], 'es')).toEqual([['4:23', at]]);
    expect(moments([at], 'en')).toEqual([['4:23 AM', at]]);
  });

  it("says yesterday's with the word for yesterday and its time", () => {
    expect(moments(['2026-10-22T16:10:00Z'], 'es')).toEqual([['Ayer 18:10', '2026-10-22T16:10:00Z']]);
    expect(moments(['2026-10-22T16:10:00Z'], 'en')).toEqual([['Yesterday 6:10 PM', '2026-10-22T16:10:00Z']]);
  });

  it('says an older one by its short date and its time, and its year only when it is another', () => {
    expect(moments(['2026-10-20T16:10:00Z'], 'es')).toEqual([['20 oct, 18:10', '2026-10-20T16:10:00Z']]);
    expect(moments(['2026-10-20T16:10:00Z'], 'en')).toEqual([['Oct 20, 6:10 PM', '2026-10-20T16:10:00Z']]);
    expect(moments(['2025-12-31T22:30:00Z'], 'es')).toEqual([['31 dic 2025, 23:30', '2025-12-31T22:30:00Z']]);
    expect(moments(['2025-12-31T22:30:00Z'], 'en')).toEqual([['Dec 31, 2025, 11:30 PM', '2025-12-31T22:30:00Z']]);
  });

  it("today and yesterday are the zone's days, not UTC's", () => {
    // 22:30Z on the 22nd is already the 23rd in Madrid, and still the 22nd in Los Angeles (03:00 there now).
    expect(moments(['2026-10-22T22:30:00Z'], 'es')).toEqual([['0:30', '2026-10-22T22:30:00Z']]);
    expect(moments(['2026-10-22T22:30:00Z'], 'es', 'America/Los_Angeles')).toEqual([['Ayer 15:30', '2026-10-22T22:30:00Z']]);
  });

  it('a civil day says «today», «yesterday» or its date, without a time', () => {
    expect(moments(['2026-10-23', '2026-10-22', '2026-10-17'], 'es')).toEqual([
      ['Hoy', '2026-10-23'],
      ['Ayer', '2026-10-22'],
      ['17 oct', '2026-10-17'],
    ]);
    expect(moments(['2025-10-23'], 'en')).toEqual([['Oct 23, 2025', '2025-10-23']]);
  });

  it('says each one whole as its detail: the date and time in the zone, a civil day without a time nor a zone', () => {
    const view = widgetView(
      recent,
      { rows: ['2026-10-22T22:30:00Z', '2026-10-22', '10:00'].map((created_at) => ({ number: 'S', created_at })) },
      'es',
      { now: NOW, timeZone: 'America/Los_Angeles' },
    );
    if (view.kind !== 'timeline') throw new Error(`expected a timeline, got ${view.kind}`);
    expect(view.entries.map((entry) => entry.detail)).toEqual(['22 oct 2026, 15:30', '22 oct 2026', undefined]);
  });

  it('a time that is no date stays as it is, and has no datetime', () => {
    const times = ['10:00', 'Mañana', '2026-02-30', '2026-10-23T25:00:00Z', 1729677835, null];
    expect(moments(times, 'es')).toEqual([
      ['10:00', undefined],
      ['Mañana', undefined],
      ['2026-02-30', undefined],
      ['2026-10-23T25:00:00Z', undefined],
      ['1729677835', undefined],
      ['', undefined],
    ]);
  });
});
