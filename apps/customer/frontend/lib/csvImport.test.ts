// Reading a CSV of customers for «Import CSV» (CUSTOMER-F08): the file is read in the browser, its
// headers matched to the card's fields (the export's own columns plus the Spanish names a spreadsheet
// gives them) and sent in blocks of 50 rows; the server checks every row and says why it skips one.
import { describe, expect, it } from 'vitest';

import { IMPORT_BLOCK, importBlocks, parseCsv, rowsFromCsv } from './csvImport';

describe('parseCsv', () => {
  it('reads commas, quoted fields with commas, quotes and line breaks, and CRLF', () => {
    const text = 'name,notes\r\n"García, Ana","She said ""hi""\ntwice"\r\nLuis,\r\n';
    expect(parseCsv(text)).toEqual([
      ['name', 'notes'],
      ['García, Ana', 'She said "hi"\ntwice'],
      ['Luis', ''],
    ]);
  });

  it('reads the semicolons a Spanish spreadsheet writes, and tabs', () => {
    expect(parseCsv('Nombre;Teléfono\nAna;600 111 222\n')).toEqual([
      ['Nombre', 'Teléfono'],
      ['Ana', '600 111 222'],
    ]);
    expect(parseCsv('name\tphone\nAna\t600\n')).toEqual([
      ['name', 'phone'],
      ['Ana', '600'],
    ]);
  });

  it('drops a byte-order mark and blank lines', () => {
    expect(parseCsv('﻿name\n\nAna\n   \n')).toEqual([['name'], ['Ana']]);
  });
});

describe('rowsFromCsv', () => {
  it('maps the export columns to the card fields, line by line (line 1 is the header)', () => {
    const csv = 'name,email,phone,tax_id,company_name,lifecycle_stage,total_spent\nAna,ana@x.es,600111222,X1,ACME,vip,12.00\n';
    expect(rowsFromCsv(csv)).toEqual([
      {
        line: 2,
        row: { name: 'Ana', email: 'ana@x.es', phone: '600111222', tax_id: 'X1', company_name: 'ACME', lifecycle_stage: 'vip' },
      },
    ]);
  });

  it('understands the Spanish headers of a spreadsheet, without caring about case or accents', () => {
    const csv =
      'Nombre;Correo;Tel;NIF;Empresa;Dirección;Ciudad;CP;País;Etapa;Notas\nAna;a@x.es;600;X;ACME;Calle 1;Madrid;28001;España;active;VIP\n';
    expect(rowsFromCsv(csv)[0].row).toEqual({
      name: 'Ana',
      email: 'a@x.es',
      phone: '600',
      tax_id: 'X',
      company_name: 'ACME',
      address: 'Calle 1',
      city: 'Madrid',
      postal_code: '28001',
      country: 'ES',
      lifecycle_stage: 'active',
      notes: 'VIP',
    });
    expect(rowsFromCsv('Teléfono,Código postal,CIF\n1,2,3\n')[0].row).toEqual({ phone: '1', postal_code: '2', tax_id: '3' });
  });

  it('also reads source, preferred channel, birthday, anniversary and avatar', () => {
    const csv = 'name,source,preferred_channel,birthday,anniversary,avatar\nAna,referral,email,1990-01-02,2010-05-06,https://x/a.png\n';
    expect(rowsFromCsv(csv)[0].row).toEqual({
      name: 'Ana',
      source: 'referral',
      preferred_channel: 'email',
      birthday: '1990-01-02',
      anniversary: '2010-05-06',
      avatar: 'https://x/a.png',
    });
  });

  it('turns a country name into its code; a text that names no country goes as written (the server warns)', () => {
    const rows = rowsFromCsv('name,country\nAna,Francia\nLuis,fr\nEva,Narnia\n');
    expect(rows.map((r) => r.row.country)).toEqual(['FR', 'FR', 'Narnia']);
  });

  it('keeps a row without a name (the server skips it with its reason) and drops a line with nothing', () => {
    const rows = rowsFromCsv('name,email\n,a@x.es\n,\nLuis,\n');
    expect(rows).toEqual([
      { line: 2, row: { name: '', email: 'a@x.es' } },
      { line: 4, row: { name: 'Luis', email: '' } },
    ]);
  });

  it('a file with no known column gives no rows', () => {
    expect(rowsFromCsv('foo,bar\n1,2\n')).toEqual([]);
    expect(rowsFromCsv('')).toEqual([]);
  });
});

describe('importBlocks', () => {
  it('cuts the rows in blocks of at most 50, the most the server takes at once', () => {
    expect(IMPORT_BLOCK).toBe(50);
    const rows = Array.from({ length: 120 }, (_, i) => ({ line: i + 2, row: { name: `C${i}` } }));
    expect(importBlocks(rows).map((b) => b.length)).toEqual([50, 50, 20]);
    expect(importBlocks([])).toEqual([]);
  });
});
