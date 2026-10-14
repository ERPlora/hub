// «Import CSV» (CUSTOMER-F08): reads the file (UTF-8, or the Windows-1252 of Excel), sends its rows in blocks of 50 to
// `customer.customer.import` one after the other and builds the summary: created, every skipped row
// with the server's reasons, the rows to review (a country it could not read) and any block the
// server refused (the next blocks still go: the ones already sent stay created). Every rule about a
// row is the server's; the live list and figures show the new cards by themselves.
import { useCommand } from '@erplora/ui/sdk';
import { ref, shallowRef } from 'vue';

import { type CsvRow, importBlocks, rowsFromCsv } from './csvImport';

export interface ImportLine {
  /** Line of the file (the header is line 1). */
  line: number;
  reasons: string[];
}

export interface ImportReport {
  total: number;
  created: number;
  skipped: ImportLine[];
  warnings: ImportLine[];
  /** Blocks the server refused, by their first and last line. */
  failed: { from: number; to: number; reason: string }[];
}

/** Why there is nothing to import: no customer in the file, or the file could not be read. */
export type ImportProblem = 'noRows' | 'unreadable';

/**
 * The file's text. UTF-8 when it is (with or without its byte-order mark); else Windows-1252, what
 * Excel writes on Windows («Teléfono», «García» would otherwise arrive broken and the column unread).
 */
export function decode(buffer: ArrayBuffer): string {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    return new TextDecoder('windows-1252').decode(buffer);
  }
}

export function useCustomerImport() {
  const { run } = useCommand('customer.customer.import');
  const importing = ref(false);
  const report = shallowRef<ImportReport | null>(null);
  const problem = ref<ImportProblem | null>(null);

  async function readRows(file: File): Promise<CsvRow[] | null> {
    try {
      return rowsFromCsv(decode(await file.arrayBuffer()));
    } catch {
      problem.value = 'unreadable';
      return null;
    }
  }

  async function importFile(file: File): Promise<void> {
    report.value = null;
    problem.value = null;
    const rows = await readRows(file);
    if (!rows) return;
    if (rows.length === 0) {
      problem.value = 'noRows';
      return;
    }
    const out: ImportReport = { total: rows.length, created: 0, skipped: [], warnings: [], failed: [] };
    importing.value = true;
    try {
      for (const block of importBlocks(rows)) {
        try {
          const answer = await run({ rows: block.map((r) => r.row) });
          out.created += answer.created;
          for (const result of answer.rows) {
            const line = block[result.index]?.line ?? result.index + 2;
            const errors = Object.values(result.errors);
            const warnings = Object.values(result.warnings);
            if (errors.length) out.skipped.push({ line, reasons: errors });
            if (warnings.length) out.warnings.push({ line, reasons: warnings });
          }
        } catch (error) {
          out.failed.push({
            from: block[0].line,
            to: block[block.length - 1].line,
            reason: error instanceof Error ? error.message : String(error),
          });
        }
      }
    } finally {
      importing.value = false;
      report.value = out;
    }
  }

  function dismiss(): void {
    report.value = null;
    problem.value = null;
  }

  return { importing, report, problem, importFile, dismiss };
}
