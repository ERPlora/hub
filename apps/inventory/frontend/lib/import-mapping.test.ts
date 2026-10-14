// The import's «which column is which» (WORKBOOK INVENTORY-F09/F10): each column of the file gets
// its field guessed from the header, in Spanish or English, with or without accents («Nombre»,
// «Código», «Precio», «IVA»…), the export's own headers included so a file exported re-imports
// unchanged; an unknown column is not imported; a field goes to one column only.
import { describe, expect, it } from 'vitest';

import {
  CATEGORY_IMPORT_ALIASES,
  guessMapping,
  mapRow,
  PRODUCT_IMPORT_ALIASES,
  PRODUCT_IMPORT_FIELDS,
  PRODUCT_IMPORT_REQUIRED,
} from './import-mapping';

describe('guessMapping (products)', () => {
  it('reads Spanish headers with accents and English ones', () => {
    expect(guessMapping(['Nombre', 'Código', 'Precio', 'IVA', 'Notas raras'], PRODUCT_IMPORT_ALIASES)).toEqual([
      'name',
      'sku',
      'price',
      'tax_category_key',
      '',
    ]);
    expect(guessMapping(['name', 'SKU', 'price', 'cost', 'qty', 'barcode', 'unit', 'VAT'], PRODUCT_IMPORT_ALIASES)).toEqual([
      'name',
      'sku',
      'price',
      'cost',
      'stock',
      'ean13',
      'unit',
      'tax_category_key',
    ]);
  });

  it("recognises the export's own headers in both languages (Activo / Active is not imported)", () => {
    const es = ['Nombre', 'SKU', 'Precio', 'Coste', 'Stock', 'Umbral', 'EAN-13', 'Descripción', 'Unidad', 'Categoría fiscal', 'Activo'];
    const en = ['Name', 'SKU', 'Price', 'Cost', 'Stock', 'Threshold', 'EAN-13', 'Description', 'Unit', 'Tax category', 'Active'];
    const fields = [...PRODUCT_IMPORT_FIELDS, ''];
    expect(guessMapping(es, PRODUCT_IMPORT_ALIASES)).toEqual(fields);
    expect(guessMapping(en, PRODUCT_IMPORT_ALIASES)).toEqual(fields);
  });

  it('gives a field to the first column only', () => {
    expect(guessMapping(['Nombre', 'Name'], PRODUCT_IMPORT_ALIASES)).toEqual(['name', '']);
  });

  it('name and SKU are the required columns', () => {
    expect(PRODUCT_IMPORT_REQUIRED).toEqual(['name', 'sku']);
  });
});

describe('guessMapping (categories)', () => {
  it('reads name, slug and the fiscal column', () => {
    expect(guessMapping(['Nombre', 'Slug', 'IVA', 'Productos'], CATEGORY_IMPORT_ALIASES)).toEqual(['name', 'slug', 'tax_category_key', '']);
    expect(guessMapping(['name', 'tax'], CATEGORY_IMPORT_ALIASES)).toEqual(['name', 'tax_category_key']);
  });
});

describe('mapRow', () => {
  it('keeps the cells of mapped columns under their field, and drops the rest', () => {
    expect(mapRow(['Coffee', 'x', 'CAF-1'], ['name', '', 'sku'])).toEqual({ name: 'Coffee', sku: 'CAF-1' });
  });
});
