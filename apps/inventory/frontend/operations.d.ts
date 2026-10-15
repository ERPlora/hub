// Types of the inventory app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`),
// from apps/inventory/schemas.py. Written by hand, as `frontend/sdk-types.d.ts` is for the PoC,
// until V3 generates them from `/api/openapi.json`. Keep it in step with schemas.py and with
// `frontend/generated/operations.json`. One input per operation (ninja's parity): no path
// parameters, a product or a category travels in the input. Money is whole cents; quantities and
// other decimals are JSON strings on the way out («2.500») and a number or its string on the way in.
import type { Page } from '../../../frontend/sdk-types';

export type UnitCode = 'ud' | 'kg' | 'g' | 't' | 'l' | 'ml' | 'min' | 'h';
export type ProductType = 'physical' | 'service';
export type MovementType = 'initial' | 'reception' | 'sale' | 'void' | 'count' | 'write_off' | 'refund';
export type ProductStatus = 'active' | 'inactive' | 'needs_tax_setup';
export type ImportStatus = 'ready' | 'created' | 'skipped' | 'failed';

/** A `Decimal` on the way in: a number or its string («2.5»). */
export type DecimalIn = number | string;

type Sorted<K extends string> = K | `-${K}`;

interface PageIn {
  limit?: number;
  offset?: number;
}

// ── Inputs: lists ──────────────────────────────────────────────────────────────────────────────

export interface ProductFiltersIn {
  search?: string;
  name?: string;
  sku?: string;
  price_min?: number;
  price_max?: number;
  stock_min?: DecimalIn;
  stock_max?: DecimalIn;
  status?: ProductStatus;
  is_active?: boolean;
  needs_tax_setup?: boolean;
  tracks_stock?: boolean;
  category_id?: string;
  category?: string;
  product_type?: ProductType;
  sort?: Sorted<'name' | 'sku' | 'price' | 'stock' | 'created_at'>;
}

export interface ProductListIn extends PageIn, ProductFiltersIn {}

export interface LowStockListIn extends PageIn {
  search?: string;
  sku?: string;
  stock_min?: DecimalIn;
  stock_max?: DecimalIn;
  sort?: Sorted<'name' | 'sku' | 'stock' | 'low_stock_threshold'>;
}

export interface ForSaleListIn extends PageIn {
  search?: string;
}

export interface ProductCategoryListIn extends PageIn {
  search?: string;
  product_id?: string;
  category_id?: string;
}

export interface CategoryFiltersIn {
  search?: string;
  name?: string;
  slug?: string;
  icon?: string;
  color?: string;
  product_count_min?: number;
  product_count_max?: number;
  sort?: Sorted<'name' | 'slug' | 'icon' | 'color' | 'product_count'>;
}

export interface CategoryListIn extends PageIn, CategoryFiltersIn {}

export interface MovementListIn extends PageIn {
  search?: string;
  movement_type?: MovementType;
  reference?: string;
  product_id?: string;
  created_from?: string;
  created_to?: string;
  sort?: Sorted<'created_at' | 'movement_type' | 'qty' | 'stock_after'>;
}

export interface UnitListIn extends PageIn {
  search?: string;
}

// ── Inputs: products and categories ───────────────────────────────────────────────────────────

/** A product by its id or, as a person says it, by its SKU or name. */
export interface ProductRefIn {
  id?: string;
  product?: string;
}

export interface ProductIn {
  name: string;
  sku: string;
  price: number;
  tax_category_key: string;
  cost?: number;
  initial_stock?: DecimalIn;
  /** `null` takes the business's default from the settings. */
  low_stock_threshold?: DecimalIn | null;
  ean13?: string | null;
  description?: string;
  product_type?: ProductType;
  unit?: UnitCode;
  price_quantity?: DecimalIn;
  pricing_unit?: UnitCode | null;
  /** `null` follows the business's setting. */
  track_stock?: boolean | null;
  category_ids?: string[];
}

