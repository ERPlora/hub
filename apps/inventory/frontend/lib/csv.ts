// Reading the CSV a person imports (WORKBOOK INVENTORY-F09/F10). A stopgap until `@erplora/ui`
// ships a maintained parser (UI-REQUESTS.md: PapaParse): RFC 4180 quoting, the separator of the
// header line (a semicolon in Excel's Spanish CSV, else a comma), UTF-8 with or without BOM or
// Excel's Windows-1252. Each row keeps the line of the file it starts on, for the import report.

export interface CsvRow {
  /** Line of the file the row starts on (the header is line 1). */
  line: number;
  /** One cell per header, `''` where the row is short. */
  values: string[];
}

export interface CsvTable {
  headers: string[];
  rows: CsvRow[];
}

/** Windows-1252's 0x80–0x9F, where it parts from Latin-1 (the rest is the byte itself). */
const WINDOWS_1252_C1 = [
  0x20ac, 0x81, 0x201a, 0x192, 0x201e, 0x2026, 0x2020, 0x2021, 0x2c6, 0x2030, 0x160, 0x2039, 0x152, 0x8d, 0x17d, 0x8f,
  0x90, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014, 0x2dc, 0x2122, 0x161, 0x203a, 0x153, 0x9d, 0x17e, 0x178,
];

/** The file's bytes as text: strict UTF-8 first, else Excel's Windows-1252; never a BOM. */
export function decodeCsv(buffer: ArrayBuffer): string {
  let text: string;
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    text = Array.from(new Uint8Array(buffer), (byte) =>
      String.fromCharCode(byte >= 0x80 && byte <= 0x9f ? WINDOWS_1252_C1[byte - 0x80] : byte),
    ).join('');
  }
  return text.charCodeAt(0) === 0xfeff ? text.slice(1) : text;
}

/** The separator of the header line, outside quotes: the one used more, a comma on a tie. */
function separatorOf(text: string): string {
  let commas = 0;
  let semicolons = 0;
  let quoted = false;
  for (const char of text) {
    if (char === '"') quoted = !quoted;
    else if (!quoted && (char === '\n' || char === '\r')) break;
    else if (!quoted && char === ',') commas++;
    else if (!quoted && char === ';') semicolons++;
  }
  return semicolons > commas ? ';' : ',';
}

/** Every record of the file with the line it starts on. */
function records(text: string, separator: string): CsvRow[] {
  const out: CsvRow[] = [];
  let values: string[] = [];
  let cell = '';
  let quoted = false;
  let line = 1;
  let start = 1;
  const end = (): void => {
    values.push(cell);
    out.push({ line: start, values });
    values = [];
    cell = '';
  };
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (char === '"') quoted = false;
      else {
        if (char === '\n') line++;
        cell += char;
      }
    } else if (char === '"') quoted = true;
    else if (char === separator) {
      values.push(cell);
      cell = '';
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i++;
      end();
      line++;
      start = line;
    } else cell += char;
  }
  if (cell !== '' || values.length > 0) end();
  return out;
}

/** Headers and rows of a CSV; blank lines (every cell empty) are not rows. */
export function parseCsv(text: string): CsvTable {
  const all = records(text, separatorOf(text)).filter((record) => record.values.some((value) => value.trim() !== ''));
  const [head, ...rows] = all;
  if (!head) return { headers: [], rows: [] };
  const headers = head.values.map((value) => value.trim());
  return {
    headers,
    rows: rows.map((row) => ({ line: row.line, values: headers.map((_, index) => row.values[index] ?? '') })),
  };
}
