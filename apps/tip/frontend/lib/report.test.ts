// What the report says of each line (TIP-F13) — whose it is, its working day — and the CSV «Export» saves: the lines
// as on screen, amounts as plain numbers in the business's money, and a name a spreadsheet would run as a formula
// written as text.
import { describe, expect, it } from 'vitest';

import type { ReportOut, ReportRowOut } from '../operations';
import { lineName, reportCsv, reportFilename, shiftText } from './report';

const t = (key: string): string =>
  ({
    'tip.list.unassigned': 'Unassigned',
    'tip.report.outside': 'Outside a clocked working day',
    'tip.report.open': 'still open',
    'tip.report.columns.person': 'Person',
    'tip.report.columns.shift': 'Working day',
    'tip.report.columns.count': 'Tips',
    'tip.report.columns.card': 'By card',
    'tip.report.columns.cash': 'In cash',
    'tip.report.columns.other': 'Other ways',
    'tip.report.columns.total': 'Total',
  })[key] ?? key;

const SAY = { t, locale: 'es', zone: 'Europe/Madrid', money: { currency: 'EUR', decimals: 2 } };

const row = (fields: Partial<ReportRowOut> = {}): ReportRowOut => ({
  member_id: 'm-bea',
  member_name: 'Bea Gil',
  shift_id: null,
  clock_in_at: null,
  clock_out_at: null,
  card: 1000,
  cash: 250,
  other: 0,
  total: 1250,
  count: 3,
  ...fields,
});

const SHIFT = row({ shift_id: 's1', clock_in_at: '2026-11-25T08:00:00Z', clock_out_at: '2026-11-25T16:30:00Z' });

const report = (by: 'person' | 'shift', rows: ReportRowOut[]): ReportOut => ({
  by,
  date_from: '2026-11-19',
  date_to: '2026-11-25',
  shifts_available: true,
  rows,
  totals: { card: 0, cash: 0, other: 0, total: 0, count: 0 },
});

describe('a line of the report', () => {
  it('is named by its person; nobody’s is unassigned by person and outside a working day by shift', () => {
    expect(lineName(row(), 'person', t)).toBe('Bea Gil');
    expect(lineName(row({ member_id: null, member_name: '' }), 'person', t)).toBe('Unassigned');
    expect(lineName(row({ member_id: null, member_name: '' }), 'shift', t)).toBe('Outside a clocked working day');
  });

  it('says its working day on the business’s clock, from the clock-in to the clock-out or still open', () => {
    expect(shiftText(SHIFT, SAY)).toBe('25 nov 2026, 9:00 – 17:30');
    expect(shiftText({ ...SHIFT, clock_out_at: null }, SAY)).toBe('25 nov 2026, 9:00 – still open');
    expect(shiftText(row(), SAY)).toBe('—');
  });
});

describe('the CSV of the report', () => {
  it('by person: the columns on screen, the amounts as plain numbers', () => {
    expect(reportCsv(report('person', [row(), row({ member_id: null, member_name: '', card: 0, cash: 5, total: 5, count: 1 })]), SAY)).toBe(
      'Person,Tips,By card,In cash,Other ways,Total\r\nBea Gil,3,10.00,2.50,0.00,12.50\r\nUnassigned,1,0.00,0.05,0.00,0.05\r\n',
    );
  });

  it('by shift: the working day after the person, quoted when it holds a comma', () => {
    expect(reportCsv(report('shift', [SHIFT]), SAY)).toBe(
      'Person,Working day,Tips,By card,In cash,Other ways,Total\r\nBea Gil,"25 nov 2026, 9:00 – 17:30",3,10.00,2.50,0.00,12.50\r\n',
    );
  });

  it('writes the amounts with the decimals of the business’s money', () => {
    const yen = { ...SAY, money: { currency: 'JPY', decimals: 0 } };
    expect(reportCsv(report('person', [row({ card: 1500, cash: 0, total: 1500, count: 1 })]), yen).split('\r\n')[1]).toBe('Bea Gil,1,1500,0,0,1500');
  });

  it('a name a spreadsheet would run as a formula goes as text, and a quote is doubled', () => {
    const csv = reportCsv(report('person', [row({ member_name: '=HYPERLINK("x")' }), row({ member_name: '@Bea "B"' })]), SAY);
    expect(csv.split('\r\n').slice(1, 3)).toEqual([`"'=HYPERLINK(""x"")",3,10.00,2.50,0.00,12.50`, `"'@Bea ""B""",3,10.00,2.50,0.00,12.50`]);
  });

  it('is named after the view and the days it covers', () => {
    expect(reportFilename(report('person', []))).toBe('tips-by-person-2026-11-19_2026-11-25.csv');
    expect(reportFilename({ ...report('shift', []), date_from: '2026-11-25' })).toBe('tips-by-shift-2026-11-25.csv');
  });
});
