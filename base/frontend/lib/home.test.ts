import { describe, expect, it } from 'vitest';

import { EUR, setupItem as item, setupStatus as status, widget } from '../__tests__/home-fixtures';
import {
  activeWidgetKeys,
  blockingItems,
  checklistView,
  formatValue,
  greetingSlot,
  heading,
  MAX_VISIBLE_ROWS,
  orderByUse,
  PHONE_MAX_VISIBLE_ROWS,
  readJsonBlock,
  recordUse,
  rowsOf,
  saleStatus,
  widgetView,
} from './home';

describe('heading', () => {
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

describe('checklistView', () => {
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

  it('collapsed: the ⛔ come first whatever the server\'s order, so a phone\'s two rows never hide them (hub#801)', () => {
    // Keys against the alphabet: only the server's order puts each level in this order.
    const items = [
      item('z.f1', { order: 30 }),
      item('m.f2', { order: 31 }),
      item('z.legal', { level: 'legal', order: 40 }),
      item('a.f3', { order: 50 }),
      item('a.settled', { level: 'legal', state: 'done', order: 55 }),
      item('a.legal2', { level: 'legal', order: 60 }),
      item('a.rec', { level: 'recommended', order: 70 }),
    ];
    const phone = checklistView(status(items), { maxRows: PHONE_MAX_VISIBLE_ROWS });
    expect(phone.rows.map((i) => i.key)).toEqual(['z.legal', 'a.legal2']);
    expect(phone.hidden).toBe(5);
    // Each level keeps the server's order among its own steps.
    const desk = checklistView(status(items), { maxRows: MAX_VISIBLE_ROWS });
    expect(desk.rows.map((i) => i.key)).toEqual(['z.legal', 'a.legal2', 'z.f1', 'm.f2', 'a.f3']);
    // Expanded stays as the server sent it.
    const all = checklistView(status(items), { expanded: true, maxRows: PHONE_MAX_VISIBLE_ROWS });
    expect(all.rows.map((i) => i.key)).toEqual(items.map((i) => i.key));
    expect(all.hidden).toBe(0);
  });

  it('collapsed with only 🟡 left: shows them instead of an empty body', () => {
    const view = checklistView(status([item('a.rec', { level: 'recommended' })]), {});
    expect(view.rows.map((i) => i.key)).toEqual(['a.rec']);
  });

  it('collapsed: hides a row another card of the screen offers («Your apps»), never one of ours', () => {
    const items = [item('base.apps'), item('base.team'), item('x.ours', { state: 'unavailable' })];
    const view = checklistView(status(items), { alreadyOnScreen: ['base.apps', 'x.ours'] });
    expect(view.rows.map((i) => i.key)).toEqual(['base.team', 'x.ours']);
    // Expanded means «everything left to do»: nothing is deduplicated there.
    const all = checklistView(status(items), { alreadyOnScreen: ['base.apps'], expanded: true });
    expect(all.rows.map((i) => i.key)).toEqual(['base.apps', 'base.team', 'x.ours']);
    expect(all.hidden).toBe(0);
  });
});

describe('blockingItems (what blocks invoicing)', () => {
  it('lists the ⛔ steps still pending, only while the server counts some', () => {
    const items = [item('invoice.business_identity', { level: 'legal' }), item('a.f'), item('a.l', { level: 'legal', state: 'done' })];
    expect(blockingItems(status(items)).map((i) => i.key)).toEqual(['invoice.business_identity']);
    expect(blockingItems(status(items, { blocking_pending: 0 }))).toEqual([]);
    expect(blockingItems(undefined)).toEqual([]);
  });
});

const PLN = { currency: 'PLN', decimals: 2 };

// An amount of the Home is in the business's currency, with its decimals and the symbol a till of that country prints;
// until the business is known, a dash, never another currency's.
describe('formatValue: the business currency', () => {
  it("writes an amount (the server's minor unit of the currency) in the business's currency, by its local symbol", () => {
    expect(formatValue(1250, 'currency', 'es', EUR)).toBe('12,50\u00a0€');
    expect(formatValue(1250, 'currency', 'es', PLN)).toBe('12,50\u00a0zł');
    expect(formatValue(1250, 'currency', 'en', PLN)).toBe('zł\u00a012.50');
  });

  it('with as many decimals as the currency has, the amount being in its minor unit', () => {
    // Every amount the server sends is in the minor unit of its currency (`currency_decimals`: 0 in JPY, 3 in KWD), as
    // Sales, Cash register and Inventory paint the same figures; dividing every currency by 100 would read «¥1,234» for
    // ¥123,400.
    expect(formatValue(123400, 'currency', 'en', { currency: 'JPY', decimals: 0 })).toBe('¥123,400');
    expect(formatValue(123456, 'currency', 'en', { currency: 'KWD', decimals: 3 })).toBe('KWD\u00a0123.456');
    expect(formatValue(123456, 'currency', 'en', EUR)).toBe('€1,234.56');
  });

  it('without the business yet, a dash, never in a currency it is not', () => {
    expect(formatValue(1250, 'currency', 'es')).toBe('—');
    expect(formatValue(1250, 'currency', 'en')).toBe('—');
  });

  it('an amount of four figures groups its thousands, as Sales writes it (base-money-thousands-grouping)', () => {
    // The Spanish CLDR only groups from five figures: the Home said «1234,56 €» where Sales says «1.234,56 €».
    expect(formatValue(123456, 'currency', 'es', EUR)).toBe('1.234,56\u00a0€');
    expect(formatValue('123456', 'currency', 'es', EUR)).toBe('1.234,56\u00a0€');
    expect(formatValue(123456, 'currency', 'es')).toBe('—');
    expect(formatValue(123400, 'currency', 'es', { currency: 'JPY', decimals: 0 })).toBe('123.400\u00a0¥');
    const list = widget('s.top', { kind: 'bar-list', map: { label: 'name', value: 'total' }, options: { valueFormat: 'currency' } });
    const view = widgetView(list, { rows: [{ name: 'Café', total: 123456 }] }, 'es', { money: EUR });
    expect(view).toMatchObject({ kind: 'bar-list', bars: [{ label: 'Café', text: '1.234,56\u00a0€' }] });
    const kpi = widget('s.total', { kind: 'kpi', map: { value: 'total' }, options: { format: 'currency' } });
    expect(widgetView(kpi, { total: 987654 }, 'es', { money: EUR })).toMatchObject({ kind: 'kpi', value: '9.876,54\u00a0€' });
  });

  it('a value that is no amount stays as it came', () => {
    expect(formatValue('n/a', 'currency', 'es', EUR)).toBe('n/a');
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

describe('rowsOf / widgetView', () => {
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

describe('activeWidgetKeys', () => {
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

describe('orderByUse', () => {
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

describe('saleStatus', () => {
  it("speaks the sales history's words, with «Other» for a status this screen does not know", () => {
    expect(['completed', 'voided', 'refunded', 'parked'].map(saleStatus)).toEqual([
      { key: 'completed', tone: 'success' },
      { key: 'voided', tone: 'danger' },
      { key: 'refunded', tone: 'warning' },
      { key: 'other', tone: 'neutral' },
    ]);
  });
});