/** Only the fields sent change; the SKU, the type and the stock are not editable. */
export interface ProductPatchIn extends ProductRefIn {
  name?: string;
  price?: number;
  cost?: number;
  low_stock_threshold?: DecimalIn;
  /** An empty text removes it. */
  ean13?: string;
  description?: string;
  tax_category_key?: string;
  is_active?: boolean;
  unit?: UnitCode;
  price_quantity?: DecimalIn;
  pricing_unit?: UnitCode;
  track_stock?: boolean;
  /** All of its categories: replaces the ones it had. */
  category_ids?: string[];
}

/** One CSV row, its columns mapped to our fields, each cell as written in the file. */
export interface ProductImportRowIn {
  line: number;
  name?: string;
  sku?: string;
  price?: string;
  cost?: string;
  stock?: string;
  low_stock_threshold?: string;
  ean13?: string;
  description?: string;
  unit?: string;
  tax_category_key?: string;
}

export interface ProductImportIn {
  rows: ProductImportRowIn[];
  dry_run?: boolean;
}

export interface ProductCategoryIn {
  product_id?: string;
  product?: string;
  category_id?: string;
  category?: string;
}

export interface CategoryRefIn {
  id?: string;
  category?: string;
}

export interface CategoryIn {
  name: string;
  slug?: string;
  description?: string;
  icon?: string;
  color?: string;
  order?: number;
  tax_category_key?: string | null;
}

/** Only the fields sent change; `tax_category_key: ""` clears it. */
export interface CategoryPatchIn extends CategoryRefIn {
  name?: string;
  slug?: string;
  description?: string;
  icon?: string;
  color?: string;
  order?: number;
  tax_category_key?: string;
}

export interface CategoryImportRowIn {
  line: number;
  name?: string;
  slug?: string;
  /** The file's fiscal text: a tax category's key, name or learned alias. */
  tax_category_key?: string;
}

export interface CategoryImportIn {
  rows: CategoryImportRowIn[];
}

// ── Inputs: stock and settings ─────────────────────────────────────────────────────────────────

export interface ReceiveLineIn {
  product_id?: string;
  product?: string;
  qty: DecimalIn;
  /** `null` keeps the cost the product had. */
  unit_cost?: number | null;
}

export interface ReceiveIn {
  items: ReceiveLineIn[];
  reference?: string;
}

export interface CountIn {
  product_id?: string;
  product?: string;
  stock: DecimalIn;
  reason: string;
}

export interface WriteOffIn {
  product_id?: string;
  product?: string;
  qty: DecimalIn;
  reason: string;
}

export interface ConfigPatchIn {
  allow_sell_without_stock?: boolean;
  low_stock_threshold?: number;
  track_stock?: boolean;
}

// ── Outputs ───────────────────────────────────────────────────────────────────────────────────

