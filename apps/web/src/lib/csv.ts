// Utilidades CSV — export e import sin dependencias. CSP-safe.

function escapeCell(value: unknown): string {
  const s = value == null ? '' : String(value);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export interface CsvColumn<Row> {
  header: string;
  value: (row: Row) => unknown;
}

/** Construye una cadena CSV a partir de filas + columnas. */
export function toCsv<Row>(rows: Row[], columns: Array<CsvColumn<Row>>): string {
  const head = columns.map((c) => escapeCell(c.header)).join(',');
  const body = rows.map((row) => columns.map((c) => escapeCell(c.value(row))).join(',')).join('\r\n');
  return body ? `${head}\r\n${body}` : head;
}

/** Dispara la descarga de un CSV en el navegador (Blob + <a download>, con BOM UTF-8). */
export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([`﻿${csv}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Parser CSV tolerante (comillas, comas y saltos de línea entre comillas). */
export function parseCsv(text: string): { headers: string[]; rows: Array<Record<string, string>> } {
  const records: string[][] = [];
  let field = '';
  let record: string[] = [];
  let inQuotes = false;
  const src = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (inQuotes) {
      if (ch === '"') {
        if (src[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += ch;
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ',') {
      record.push(field); field = '';
    } else if (ch === '\n') {
      record.push(field); records.push(record); field = ''; record = [];
    } else field += ch;
  }
  if (field.length > 0 || record.length > 0) { record.push(field); records.push(record); }

  const nonEmpty = records.filter((r) => r.some((c) => c.trim() !== ''));
  if (nonEmpty.length === 0) return { headers: [], rows: [] };

  const headers = nonEmpty[0].map((h) => h.trim());
  const rows = nonEmpty.slice(1).map((r) => {
    const obj: Record<string, string> = {};
    headers.forEach((h, idx) => { obj[h] = (r[idx] ?? '').trim(); });
    return obj;
  });
  return { headers, rows };
}
