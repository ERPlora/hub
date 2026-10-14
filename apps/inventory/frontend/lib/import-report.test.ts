// The import's bookkeeping (WORKBOOK INVENTORY-F09/F10): the file goes to the server in calls of
// at most 100 rows, and their reports add up to one «Import result»: rows, created, skipped (already
// existed), failed (each with its line and reason, in file order), plus the rows the page itself
// failed before sending them (a SKU repeated across calls). The report can be copied as text.
import { describe, expect, it } from 'vitest';

import { addReport, chunk, emptyReport, failRows, reportText } from './import-report';

const out = (rows: Array<[number, string, 'created' | 'skipped' | 'failed' | 'ready', string?]>) => ({
  dry_run: false,
  total: rows.length,
  ready: rows.filter((r) => r[2] === 'ready').length,
  created: rows.filter((r) => r[2] === 'created').length,
  skipped: rows.filter((r) => r[2] === 'skipped').length,
  failed: rows.filter((r) => r[2] === 'failed').length,
  rows: rows.map(([line, key, status, reason = '']) => ({ line, key, status, id: null, reason })),
});

describe('chunk', () => {
  it('cuts the rows into calls of at most 100, in order', () => {
    const rows = Array.from({ length: 250 }, (_, i) => i);
    expect(chunk(rows).map((part) => [part.length, part[0]])).toEqual([
      [100, 0],
      [100, 100],
      [50, 200],
    ]);
    expect(chunk([])).toEqual([]);
  });
});

describe('addReport / failRows', () => {
  it('adds up the calls, failures in file order', () => {
    let report = emptyReport();
    report = addReport(report, out([[2, 'A', 'created'], [3, 'B', 'failed', 'Price is not a number']]));
    report = failRows(report, [{ line: 5, key: 'A', reason: 'SKU repeated in the file' }]);
    report = addReport(report, out([[4, 'C', 'skipped'], [6, 'D', 'ready']]));
    expect(report).toEqual({
      total: 5,
      ready: 1,
      created: 1,
      skipped: 1,
      failed: [
        { line: 3, key: 'B', reason: 'Price is not a number' },
        { line: 5, key: 'A', reason: 'SKU repeated in the file' },
      ],
      cancelled: false,
      notes: [],
    });
  });
});

describe('reportText', () => {
  it('copies the counts and one line per failed row', () => {
    const report = failRows({ ...emptyReport(), total: 2, created: 2 }, [{ line: 4, key: '', reason: 'Name or SKU missing' }]);
    const t = (key: string, named?: Record<string, unknown>) => `${key}${named ? JSON.stringify(named) : ''}`;
    expect(reportText(report, t)).toBe(
      [
        'inventory.import.rows: 3',
        'inventory.import.created: 2',
        'inventory.import.skipped: 0',
        'inventory.import.failed: 1',
        'inventory.import.failedLine{"line":4,"key":"—","reason":"Name or SKU missing"}',
      ].join('\n'),
    );
  });
});
