// The rules of the Home that are not the server's (the old hub's `dashboard-heading.ts`, `setup-status.ts`,
// `dashboard-widgets.ts` and the «My apps» card): pure, so each one is pinned here once.
import { describe, expect, it, vi } from 'vitest';

import type { SetupItem, SetupStatus, WidgetDef } from '../operations';
import {
  activeWidgetKeys,
  blockingItems,
  checklistView,
  formatValue,
  greetingSlot,
  heading,
  orderByUse,
  readJsonBlock,
  recordUse,
  rowsOf,
  saleStatus,
  widgetView,
} from './home';

function item(key: string, fields: Partial<SetupItem> = {}): SetupItem {
  return {
    key,
    app: key.split('.')[0],
    state: 'pending',
    level: 'functional',
    required: true,
    actionable: true,
    title: key,
    description: '',
    icon: 'ion:settings-outline',
    route: `/${key}`,
    order: 50,
    ...fields,
  };
}

function status(items: SetupItem[], fields: Partial<SetupStatus> = {}): SetupStatus {
  const pending = items.filter((i) => i.state === 'pending').length;
  const unavailable = items.filter((i) => i.state === 'unavailable').length;
  const blocking = items.filter((i) => i.state === 'pending' && i.level === 'legal').length;
  return { total: items.length, pending, unavailable, blocking_pending: blocking, items, ...fields };
}

function widget(key: string, fields: Partial<WidgetDef> = {}): WidgetDef {
  return {
    key,
    app: key.split('.')[0],
    title: key,
    icon: '',
    category: 'Demo',
    size: 'md',
    default: false,
    kind: 'kpi',
    operation: 'demo.item.stats',
    params: {},
    map: { value: 'open' },
    options: {},
    component: null,
    refresh_on: [],
    live: true,
    ...fields,
  };
}

describe('heading (BASE-G127)', () => {
  it('greets by the hour while the business has no name: morning before 12, afternoon before 20, evening after', () => {
    expect([0, 11, 12, 19, 20, 23].map(greetingSlot)).toEqual([
      'morning',
      'morning',
      'afternoon',
      'afternoon',
      'evening',
      'evening',
    ]);
  });

  it("is the business's name when it has one, never an e-mail address nor blanks", () => {
    expect(heading('  Bar Pepe ', 9)).toEqual({ kind: 'business', name: 'Bar Pepe' });
    expect(heading('', 9)).toEqual({ kind: 'greeting', slot: 'morning' });
    expect(heading('   ', 21)).toEqual({ kind: 'greeting', slot: 'evening' });
    expect(heading('ana@example.com', 13)).toEqual({ kind: 'greeting', slot: 'afternoon' });
    expect(heading(undefined, 13)).toEqual({ kind: 'greeting', slot: 'afternoon' });
  });
});

describe('readJsonBlock', () => {
  it('reads a JSON block Django embedded, and nothing when it is missing or broken', () => {
    document.body.innerHTML = `<script id="hub-home" type="application/json">{"name": "Bar"}</script>
      <script id="broken" type="application/json">{</script>`;
    expect(readJsonBlock<{ name: string }>('hub-home', document)).toEqual({ name: 'Bar' });
    expect(readJsonBlock('missing', document)).toBeUndefined();
    expect(readJsonBlock('broken', document)).toBeUndefined();
  });
});

describe('checklistView (BASE-G22, BASE-G130)', () => {
  it('is empty with nothing to show: an empty answer is silence, never «your business is ready»', () => {
    expect(checklistView(undefined, {}).empty).toBe(true);
    expect(checklistView(status([]), {}).empty).toBe(true);
    expect(checklistView(status([]), {}).complete).toBe(false);
  });

  it('counts done as total minus pending minus unavailable', () => {
    const view = checklistView(
      status([item('a.x', { state: 'done' }), item('a.y'), item('a.z', { state: 'unavailable' })]),
      {},
    );
    expect([view.done, view.total]).toEqual([1, 3]);
  });

  it('is complete only when nothing is pending nor unavailable, and then folds every row away', () => {
    const done = checklistView(status([item('a.x', { state: 'done' })]), {});
    expect([done.complete, done.rows.length]).toEqual([true, 0]);
    const ours = checklistView(status([item('a.x', { state: 'unavailable' })]), {});
    expect(ours.complete).toBe(false);
  });

  it('collapsed: what is left, ⛔ and 🔴 before 🟡 (folded), at most `maxRows`', () => {
    const items = [
      item('a.done', { state: 'done' }),
      item('a.rec', { level: 'recommended' }),
      item('a.legal', { level: 'legal' }),
      item('a.f1'),
      item('a.f2'),
    ];
    const view = checklistView(status(items), { maxRows: 2 });
    expect(view.rows.map((i) => i.key)).toEqual(['a.legal', 'a.f1']);
    expect(view.hidden).toBe(3);
  });

  it('collapsed with only 🟡 left: shows them instead of an empty body', () => {
    const view = checklistView(status([item('a.rec', { level: 'recommended' })]), {});
    expect(view.rows.map((i) => i.key)).toEqual(['a.rec']);
  });

  it('collapsed: hides a row another card of the screen offers («Your apps»), never one of ours', () => {
    const items = [item('base.apps'), item('base.team'), item('x.ours', { state: 'unavailable' })];
    const view = checklistView(status(items), { alreadyOnScreen: ['base.apps', 'x.ours'] });
    expect(view.rows.map((i) => i.key)).toEqual(['base.team', 'x.ours']);
    // Expanded means «everything left to do»: nothing is deduplicated there (hub#487).
    const all = checklistView(status(items), { alreadyOnScreen: ['base.apps'], expanded: true });
    expect(all.rows.map((i) => i.key)).toEqual(['base.apps', 'base.team', 'x.ours']);
    expect(all.hidden).toBe(0);
  });
});

