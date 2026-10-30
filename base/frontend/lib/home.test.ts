// The rules of the Home that are not the server's (the old hub's `dashboard-heading.ts`, `setup-status.ts`,
// `dashboard-widgets.ts` and the «My apps» card): pure, so each one is pinned here once.
import * as components from '@erplora/ui/components';
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
  it("writes an amount (the server's minor unit of the currency) in the business's currency, by its local symbol", () => {
    expect(formatValue(1250, 'currency', 'es', EUR)).toBe('12,50\u00a0€');
    expect(formatValue(1250, 'currency', 'es', PLN)).toBe('12,50\u00a0zł');
    expect(formatValue(1250, 'currency', 'en', PLN)).toBe('zł\u00a012.50');
  });

  it('with as many decimals as the currency has, the amount being in its minor unit', () => {
    // FIX-HUB-BASE-ASSISTANT-CARD-MONEY-IN-BUSINESS-NOT-PREVIEW-CURRENCY: every amount the server sends is in the minor
    // unit of its currency (`currency_decimals`: 0 in JPY, 3 in KWD), as Sales, Cash register and Inventory paint the
    // same figures; this test said «¥1,234» for ¥123,400, a hundred times less, by dividing every currency by 100.
    expect(formatValue(123400, 'currency', 'en', { currency: 'JPY', decimals: 0 })).toBe('¥123,400');
    expect(formatValue(123456, 'currency', 'en', { currency: 'KWD', decimals: 3 })).toBe('KWD\u00a0123.456');
    expect(formatValue(123456, 'currency', 'en', EUR)).toBe('€1,234.56');
  });

  it('without the business yet, the amount alone, never in a currency it is not', () => {
    expect(formatValue(1250, 'currency', 'es')).toBe('12,50');
    expect(formatValue(1250, 'currency', 'en')).toBe('12.50');
  });

  it('an amount of four figures groups its thousands, as Sales writes it (base-money-thousands-grouping)', () => {
    // The Spanish CLDR only groups from five figures: the Home said «1234,56 €» where Sales says «1.234,56 €».
    expect(formatValue(123456, 'currency', 'es', EUR)).toBe('1.234,56 €');
    expect(formatValue('123456', 'currency', 'es', EUR)).toBe('1.234,56 €');
    expect(formatValue(123456, 'currency', 'es')).toBe('1.234,56');
    expect(formatValue(123400, 'currency', 'es', { currency: 'JPY', decimals: 0 })).toBe('123.400 ¥');
    const list = widget('s.top', { kind: 'bar-list', map: { label: 'name', value: 'total' }, options: { valueFormat: 'currency' } });
    const view = widgetView(list, { rows: [{ name: 'Café', total: 123456 }] }, 'es', { money: EUR });
    expect(view).toMatchObject({ kind: 'bar-list', bars: [{ label: 'Café', text: '1.234,56 €' }] });
    const kpi = widget('s.total', { kind: 'kpi', map: { value: 'total' }, options: { format: 'currency' } });
    expect(widgetView(kpi, { total: 987654 }, 'es', { money: EUR })).toMatchObject({ kind: 'kpi', value: '9.876,54 €' });
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

// BASE-F06 — a value a row does not have (Cash register's «Recent discrepancies»: a session closed without a count has
// no difference) painted as «0,00 €», a discrepancy of zero that never was. As Square, Toast, Shopify, Lightspeed or
// Odoo say a cell without a value: «—» and no bar; the row stays, so the session is still in sight. A real 0 is a 0.
describe('a value the row does not have (BASE-F06): «—», never a made-up 0', () => {
  const discrepancies = widget('cash_register.recent_sessions', {
    kind: 'bar-list',
    map: { label: 'number', value: 'difference' },
    options: { valueFormat: 'currency' },
  });
  const barsOf = (rows: Record<string, unknown>[], locale = 'es') => {
    const view = widgetView(discrepancies, { rows }, locale, { money: EUR });
    if (view.kind !== 'bar-list') throw new Error(`expected a bar-list, got ${view.kind}`);
    return view.bars;
  };

  it('a bar-list row without its value says «—» with no share, and a real 0 is still «0,00 €»', () => {
    const bars = barsOf([
      { number: 'CS-3', difference: 250 },
      { number: 'CS-2', difference: null },
      { number: 'CS-1', difference: 0 },
    ]);
    expect(bars).toEqual([
      { label: 'CS-3', value: 250, text: '2,50 €', share: 1 },
      { label: 'CS-2', value: null, text: '—', share: 0 },
      { label: 'CS-1', value: 0, text: '0,00 €', share: 0 },
    ]);
  });

  it('absent or blank is no value either; a value that is no number is still left out', () => {
    const bars = barsOf([{ number: 'CS-4' }, { number: 'CS-3', difference: '' }, { number: 'CS-2', difference: ' ' }, { number: 'CS-1', difference: 'n/a' }]);
    expect(bars.map((bar) => [bar.label, bar.value, bar.text])).toEqual([
      ['CS-4', null, '—'],
      ['CS-3', null, '—'],
      ['CS-2', null, '—'],
    ]);
  });

  it('only rows without a value: still the rows, never «No data» nor a list of zeros', () => {
    expect(barsOf([{ number: 'CS-1', difference: null }], 'en')).toEqual([{ label: 'CS-1', value: null, text: '—', share: 0 }]);
  });

  it('a day of a chart without its value says «—», and the other days keep their share', () => {
    const chart = widget('sale.last_7_days', { kind: 'chart', map: { label: 'day', value: 'total' }, options: { format: 'currency' } });
    const view = widgetView(chart, { rows: [{ day: '2026-10-22', total: null }, { day: '2026-10-23', total: 500 }] }, 'es', { money: EUR });
    expect(view).toMatchObject({
      kind: 'chart',
      bars: [
        { key: '2026-10-22', value: null, text: '—', share: 0 },
        { key: '2026-10-23', value: 500, text: '5,00 €', share: 1 },
      ],
    });
  });

  it('a sparkline skips a point without its value and never says «null» as its figure', () => {
    const spark = widget('s.days', { kind: 'sparkline', map: { series: 'n', value: 'today' } });
    expect(widgetView(spark, [{ n: 1, today: null }, { n: null }, { n: 3 }], 'en')).toEqual({ kind: 'sparkline', series: [1, 3], value: undefined });
    const last = widget('s.days', { kind: 'sparkline', map: { series: 'n' } });
    expect(widgetView(last, [{ n: 1 }, { n: 0 }, { n: null }], 'en')).toEqual({ kind: 'sparkline', series: [1, 0], value: '0' });
  });
});

// BASE-F06 — a bar-list with negatives (Cash register's «Recent discrepancies»: a drawer 0,40 € short and one 5,50 €
// over) painted the shortfall as long as the biggest bar: its share was -0.0727, a width the browser drops (the old
// hub's outfitkit#244 drew none at all). The bar measures the size of the value against the biggest size; as a report
// says it (Excel, QuickBooks, Square), only a negative figure is marked — red, with its sign in the text («-0,40 €») —
// and every other bar keeps the panel's colour: a surplus is a discrepancy too, and a product with 1 left beside one
// at -1 is still low on stock (rv-hub-264), so neither is ever painted as «good».
describe('a bar-list with negatives (BASE-F06): the bar measures the size, only a negative is marked', () => {
  const discrepancies = widget('cash_register.recent_sessions', {
    kind: 'bar-list',
    map: { label: 'number', value: 'difference' },
    options: { valueFormat: 'currency' },
  });
  const barsOf = (rows: Record<string, unknown>[], fields: Partial<WidgetDef> = {}) => {
    const view = widgetView({ ...discrepancies, ...fields }, { rows }, 'es', { money: EUR });
    if (view.kind !== 'bar-list') throw new Error(`expected a bar-list, got ${view.kind}`);
    return view.bars;
  };

  it('-0,40 € and +5,50 € have shares 0,0727 and 1, and only the shortfall is marked negative', () => {
    const bars = barsOf([
      { number: 'CS-2', difference: 550 },
      { number: 'CS-1', difference: -40 },
    ]);
    expect(bars).toStrictEqual([
      { label: 'CS-2', value: 550, text: '5,50 €', share: 1 },
      { label: 'CS-1', value: -40, text: '-0,40 €', share: 40 / 550, negative: true },
    ]);
    expect(bars[1].share).toBeCloseTo(0.0727, 4);
  });

  it('a stock list with -1 and 1 marks only the -1: the 1 is low stock as well, never painted as «good»', () => {
    const bars = barsOf([{ name: 'Té', stock: -1 }, { name: 'Café', stock: 1 }], {
      key: 'inventory.low_stock_products',
      map: { label: 'name', value: 'stock' },
      options: { valueFormat: 'number' },
    });
    expect(bars).toStrictEqual([
      { label: 'Té', value: -1, text: '-1', share: 1, negative: true },
      { label: 'Café', value: 1, text: '1', share: 1 },
    ]);
  });

  it('the biggest size fills the bar whatever its sign: a shortfall bigger than any surplus', () => {
    const bars = barsOf([
      { number: 'CS-2', difference: 1235 },
      { number: 'CS-1', difference: -123456 },
    ]);
    expect(bars.map((bar) => [bar.share, bar.negative])).toEqual([
      [1235 / 123456, undefined],
      [1, true],
    ]);
    expect(bars.every((bar) => bar.share >= 0 && bar.share <= 1)).toBe(true);
  });

  it('a declared `options.max` still caps the scale, by size', () => {
    const bars = barsOf([{ number: 'CS-1', difference: -250 }], { options: { valueFormat: 'currency', max: 1000 } });
    expect(bars).toStrictEqual([{ label: 'CS-1', value: -250, text: '-2,50 €', share: 0.25, negative: true }]);
  });

  it('an even drawer (0) and one without a count («—») are not marked among negatives', () => {
    const bars = barsOf([
      { number: 'CS-3', difference: -40 },
      { number: 'CS-2', difference: 0 },
      { number: 'CS-1', difference: null },
    ]);
    expect(bars.map((bar) => [bar.text, bar.share, 'negative' in bar])).toEqual([
      ['-0,40 €', 1, true],
      ['0,00 €', 0, false],
      ['—', 0, false],
    ]);
  });

  it('a list with no negatives paints as before: nothing marked', () => {
    const bars = barsOf([
      { number: 'CS-2', difference: 550 },
      { number: 'CS-1', difference: 40 },
    ]);
    expect(bars.map((bar) => [bar.share, 'negative' in bar])).toEqual([
      [1, false],
      [40 / 550, false],
    ]);
  });

  it('a chart day below zero (refunds over sales) is measured by its size and marked negative, never a stub', () => {
    const chart = widget('sale.last_7_days', { kind: 'chart', map: { label: 'day', value: 'total' }, options: { format: 'currency' } });
    const view = widgetView(chart, { rows: [{ day: '2026-10-22', total: -200 }, { day: '2026-10-23', total: 500 }] }, 'es', { money: EUR });
    expect(view).toMatchObject({
      kind: 'chart',
      bars: [
        { key: '2026-10-22', value: -200, text: '-2,00 €', share: 0.4, negative: true },
        { key: '2026-10-23', value: 500, text: '5,00 €', share: 1 },
      ],
    });
    if (view.kind !== 'chart') throw new Error(`expected a chart, got ${view.kind}`);
    expect('negative' in view.bars[1]).toBe(false);
  });
});

// BASE-F06 — a bar-list with the colour of its row (FIX-HUB-BASE-HOME-BAR-LIST-IGNORES-MAP-COLOR): Staff's «Staff by
// role» painted every role's bar in the panel's colour although each role has its own; the old hub's `renderBarList`
// gave each bar `color: row[map.color]`. The colour is typed by a person (a role's colour in Staff), so only a hex
// colour (#rgb, #rrggbb) reaches the bar: anything else paints as before. A negative stays red whatever its row's
// colour: the alarm wins over the category, as Excel's data bars, Power BI's rules or Grafana's thresholds do.
describe('a bar-list with the colour of its row (BASE-F06): `map.color`, only a hex colour, red still wins', () => {
  const byRole = widget('staff.by_role', {
    kind: 'bar-list',
    map: { label: 'name', value: 'member_count', color: 'color' },
    options: { valueFormat: 'number' },
  });
  const barsOf = (rows: Record<string, unknown>[], fields: Partial<WidgetDef> = {}) => {
    const view = widgetView({ ...byRole, ...fields }, { rows }, 'es');
    if (view.kind !== 'bar-list') throw new Error(`expected a bar-list, got ${view.kind}`);
    return view.bars;
  };

  it('each bar takes the colour its row gives, #rrggbb or #rgb', () => {
    const bars = barsOf([
      { name: 'Estilista', member_count: 4, color: '#2E7D32' },
      { name: 'Recepción', member_count: 2, color: '#c2185b' },
      { name: 'Limpieza', member_count: 1, color: '#fa0' },
    ]);
    expect(bars).toStrictEqual([
      { label: 'Estilista', value: 4, text: '4', share: 1, color: '#2E7D32' },
      { label: 'Recepción', value: 2, text: '2', share: 0.5, color: '#c2185b' },
      { label: 'Limpieza', value: 1, text: '1', share: 0.25, color: '#fa0' },
    ]);
  });

  it('a panel that does not declare `map.color` paints as before, even when its rows have a colour', () => {
    const bars = barsOf([{ name: 'Estilista', member_count: 4, color: '#2e7d32' }], { map: { label: 'name', value: 'member_count' } });
    expect(bars).toStrictEqual([{ label: 'Estilista', value: 4, text: '4', share: 1 }]);
  });

  it('a row with no colour, or one that is no hex colour, paints as before: nothing typed reaches the style', () => {
    const typed = ['', '   ', 'red', 'rgb(0, 0, 0)', 'var(--ion-color-danger)', '#12345', '#ggg', '#2e7d32ff', ' #2e7d32', '#2e7d32;', '#fff; background: url(x)'];
    const bars = barsOf([
      ...typed.map((color, index) => ({ name: `R${index}`, member_count: 1, color })),
      { name: 'Sin color', member_count: 1, color: null },
      { name: 'Sin campo', member_count: 1 },
      { name: 'Número', member_count: 1, color: 0x2e7d32 },
    ]);
    expect(bars).toHaveLength(typed.length + 3);
    expect(bars.filter((bar) => 'color' in bar)).toEqual([]);
  });

  it('a negative is red whatever its row says: it carries no colour of its own, only the mark', () => {
    const bars = barsOf([
      { name: 'Estilista', member_count: 2, color: '#2e7d32' },
      { name: 'Recepción', member_count: -1, color: '#2e7d32' },
    ]);
    expect(bars).toStrictEqual([
      { label: 'Estilista', value: 2, text: '2', share: 1, color: '#2e7d32' },
      { label: 'Recepción', value: -1, text: '-1', share: 0.5, negative: true },
    ]);
  });

  it('a row without its value («—») has no bar, so no colour either', () => {
    expect(barsOf([{ name: 'Estilista', member_count: null, color: '#2e7d32' }])).toStrictEqual([
      { label: 'Estilista', value: null, text: '—', share: 0 },
    ]);
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
    // Only this module is the page's: the UI library already loaded is handed to each fresh copy, not evaluated again
    // (every component and Ionic, three times over, outlasted the test on a busy run).
    vi.doMock('@erplora/ui/components', () => components);
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
      vi.doUnmock('@erplora/ui/components');
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
