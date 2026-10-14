// «Import CSV» (CUSTOMER-F08): the file is read here, its headers matched to the card's fields and
// the rows sent in blocks of 50 (`customer.customer.import` takes one to fifty). Every rule about a
// row (name required, email, phone, stage…) is the server's: a row it skips comes back with its
// reason. Until `@erplora/ui` brings a CSV reader (UI-REQUESTS.md, papaparse), this one reads
// RFC 4180 and the semicolons and tabs spreadsheets write.
import type { ImportRowIn } from '../operations';
import { countryCode } from './countries';

/** The most rows `customer.customer.import` takes in one call. */
export const IMPORT_BLOCK = 50;

/** A row of the file, with its line number (the header is line 1) to name it in the report. */
export interface CsvRow {
  line: number;
  row: ImportRowIn;
}

type Field = keyof ImportRowIn;

/** Header (lower case, without accents) → field: the export's columns and a spreadsheet's names. */
const HEADERS: Record<string, Field> = {
  name: 'name',
  nombre: 'name',
  email: 'email',
  'e-mail': 'email',
  correo: 'email',
  phone: 'phone',
  telefono: 'phone',
  tel: 'phone',
  movil: 'phone',
  tax_id: 'tax_id',
  nif: 'tax_id',
  cif: 'tax_id',
  'nif/cif': 'tax_id',
  company_name: 'company_name',
  empresa: 'company_name',
  address: 'address',
  direccion: 'address',
  city: 'city',
  ciudad: 'city',
  postal_code: 'postal_code',
  cp: 'postal_code',
  'codigo postal': 'postal_code',
  country: 'country',
  pais: 'country',
  lifecycle_stage: 'lifecycle_stage',
  etapa: 'lifecycle_stage',
  notes: 'notes',
  notas: 'notes',
  source: 'source',
  origen: 'source',
  preferred_channel: 'preferred_channel',
  'canal preferido': 'preferred_channel',
  birthday: 'birthday',
  cumpleanos: 'birthday',
  anniversary: 'anniversary',
  aniversario: 'anniversary',
  avatar: 'avatar',
  foto: 'avatar',
};

const DELIMITERS = [',', ';', '\t'] as const;

function normalize(header: string): string {
  return header.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/\s+/g, ' ').trim();
}

/** The delimiter of the header line: the one it holds most of, outside quotes. */
function delimiterOf(text: string): string {
  const firstLine = text.split(/\r?\n/, 1)[0].replace(/"[^"]*"/g, '');
  let best: string = DELIMITERS[0];
  let most = -1;
  for (const delimiter of DELIMITERS) {
    const count = firstLine.split(delimiter).length - 1;
    if (count > most) {
      best = delimiter;
      most = count;
    }
  }
  return best;
}

interface CsvRecord {
  /** Line of the file where the record starts (1-based). */
  line: number;
  cells: string[];
}

/** The records of `text` with the line each starts on; blank ones are left out. */
function records(text: string): CsvRecord[] {
  const source = text.replace(/^\uFEFF/, '');
  const delimiter = delimiterOf(source);
  const out: CsvRecord[] = [];
  let cells: string[] = [];
  let cell = '';
  let quoted = false;
  let line = 1;
  let start = 1;
  const endCell = () => {
    cells.push(cell);
    cell = '';
  };
  const endRecord = () => {
    endCell();
    if (cells.some((c) => c.trim() !== '')) out.push({ line: start, cells });
    cells = [];
    start = line;
  };
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    if (char === '\n') line++;
    if (quoted) {
      if (char === '"' && source[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (char === '"') quoted = false;
      else cell += char;
    } else if (char === '"' && cell === '') quoted = true;
    else if (char === delimiter) endCell();
    else if (char === '\n') endRecord();
    else if (char !== '\r') cell += char;
  }
  if (cell !== '' || cells.length) endRecord();
  return out;
}

/** The cells of `text`, record by record (RFC 4180); blank lines are left out. */
export function parseCsv(text: string): string[][] {
  return records(text).map((record) => record.cells);
}

/** The rows of a customers CSV as the import's input; nothing when no column is known. */
export function rowsFromCsv(text: string): CsvRow[] {
  const [header, ...body] = records(text);
  if (!header) return [];
  const columns = header.cells.map((name) => HEADERS[normalize(name)]);
  if (!columns.some(Boolean)) return [];
  const out: CsvRow[] = [];
  for (const { line, cells } of body) {
    const row: ImportRowIn = {};
    let hasData = false;
    columns.forEach((field, column) => {
      if (!field || row[field] !== undefined) return;
      const value = (cells[column] ?? '').trim();
      if (value) hasData = true;
      row[field] = field === 'country' && value ? countryCode(value) || value : value;
    });
    if (hasData) out.push({ line, row });
  }
  return out;
}

/** `rows` in blocks of `IMPORT_BLOCK`. */
export function importBlocks<T>(rows: T[]): T[][] {
  const blocks: T[][] = [];
  for (let i = 0; i < rows.length; i += IMPORT_BLOCK) blocks.push(rows.slice(i, i + IMPORT_BLOCK));
  return blocks;
}