describe('blockingItems (the strip)', () => {
  it('lists the ⛔ steps still pending, only while the server counts some', () => {
    const items = [item('invoice.business_identity', { level: 'legal' }), item('a.f'), item('a.l', { level: 'legal', state: 'done' })];
    expect(blockingItems(status(items)).map((i) => i.key)).toEqual(['invoice.business_identity']);
    expect(blockingItems(status(items, { blocking_pending: 0 }))).toEqual([]);
    expect(blockingItems(undefined)).toEqual([]);
  });
});

const EUR = { currency: 'EUR', decimals: 2 };
const PLN = { currency: 'PLN', decimals: 2 };

// BASE-G98: an amount of the Home is in the business's currency (its country's, as Settings › Business says), with
// its decimals and the symbol a till of that country prints — a Polish business reads «zł», a Spanish one «€» —,
// never a fixed euro; until the business is known, the amount without a symbol, never another currency's.
describe('formatValue: the business currency (BASE-G98)', () => {
  it("writes an amount (the server's cents) in the business's currency, by its local symbol", () => {
    expect(formatValue(1250, 'currency', 'es', EUR)).toBe('12,50\u00a0€');
    expect(formatValue(1250, 'currency', 'es', PLN)).toBe('12,50\u00a0zł');
    expect(formatValue(1250, 'currency', 'en', PLN)).toBe('zł\u00a012.50');
  });

  it('with as many decimals as the currency has', () => {
    expect(formatValue(123400, 'currency', 'en', { currency: 'JPY', decimals: 0 })).toBe('¥1,234');
    expect(formatValue(123456, 'currency', 'en', { currency: 'KWD', decimals: 3 })).toBe('KWD\u00a01,234.560');
  });

  it('without the business yet, the amount alone, never in a currency it is not', () => {
    expect(formatValue(1250, 'currency', 'es')).toBe('12,50');
    expect(formatValue(1250, 'currency', 'en')).toBe('12.50');
  });

  it("a panel's every amount — a sparkline's last value, each bar of a list — is in the business's currency", () => {
    const spark = widget('s.days', { kind: 'sparkline', map: { series: 'n' }, options: { format: 'currency' } });
    expect(widgetView(spark, [{ n: 100 }, { n: 250 }], 'es', { money: PLN })).toMatchObject({ value: '2,50\u00a0zł' });
    const list = widget('s.top', { kind: 'bar-list', map: { label: 'name', value: 'total' }, options: { valueFormat: 'currency' } });
    const view = widgetView(list, { rows: [{ name: 'Café', total: 1250 }] }, 'es', { money: PLN });
    expect(view).toMatchObject({ kind: 'bar-list', bars: [{ label: 'Café', text: '12,50\u00a0zł' }] });
  });

  it('one format per currency: a business that follows another on the same page keeps its own', () => {
    expect(formatValue(500, 'currency', 'es', PLN)).toBe('5,00\u00a0zł');
    expect(formatValue(500, 'currency', 'es', EUR)).toBe('5,00\u00a0€');
  });
});

