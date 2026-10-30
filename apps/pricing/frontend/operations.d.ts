// Types of the pricing app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/pricing/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: money in whole cents; quantities and percents are decimals as JSON strings («10.000»,
// «12.50»); dates ISO `YYYY-MM-DD`, moments ISO 8601.
import type { Page } from '../../../frontend/sdk-types';

export type SortDir = 'asc' | 'desc';
export type Status = 'active' | 'inactive' | 'all';
export type TaxBasis = 'included' | 'excluded' | 'business';
export type Kind = 'product' | 'service';
export type RuleType = 'percent' | 'fixed' | 'buy_x_get_y' | 'tiered';
export type RuleScope = 'all' | 'products' | 'services' | 'category' | 'product' | 'service';

interface PageIn {
  limit?: number;
  offset?: number;
}

// ── Price lists ────────────────────────────────────────────────────────────────────────────────

export interface PriceListListIn extends PageIn {
  search?: string;
  code?: string;
  name?: string;
  currency?: string;
  customer_group_id?: string;
  tax_basis?: TaxBasis;
  status?: Status;
  sort?: 'code' | 'name' | 'currency' | 'customer_group_name' | 'tax_included';
  dir?: SortDir;
}

/** A list by its id, or by its code or name. */
export interface PriceListRefIn {
  id?: string;
  price_list?: string;
}

export interface PriceListIn {
  code: string;
  name: string;
  currency?: string;
  tax_included?: boolean | null;
  customer_group_id?: string | null;
  customer_group?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  is_default?: boolean;
}

/** Only the fields sent change; `null` empties the group, the tax basis or a day. */
export interface PriceListPatchIn extends PriceListRefIn {
  code?: string;
  name?: string;
  currency?: string;
  tax_included?: boolean | null;
  customer_group_id?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
}

export interface PriceListDefaultIn extends PriceListRefIn {
  is_default?: boolean;
}

export interface PriceListOut {
  id: string;
  code: string;
  name: string;
  currency: string;
  /** `null`: as the business sells. */
  tax_included: boolean | null;
  customer_group_id: string | null;
  customer_group_name: string | null;
  valid_from: string | null;
  valid_until: string | null;
  is_default: boolean;
  is_active: boolean;
  item_count: number;
  updated_at: string;
}

// ── Prices ─────────────────────────────────────────────────────────────────────────────────────

export interface PriceItemListIn extends PageIn {
  price_list_id?: string;
  price_list?: string;
  product_id?: string;
  service_id?: string;
  kind?: Kind;
  search?: string;
  sort?: 'name' | 'min_quantity' | 'price';
  dir?: SortDir;
}

export interface PriceItemIn {
  price_list_id?: string;
  price_list?: string;
  product_id?: string;
  product?: string;
  service_id?: string;
  service?: string;
  price: number;
  min_quantity?: string;
}

export interface PriceItemPatchIn {
  id: string;
  price?: number;
  min_quantity?: string;
}

export interface PriceItemIdIn {
  id: string;
}

export interface PriceItemRefIn {
  id?: string;
  price_list_id?: string;
  price_list?: string;
  product_id?: string;
  product?: string;
  service_id?: string;
  service?: string;
  min_quantity?: string;
}

export interface PriceItemOut {
  id: string;
  price_list_id: string;
  price_list_code: string;
  price_list_name: string;
  kind: Kind;
  product_id: string | null;
  service_id: string | null;
  name: string;
  sku: string | null;
  unit: string | null;
  base_price: number | null;
  min_quantity: string;
  price: number;
  updated_at: string;
}

/** One price with the currency of its list, the one its price is in (ISO 4217). */
export interface PriceItemDetailOut extends PriceItemOut {
  currency: string;
}

export interface DeletedOut {
  id: string;
}

// ── Rules ──────────────────────────────────────────────────────────────────────────────────────

export interface Tier {
  min_quantity: string;
  percent: string;
}

export interface RuleListIn extends PageIn {
  search?: string;
  code?: string;
  name?: string;
  rule_type?: RuleType;
  applies_to?: RuleScope;
  customer_group_id?: string;
  status?: Status;
  sort?: 'code' | 'name' | 'rule_type' | 'priority';
  dir?: SortDir;
}

