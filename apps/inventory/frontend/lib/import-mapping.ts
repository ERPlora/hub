// The import's «which column is which» (WORKBOOK INVENTORY-F09/F10): the market's mapping step
// (Odoo, WooCommerce, Lightspeed, Square). Each header is matched, in Spanish or English and without
// caring for accents, case or separators, against the names a field is known by, the export's own
// headers included (so an exported file re-imports unchanged). `''` = do not import that column.

export const PRODUCT_IMPORT_FIELDS = [
  'name',
  'sku',
  'price',
  'cost',
  'stock',
  'low_stock_threshold',
  'ean13',
  'description',
  'unit',
  'tax_category_key',
] as const;
export type ProductImportField = (typeof PRODUCT_IMPORT_FIELDS)[number];

/** Without them no product can be created (as Lightspeed and WooCommerce require). */
export const PRODUCT_IMPORT_REQUIRED: readonly ProductImportField[] = ['name', 'sku'];

const TAX_HEADERS = [
  'tax category',
  'tax category key',
  'tax_category_key',
  'category tax',
  'fiscal category',
  'tax',
  'iva',
  'vat',
  'impuesto',
  'tax class',
  'categoria fiscal',
  'tipo de iva',
];

export const PRODUCT_IMPORT_ALIASES: Readonly<Record<ProductImportField, readonly string[]>> = {
  name: ['name', 'nombre', 'producto', 'product', 'articulo', 'item', 'titulo'],
  sku: ['sku', 'codigo', 'code', 'referencia', 'ref', 'reference', 'cod'],
  price: ['price', 'precio', 'pvp', 'precio venta', 'sale price', 'precio de venta'],
  cost: ['cost', 'coste', 'costo', 'precio coste', 'purchase price', 'precio de compra'],
  stock: ['stock', 'existencias', 'cantidad', 'qty', 'quantity', 'unidades'],
  low_stock_threshold: ['threshold', 'umbral', 'low stock threshold', 'umbral stock bajo', 'minimo', 'stock minimo', 'min stock', 'reorder point'],
  ean13: ['ean13', 'ean 13', 'ean', 'barcode', 'codigo de barras', 'codigo barras', 'gtin'],
  description: ['description', 'descripcion', 'detalle', 'notas'],
  unit: ['unit', 'unidad', 'unit code', 'unidad de medida', 'medida', 'uom'],
  tax_category_key: TAX_HEADERS,
};

export const CATEGORY_IMPORT_FIELDS = ['name', 'slug', 'tax_category_key'] as const;
export type CategoryImportField = (typeof CATEGORY_IMPORT_FIELDS)[number];

export const CATEGORY_IMPORT_ALIASES: Readonly<Record<CategoryImportField, readonly string[]>> = {
  name: ['name', 'nombre', 'categoria', 'category'],
  slug: ['slug'],
  tax_category_key: TAX_HEADERS,
};

/** Lowercase, without accents and with single spaces: «Código» and «codigo» are the same header. */
export function normalizeHeader(header: string): string {
  return header
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, ' ');
}

/** The field each column goes to, by its header; a field goes to the first column that names it. */
export function guessMapping<F extends string>(headers: readonly string[], aliases: Readonly<Record<F, readonly string[]>>): (F | '')[] {
  const taken = new Set<F>();
  const fields = Object.keys(aliases) as F[];
  return headers.map((header) => {
    const wanted = normalizeHeader(header);
    const field = fields.find((f) => !taken.has(f) && aliases[f].some((alias) => normalizeHeader(alias) === wanted));
    if (!field) return '';
    taken.add(field);
    return field;
  });
}

/** A row's cells under the fields their columns go to; columns not imported are dropped. */
export function mapRow<F extends string>(values: readonly string[], mapping: readonly (F | '')[]): Partial<Record<F, string>> {
  const out: Partial<Record<F, string>> = {};
  mapping.forEach((field, index) => {
    if (field) out[field] = values[index] ?? '';
  });
  return out;
}
