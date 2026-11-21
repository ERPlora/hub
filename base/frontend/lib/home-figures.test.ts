import { describe, expect, it } from 'vitest';

import { widget } from '../__tests__/home-fixtures';
import { figureCard, figureTone, isFigure, livelyRow } from './home-figures';

const figure = (key: string, tone?: unknown) => widget(key, { kind: 'kpi', options: tone === undefined ? {} : { tone } });

describe('isFigure', () => {
  it('is a kpi, a stat or a sparkline painted from its operation', () => {
    expect(['kpi', 'stat', 'sparkline'].map((kind) => isFigure(widget('a.x', { kind: kind as 'kpi' })))).toEqual([
      true,
      true,
      true,
    ]);
  });

  it('is never a list, a timeline, a chart nor a panel with its own component', () => {
    expect(['bar-list', 'timeline', 'chart'].map((kind) => isFigure(widget('a.x', { kind: kind as 'kpi' })))).toEqual([
      false,
      false,
      false,
    ]);
    expect(isFigure(widget('a.x', { kind: null, operation: null, component: 'Own' }))).toBe(false);
  });

  it('is also a stat that says its state by a severity', () => {
    expect(isFigure(widget('a.x', { kind: 'stat', map: { value: 'n', severity: 'severity' } }))).toBe(true);
  });
});

describe('figureTone', () => {
  it('is the colour of data its app declares, 1 to 6', () => {
    expect([1, 2, 3, 4, 5, 6].map((tone) => figureTone(figure('a.x', tone)))).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('is none for a panel that declares none or one out of the six', () => {
    expect([undefined, 0, 7, 2.5, '1', null].map((tone) => figureTone(figure('a.x', tone)))).toEqual([
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    ]);
  });
});

describe('livelyRow', () => {
  const keys = (row: { key: string }[]) => row.map((panel) => panel.key);

  it('takes the first figures with a colour, in the order of the board, one per colour and four at most', () => {
    const board = [
      widget('sale.chart', { kind: 'chart', options: { tone: 1 } }),
      figure('cash.balance'),
      figure('inventory.low', 6),
      figure('sale.today', 1),
      figure('inventory.value', 6),
      figure('sale.tickets', 2),
      figure('table.busy', 4),
      figure('customer.new', 5),
    ];
    expect(keys(livelyRow(board))).toEqual(['inventory.low', 'sale.today', 'sale.tickets', 'table.busy']);
  });

  it('is no row with fewer than two figures with a colour', () => {
    expect(livelyRow([figure('sale.today', 1), figure('cash.balance'), figure('inventory.value', 1)])).toEqual([]);
    expect(livelyRow([])).toEqual([]);
  });
});

describe('figureCard', () => {
  it("is a kpi's figure, nothing under it", () => {
    expect(figureCard({ kind: 'kpi', value: '3', label: 'ignored' })).toEqual({ value: '3' });
  });

  it("is a stat's figure with what it counts as its note", () => {
    expect(figureCard({ kind: 'stat', value: '2', label: 'In the queue', severity: 'ok' })).toEqual({
      value: '2',
      note: 'In the queue',
    });
  });

  it("is a sparkline's last value over its series", () => {
    expect(figureCard({ kind: 'sparkline', series: [1, 4, 2], value: '2 €' })).toEqual({
      value: '2 €',
      sparkline: [1, 4, 2],
    });
    expect(figureCard({ kind: 'sparkline', series: [1], value: undefined })).toEqual({ value: null, sparkline: [1] });
  });

  it("says a stat's state apart, in words, by its severity: never by the figure's colour", () => {
    expect(figureCard({ kind: 'stat', value: '4', label: 'In the queue', severity: 'warning' })).toEqual({
      value: '4',
      status: { tone: 'warning', label: 'In the queue' },
    });
    expect(figureCard({ kind: 'stat', value: '1', label: 'In the queue', severity: 'danger' })).toEqual({
      value: '1',
      status: { tone: 'danger', label: 'In the queue' },
    });
    // Nothing to flag (VeriFactu says «ok» with an empty queue): what it counts stays a note.
    expect(figureCard({ kind: 'stat', value: '0', label: 'In the queue', severity: 'ok' })).toEqual({
      value: '0',
      note: 'In the queue',
    });
  });

  it('is no figure when there is no data', () => {
    expect(figureCard({ kind: 'empty' })).toEqual({ value: null });
  });
});
