// Types of the combo app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/combo/schemas.py. Written by hand, as the other apps' are, until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and with `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, ids travel in the input. Money is in
// cents; moments are ISO date-times.
import type { CatalogImage } from '../../../base/frontend/operations';
import type { Page } from '../../../frontend/sdk-types';

export type SupplyKind = 'service' | 'goods';
export type SortDir = 'asc' | 'desc';
export type ComboSort = 'sort_order' | 'name' | 'price' | 'supply_kind' | 'is_active' | 'id';
/** offered; sold_out (marked here); product_inactive, product_sold_out, product_deleted or not_by_unit (in Inventory); untaxed
 *  (no VAT category to bill it at to take away). */
export type OptionStatus = 'offered' | 'sold_out' | 'product_inactive' | 'product_sold_out' | 'product_deleted' | 'not_by_unit' | 'untaxed';

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A menu by id, or by its name. */
export interface ComboRefIn {
  id?: string | null;
  combo?: string | null;
}

/** COMBO-F14: `catalog:<folder>/<name>` of the shared library, or `''` for none (a `file:` is refused). */
export interface ComboImageIn extends ComboRefIn {
  image: string;
}

/** COMBO-F14: a JPG, PNG or WebP of 2 MB at most, in base64; kept as a 512 × 512 WebP. */
export interface ComboImageUploadIn extends ComboRefIn {
  data_base64: string;
}

export interface ComboImageSuggestIn extends ComboRefIn {
  /** 1 to 20; 5 by default. */
  limit?: number;
}

/** COMBO-F14: the library's best images for the menu's name, titled in the business's language. */
export interface ComboImageSuggestOut {
  combo_id: string;
  query: string;
  rows: CatalogImage[];
}

export interface ComboListIn extends PageIn {
  search?: string;
  name?: string;
  supply_kind?: SupplyKind;
  is_active?: boolean;
  sort?: ComboSort;
  dir?: SortDir;
}