export interface ProductOut {
  id: string;
  name: string;
  sku: string;
  ean13: string | null;
  description: string;
  product_type: ProductType;
  /** Cents, per `price_quantity` of `pricing_unit`. */
  price: number;
  cost: number;
  stock: string;
  low_stock_threshold: string;
  unit: UnitCode;
  price_quantity: string;
  pricing_unit: UnitCode;
  tax_category_id: string | null;
  tax_category_key: string | null;
  needs_tax_setup: boolean;
  /** Its own decision; `null` follows the business. */
  track_stock: boolean | null;
  /** Whether stock control applies to it now. */
  tracks_stock: boolean;
  is_active: boolean;
  category_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ProductsOut {
  rows: ProductOut[];
}

export interface SaleProductOut {
  id: string;
  name: string;
  sku: string;
  product_type: ProductType;
  price: number;
  cost: number;
  tax_category_id: string | null;
  tax_category_key: string | null;
  needs_tax_setup: boolean;
  unit: UnitCode;
  price_quantity: string;
  pricing_unit: UnitCode;
  tracks_stock: boolean;
}

export interface LowStockOut {
  id: string;
  name: string;
  sku: string;
  stock: string;
  low_stock_threshold: string;
  unit: UnitCode;
  price_quantity: string;
  pricing_unit: UnitCode;
}

export interface ProductCategoryOut {
  product_id: string;
  category_id: string;
}

export interface ProductCategoryLinkOut extends ProductCategoryOut {
  changed: boolean;
}

export interface CategoryOut {
  id: string;
  name: string;
  slug: string;
  description: string;
  icon: string;
  color: string;
  order: number;
  tax_category_id: string | null;
  tax_category_key: string | null;
  /** Active products in it. */
  product_count: number;
}

export interface MovementOut {
  id: string;
  product_id: string;
  product_name: string;
  sku: string;
  movement_type: MovementType;
  /** What the balance changed by, with its sign. */
  qty: string;
  stock_after: string;
  reason: string;
  reference: string;
  unit_cost: number | null;
  actor: string;
  created_at: string;
}

export interface SummaryOut {
  products_tracked: number;
  products_in_stock: number;
  products_out_of_stock: number;
  products_low_stock: number;
  products_without_cost: number;
  /** Σ cost × stock of the ones in stock, in cents. */
  stock_value: number;
  active_products: number;
}

export interface UnitOut {
  code: UnitCode;
  name: string;
  category: string;
  factor_num: number;
  factor_den: number;
  /** The step every quantity in this unit is a multiple of. */
  increment: string;
  is_reference: boolean;
}

export interface ConfigOut {
  allow_sell_without_stock: boolean;
  low_stock_threshold: number;
  track_stock: boolean;
}

export interface ImportRowOut {
  line: number;
  key: string;
  status: ImportStatus;
  id: string | null;
  reason: string;
}

export interface ImportReportOut {
  dry_run: boolean;
  total: number;
  ready: number;
  created: number;
  skipped: number;
  failed: number;
  rows: ImportRowOut[];
}

export interface ExportOut {
  filename: string;
  content_type: string;
  content: string;
}

export interface DeletedOut {
  id: string;
}

type NoInput = Record<string, never>;

declare module '@erplora/ui/sdk' {
  interface Operations {
    'inventory.product.list': { input: ProductListIn; output: Page<ProductOut> };
    'inventory.product.get': { input: ProductRefIn; output: ProductOut };
    'inventory.product.list_for_sale': { input: ForSaleListIn; output: Page<SaleProductOut> };
    'inventory.product.list_low_stock': { input: LowStockListIn; output: Page<LowStockOut> };
    'inventory.product.export': { input: ProductFiltersIn; output: ExportOut };
    'inventory.product.create': { input: ProductIn; output: ProductOut };
    'inventory.product.bulk_create': { input: ProductImportIn; output: ImportReportOut };
    'inventory.product.update': { input: ProductPatchIn; output: ProductOut };
    'inventory.product.delete': { input: ProductRefIn; output: DeletedOut };
    'inventory.product_category.list': { input: ProductCategoryListIn; output: Page<ProductCategoryOut> };
    'inventory.product_category.add': { input: ProductCategoryIn; output: ProductCategoryLinkOut };
    'inventory.product_category.remove': { input: ProductCategoryIn; output: ProductCategoryLinkOut };
    'inventory.category.list': { input: CategoryListIn; output: Page<CategoryOut> };
    'inventory.category.export': { input: CategoryFiltersIn; output: ExportOut };
    'inventory.category.create': { input: CategoryIn; output: CategoryOut };
    'inventory.category.bulk_create': { input: CategoryImportIn; output: ImportReportOut };
    'inventory.category.update': { input: CategoryPatchIn; output: CategoryOut };
    'inventory.category.delete': { input: CategoryRefIn; output: DeletedOut };
    'inventory.movement.list': { input: MovementListIn; output: Page<MovementOut> };
    'inventory.stock.get_summary': { input: NoInput; output: SummaryOut };
    'inventory.stock.receive': { input: ReceiveIn; output: ProductsOut };
    'inventory.stock.count': { input: CountIn; output: ProductOut };
    'inventory.stock.write_off': { input: WriteOffIn; output: ProductOut };
    'inventory.unit.list': { input: UnitListIn; output: Page<UnitOut> };
    'inventory.config.get': { input: NoInput; output: ConfigOut };
    'inventory.config.update': { input: ConfigPatchIn; output: ConfigOut };
  }
}
