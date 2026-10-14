// Reading a CSV the way it really arrives (WORKBOOK INVENTORY-F09/F10): header on the first line,
// separated by commas or by semicolons (Excel in Spanish), quoted cells with commas, quotes and line
// breaks inside, UTF-8 with or without BOM or Excel's Windows-1252; each row keeps the line of the
// file it starts on, for the report. Blank lines are not rows.
import { describe, expect, it } from 'vitest';

import { decodeCsv, parseCsv } from './csv';

const bytes = (...values: number[]): ArrayBuffer => new Uint8Array(values).buffer;

describe('parseCsv', () => {
  it('reads a comma file: headers, then each row with its line', () => {
    expect(parseCsv('name,sku,price\nCoffee,CAF-1,"2,20"\nTea,TEA-1,1.80\n')).toEqual({
      headers: ['name', 'sku', 'price'],
      rows: [
        { line: 2, values: ['Coffee', 'CAF-1', '2,20'] },
        { line: 3, values: ['Tea', 'TEA-1', '1.80'] },
      ],
    });
  });

  it('reads the semicolon file of Excel in Spanish, CRLF included', () => {
    expect(parseCsv('Nombre;Código;Precio\r\nCafé;CAF-1;2,20\r\n')).toEqual({
      headers: ['Nombre', 'Código', 'Precio'],
      rows: [{ line: 2, values: ['Café', 'CAF-1', '2,20'] }],
    });
  });

  it('keeps quotes, separators and line breaks inside a quoted cell; the next row keeps its own line', () => {
    const table = parseCsv('name;description\n"Wine ""Rioja""";"Red; oak\naged"\nWater;Still\n');
    expect(table.rows).toEqual([
      { line: 2, values: ['Wine "Rioja"', 'Red; oak\naged'] },
      { line: 4, values: ['Water', 'Still'] },
    ]);
  });

  it('skips blank lines and fills a short row with empty cells', () => {
    expect(parseCsv('a,b\n\n1\n,\n2,3').rows).toEqual([
      { line: 3, values: ['1', ''] },
      { line: 5, values: ['2', '3'] },
    ]);
  });

  it('an empty file has no headers and no rows', () => {
    expect(parseCsv('')).toEqual({ headers: [], rows: [] });
  });
});

describe('decodeCsv', () => {
  it('reads UTF-8 and drops its BOM', () => {
    expect(decodeCsv(bytes(0xef, 0xbb, 0xbf, 0x43, 0x61, 0x66, 0xc3, 0xa9))).toBe('Café');
  });

  it("reads Excel's Windows-1252 when the bytes are not UTF-8 (the euro sign included)", () => {
    expect(decodeCsv(bytes(0x43, 0x61, 0x66, 0xe9, 0x20, 0x80))).toBe('Café €');
  });
});