export interface RuleRefIn {
  id?: string;
  rule?: string;
}

export interface RuleFields {
  percent?: string | null;
  amount?: number | null;
  buy_quantity?: number | null;
  get_quantity?: number | null;
  tiers?: Tier[];
  applies_to?: RuleScope;
  category_id?: string | null;
  product_id?: string | null;
  service_id?: string | null;
  customer_group_id?: string | null;
  min_quantity?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  priority?: number;
}

export interface RuleIn extends RuleFields {
  code: string;
  name: string;
  rule_type: RuleType;
}

export interface RulePatchIn extends RuleRefIn, RuleFields {
  code?: string;
  name?: string;
  rule_type?: RuleType;
}

export interface RuleOut {
  id: string;
  code: string;
  name: string;
  rule_type: RuleType;
  percent: string | null;
  amount: number | null;
  buy_quantity: number | null;
  get_quantity: number | null;
  tiers: Tier[];
  applies_to: RuleScope;
  category_id: string | null;
  category_name: string | null;
  product_id: string | null;
  product_name: string | null;
  service_id: string | null;
  service_name: string | null;
  /** Inventory deleted its category or product: it no longer applies to anything. */
  target_deleted: boolean;
  customer_group_id: string | null;
  customer_group_name: string | null;
  min_quantity: string | null;
  valid_from: string | null;
  valid_until: string | null;
  priority: number;
  is_active: boolean;
  updated_at: string;
}

// ── The price of a line ────────────────────────────────────────────────────────────────────────

export interface ResolveIn {
  product_id?: string;
  product?: string;
  service_id?: string;
  service?: string;
  customer_id?: string;
  customer?: string;
  quantity?: string;
  /** Whether the sale's prices carry the tax (true by default): only lists of that basis compete. */
  tax_included?: boolean;
  when?: string;
  price_list_id?: string;
  price_list?: string;
}

export interface ResolveOut {
  kind: Kind;
  product_id: string | null;
  service_id: string | null;
  name: string;
  quantity: string;
  date: string;
  base_price: number;
  unit_price: number;
  price_list_id: string | null;
  price_list_code: string | null;
  price_list_name: string | null;
  tax_included: boolean | null;
  currency: string;
  line_amount: number;
  discount: number;
  rule_id: string | null;
  rule_code: string | null;
  rule_name: string | null;
  rule_type: RuleType | null;
  total: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'pricing.price_list.list': { input: PriceListListIn; output: Page<PriceListOut> };
    'pricing.price_list.get': { input: PriceListRefIn; output: PriceListOut };
    'pricing.price_list.create': { input: PriceListIn; output: PriceListOut };
    'pricing.price_list.update': { input: PriceListPatchIn; output: PriceListOut };
    'pricing.price_list.set_default': { input: PriceListDefaultIn; output: PriceListOut };
    'pricing.price_list.deactivate': { input: PriceListRefIn; output: PriceListOut };
    'pricing.price_list.activate': { input: PriceListRefIn; output: PriceListOut };
    'pricing.price_item.list': { input: PriceItemListIn; output: Page<PriceItemOut> };
    'pricing.price_item.get': { input: PriceItemIdIn; output: PriceItemDetailOut };
    'pricing.price_item.add': { input: PriceItemIn; output: PriceItemOut };
    'pricing.price_item.update': { input: PriceItemPatchIn; output: PriceItemOut };
    'pricing.price_item.remove': { input: PriceItemRefIn; output: DeletedOut };
    'pricing.rule.list': { input: RuleListIn; output: Page<RuleOut> };
    'pricing.rule.create': { input: RuleIn; output: RuleOut };
    'pricing.rule.update': { input: RulePatchIn; output: RuleOut };
    'pricing.rule.deactivate': { input: RuleRefIn; output: RuleOut };
    'pricing.rule.activate': { input: RuleRefIn; output: RuleOut };
    'pricing.price.resolve': { input: ResolveIn; output: ResolveOut };
  }
}