describe('rowsOf / widgetView (BASE-G166)', () => {
  it('reads the rows of a page, a list or one object, as the server reads the first row', () => {
    expect(rowsOf({ rows: [{ a: 1 }], total: 1 })).toEqual([{ a: 1 }]);
    expect(rowsOf({ items: [{ a: 2 }] })).toEqual([{ a: 2 }]);
    expect(rowsOf([{ a: 3 }])).toEqual([{ a: 3 }]);
    expect(rowsOf({ open: 4 })).toEqual([{ open: 4 }]);
    expect(rowsOf(null)).toEqual([]);
  });

  it('a kpi reads `map.value` of the first row, formatted by `options.format`', () => {
    expect(widgetView(widget('demo.k'), { open: 1234 }, 'es')).toEqual({ kind: 'kpi', value: '1234', label: undefined });
    const money = widget('s.k', { map: { value: 'total' }, options: { format: 'currency' } });
    expect(widgetView(money, { total: 1250 }, 'es', { money: EUR })).toMatchObject({ kind: 'kpi', value: '12,50 €' });
    expect(widgetView(money, { total: 1250 }, 'es', { money: PLN })).toMatchObject({ kind: 'kpi', value: '12,50 zł' });
  });

  it('says «No data» without a row or without the mapped value, never a 0 it did not get', () => {
    expect(widgetView(widget('demo.k'), { rows: [] }, 'en')).toEqual({ kind: 'empty' });
    expect(widgetView(widget('demo.k'), { other: 1 }, 'en')).toEqual({ kind: 'empty' });
  });

  it('a bar-list, a timeline and a chart read every row', () => {
    const bars = widget('i.low', { kind: 'bar-list', map: { label: 'name', value: 'stock' } });
    expect(widgetView(bars, { rows: [{ name: 'Café', stock: 3 }, { name: 'Té', stock: 1 }] }, 'es')).toEqual({
      kind: 'bar-list',
      bars: [
        { label: 'Café', value: 3, text: '3', share: 1 },
        { label: 'Té', value: 1, text: '1', share: 1 / 3 },
      ],
    });
    const timeline = widget('b.recent', { kind: 'timeline', map: { title: 'name', time: 'at' } });
    expect(widgetView(timeline, [{ name: 'Ana', at: '10:00' }], 'es')).toEqual({
      kind: 'timeline',
      entries: [{ title: 'Ana', time: '10:00', description: '' }],
    });
    const chart = widget('s.week', { kind: 'chart', map: { label: 'day', value: 'n' } });
    expect(widgetView(chart, [{ day: 'L', n: 2 }, { day: 'M', n: 4 }], 'es')).toMatchObject({
      kind: 'chart',
      bars: [
        { label: 'L', value: 2, share: 0.5 },
        { label: 'M', value: 4, share: 1 },
      ],
    });
  });

  it('a sparkline collects `map.series` over the rows and shows the last value', () => {
    const spark = widget('s.days', { kind: 'sparkline', map: { series: 'n' } });
    expect(widgetView(spark, [{ n: 1 }, { n: 3 }, { n: 2 }], 'en')).toEqual({ kind: 'sparkline', series: [1, 3, 2], value: '2' });
  });

  it('a stat carries its own label and severity', () => {
    const stat = widget('s.s', { kind: 'stat', map: { value: 'n', severity: 'tone' }, options: { label: 'Late' } });
    expect(widgetView(stat, { n: 2, tone: 'danger' }, 'en')).toEqual({ kind: 'stat', value: '2', label: 'Late', severity: 'danger' });
  });
});

// BASE-F06 — a chart of business days (Sales' «Sales, last 7 days»): the old hub's gh:hub#2392 painted each day
// as `2026-10-17` and no amount at all.
describe('a chart of business days (BASE-F06, gh:hub#2392)', () => {
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

  it('a business day is the same day in every time zone: a civil day, never an instant', async () => {
    const zone = process.env.TZ;
    try {
      for (const tz of ['America/Los_Angeles', 'Europe/Madrid', 'Pacific/Kiritimati']) {
        // A page opened in that zone: a fresh module, so no formatter of another zone is reused.
        process.env.TZ = tz;
        vi.resetModules();
        const fresh = await import('./home');
        expect(fresh.widgetView(chart, days(['2026-10-17']), 'es'), tz).toMatchObject({
          kind: 'chart',
          bars: [{ label: 'sáb', detail: 'sáb, 17 oct' }],
        });
      }
    } finally {
      if (zone === undefined) delete process.env.TZ;
      else process.env.TZ = zone;
      vi.resetModules();
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

describe('activeWidgetKeys (BASE-G167)', () => {
  const catalogue = [widget('a.one', { default: true }), widget('a.two'), widget('b.three', { default: true })];

  it("starts from the catalogue's defaults while this browser chose nothing", () => {
    expect(activeWidgetKeys(null, catalogue)).toEqual(['a.one', 'b.three']);
  });

  it('keeps the chosen order and drops a panel whose app is gone, without a word', () => {
    expect(activeWidgetKeys(['b.three', 'gone.x', 'a.two'], catalogue)).toEqual(['b.three', 'a.two']);
  });

  it('keeps an empty choice empty (the person removed every panel)', () => {
    expect(activeWidgetKeys([], catalogue)).toEqual([]);
  });
});

describe('orderByUse (BASE-G165)', () => {
  it('puts the apps opened most in this browser first, the rest in their order', () => {
    const apps = [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }];
    expect(orderByUse(apps, { c: 3, b: 1 }).map((a) => a.id)).toEqual(['c', 'b', 'a', 'd']);
  });

  it('counts an opening in the browser store, and survives a broken store', () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    expect(recordUse('demo', storage)).toEqual({ demo: 1 });
    expect(recordUse('demo', storage)).toEqual({ demo: 2 });
    store.set('hub-app-usage', '{');
    expect(recordUse('sale', storage)).toEqual({ sale: 1 });
  });
});

describe('saleStatus (BASE-G129)', () => {
  it("speaks the sales history's words, with «Other» for a status this screen does not know", () => {
    expect(['completed', 'voided', 'refunded', 'parked'].map(saleStatus)).toEqual([
      { key: 'completed', tone: 'success' },
      { key: 'voided', tone: 'danger' },
      { key: 'refunded', tone: 'warning' },
      { key: 'other', tone: 'neutral' },
    ]);
  });
});
