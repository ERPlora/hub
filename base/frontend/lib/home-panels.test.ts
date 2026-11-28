import { describe, expect, it } from 'vitest';

import { EUR, widget } from '../__tests__/home-fixtures';
import { formatValue, rowsOf, widgetView } from './home-panels';

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
