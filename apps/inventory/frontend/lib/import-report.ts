// The import's bookkeeping (WORKBOOK INVENTORY-F09/F10): the server takes at most 100 rows per call
// (schemas.MAX_BATCH), so the page cuts the file and adds the reports up into one «Import result»,
// together with the rows the page failed itself before sending them (a SKU repeated across calls).
import type { OutputOf } from '@erplora/ui/sdk';

/** Rows of one `bulk_create` call. */
export const BATCH = 100;

export interface FailedRow {
  line: number;
  key: string;
  reason: string;
}

export interface ImportReport {
  total: number;
  /** Rows a rehearsal found ready. */
  ready: number;
  created: number;
  skipped: number;
  /** In file order. */
  failed: FailedRow[];
  /** «Stop» was pressed halfway. */
  cancelled: boolean;
  /** What else the person must know (Taxes could not save a text…). */
  notes: string[];
}

type ServerReport = OutputOf<'inventory.product.bulk_create'>;

export function chunk<T>(items: readonly T[], size = BATCH): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

export function emptyReport(): ImportReport {
  return { total: 0, ready: 0, created: 0, skipped: 0, failed: [], cancelled: false, notes: [] };
}

const byLine = (a: FailedRow, b: FailedRow): number => a.line - b.line;

/** The report with one more call of the server added. */
export function addReport(report: ImportReport, out: ServerReport): ImportReport {
  const failed = out.rows.filter((row) => row.status === 'failed').map((row) => ({ line: row.line, key: row.key, reason: row.reason }));
  return {
    ...report,
    total: report.total + out.total,
    ready: report.ready + out.ready,
    created: report.created + out.created,
    skipped: report.skipped + out.skipped,
    failed: [...report.failed, ...failed].sort(byLine),
  };
}

/** The report with rows the page failed itself (never sent), counted as rows of the file. */
export function failRows(report: ImportReport, rows: readonly FailedRow[]): ImportReport {
  return { ...report, total: report.total + rows.length, failed: [...report.failed, ...rows].sort(byLine) };
}

/** The report as text to copy: the counts, then «Line N · key — reason» per failed row. */
export function reportText(report: ImportReport, t: (key: string, named?: Record<string, unknown>) => string): string {
  return [
    ...report.notes,
    `${t('inventory.import.rows')}: ${report.total}`,
    `${t('inventory.import.created')}: ${report.created}`,
    `${t('inventory.import.skipped')}: ${report.skipped}`,
    `${t('inventory.import.failed')}: ${report.failed.length}`,
    ...report.failed.map((row) => t('inventory.import.failedLine', { line: row.line, key: row.key || '—', reason: row.reason })),
  ].join('\n');
}