export interface ComboIn {
  name: string;
  kitchen_name?: string;
  price?: number;
  supply_kind?: SupplyKind;
  tax_category_key?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

/** Only the fields sent change. */
export interface ComboPatchIn extends ComboRefIn {
  name?: string;
  kitchen_name?: string;
  price?: number;
  supply_kind?: SupplyKind;
  tax_category_key?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

interface ComboOfIn {
  combo_id?: string | null;
  combo?: string | null;
}

interface GroupOfIn extends ComboOfIn {
  group_id?: string | null;
  group?: string | null;
}

export interface GroupRefIn extends ComboOfIn {
  id?: string | null;
  group?: string | null;
}

export interface GroupIn extends ComboOfIn {
  name: string;
  min_choices?: number;
  max_choices?: number;
  allow_repeat?: boolean;
}

export interface GroupPatchIn extends GroupRefIn {
  name?: string;
  min_choices?: number;
  max_choices?: number;
  allow_repeat?: boolean;
}

export interface GroupReorderIn extends ComboRefIn {
  group_ids: string[];
}

export interface OptionRefIn extends GroupOfIn {
  id?: string | null;
  product?: string | null;
}

export interface OptionIn extends GroupOfIn {
  product_id?: string | null;
  product?: string | null;
  price_delta?: number;
  is_available?: boolean;
}

export interface OptionBulkIn extends GroupOfIn {
  product_ids: string[];
}

export interface OptionPatchIn extends OptionRefIn {
  new_product_id?: string | null;
  new_product?: string | null;
  price_delta?: number;
  is_available?: boolean;
}

export interface OptionReorderIn extends GroupOfIn {
  option_ids: string[];
}

export interface ForSaleIn extends PageIn {
  search?: string;
}

export interface ChoiceIn {
  option_id?: string | null;
  product?: string | null;
  group?: string | null;
  quantity?: number;
}

/** Ventas' order channel: dine_in is billed as eaten in, takeaway and delivery as to take away. */
export type Channel = 'dine_in' | 'takeaway' | 'delivery';

export interface ResolveIn extends ComboRefIn {
  choices?: ChoiceIn[];
  amount?: number | null;
  channel?: Channel | null;
}

export interface OptionOut {
  id: string;
  group_id: string;
  product_id: string;
  product_name: string;
  sku: string;
  catalog_price: number;
  price_delta: number;
  is_available: boolean;
  sort_order: number;
  status: OptionStatus;
}

export interface GroupOut {
  id: string;
  combo_id: string;
  name: string;
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
  sort_order: number;
  options: OptionOut[];
}

export interface ComboOut {
  id: string;
  name: string;
  kitchen_name: string;
  price: number;
  supply_kind: SupplyKind;
  tax_category_key: string | null;
  tax_category_name: string | null;
  sort_order: number;
  is_active: boolean;
  group_count: number;
  /** `catalog:<folder>/<name>`, `file:combo/combos/<uuid7 hex>.webp` or `''` (COMBO-F14). The server always sends
   *  both; optional only so that the menus other apps' tests typed before them still compile. */
  image?: string;
  /** `/p/catalog/…` or `/p/media/<hub>/…`; `''`: none, show the initials. */
  image_url?: string;
  created_at: string;
  updated_at: string;
}

export interface BlockerOut {
  code: string;
  message: string;
  group_id: string | null;
}

export interface ComboDetailOut extends ComboOut {
  groups: GroupOut[];
  sellable: boolean;
  blockers: BlockerOut[];
}

export interface DeletedOut {
  id: string;
}

export interface SaleOptionOut {
  id: string;
  product_id: string;
  product_name: string;
  sku: string;
  price_delta: number;
}

export interface SaleGroupOut {
  id: string;
  name: string;
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
  options: SaleOptionOut[];
}

export interface SaleComboOut {
  id: string;
  name: string;
  kitchen_name: string;
  price: number;
  supply_kind: SupplyKind;
  sort_order: number;
  /** `catalog:<folder>/<name>`, `file:combo/combos/<uuid7 hex>.webp` or `''` (COMBO-F14). The server always sends
   *  both; optional only so that the menus other apps' tests typed before them still compile. */
  image?: string;
  /** `/p/catalog/…` or `/p/media/<hub>/…`; `''`: none, show the initials. */
  image_url?: string;
  groups: SaleGroupOut[];
}

export interface ComponentOut {
  option_id: string;
  group_id: string;
  group_name: string;
  product_id: string;
  product_name: string;
  sku: string;
  category_id: string | null;
  is_service: boolean;
  quantity: number;
  price_delta: number;
  catalog_price: number;
  tax_category_key: string | null;
  amount: number | null;
}

export interface ResolvedOut {
  combo_id: string;
  name: string;
  kitchen_name: string;
  supply_kind: SupplyKind;
  price: number;
  supplements: number;
  amount: number;
  split: boolean;
  tax_category_key: string | null;
  components: ComponentOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'combo.combo.list': { input: ComboListIn; output: Page<ComboOut> };
    'combo.combo.get': { input: ComboRefIn; output: ComboDetailOut };
    'combo.combo.for_sale': { input: ForSaleIn; output: Page<SaleComboOut> };
    'combo.combo.resolve': { input: ResolveIn; output: ResolvedOut };
    'combo.combo.create': { input: ComboIn; output: ComboDetailOut };
    'combo.combo.update': { input: ComboPatchIn; output: ComboDetailOut };
    'combo.combo.delete': { input: ComboRefIn; output: DeletedOut };
    'combo.combo.set_image': { input: ComboImageIn; output: ComboDetailOut };
    'combo.combo.upload_image': { input: ComboImageUploadIn; output: ComboDetailOut };
    'combo.combo.suggest_image': { input: ComboImageSuggestIn; output: ComboImageSuggestOut };
    'combo.group.create': { input: GroupIn; output: GroupOut };
    'combo.group.update': { input: GroupPatchIn; output: GroupOut };
    'combo.group.delete': { input: GroupRefIn; output: DeletedOut };
    'combo.group.reorder': { input: GroupReorderIn; output: ComboDetailOut };
    'combo.option.create': { input: OptionIn; output: OptionOut };
    'combo.option.bulk_create': { input: OptionBulkIn; output: GroupOut };
    'combo.option.update': { input: OptionPatchIn; output: OptionOut };
    'combo.option.delete': { input: OptionRefIn; output: DeletedOut };
    'combo.option.reorder': { input: OptionReorderIn; output: GroupOut };
  }
}
