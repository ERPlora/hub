import { describe, expect, it } from 'vitest';

import { EUR, widget } from '../__tests__/home-fixtures';
import type { WidgetDef } from '../operations/home';
import { widgetView } from './home-panels';

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
// hub's OutfitKit drew none at all). The bar measures the size of the value against the biggest size; as a report
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

// A bar-list with the colour of its row (`map.color`). The colour is typed by a person (a role's colour in Staff), so
// only a hex colour (#rgb, #rrggbb) reaches the bar: anything else keeps the panel's colour. A negative stays red
// whatever its row's colour: the alarm wins over the category, as Excel's data bars, Power BI's rules or Grafana's
// thresholds do.
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
