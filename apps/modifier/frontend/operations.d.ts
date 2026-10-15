// Types of the modifier app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/modifier/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: supplements in whole cents (negative = a discount), moments ISO 8601.
import type { Page } from '../../../frontend/sdk-types';

export type GroupSort =
  | 'name'
  | '-name'
  | 'sort_order'
  | '-sort_order'
  | 'min_choices'
  | '-min_choices'
  | 'max_choices'
  | '-max_choices'
  | 'option_count'
  | '-option_count'
  | 'link_count'
  | '-link_count';
export type OptionSort = 'sort_order' | '-sort_order' | 'name' | '-name' | 'price_delta' | '-price_delta';
export type TargetKind = 'product' | 'category';

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A group by its id, or by its name as a person says it. */
export interface GroupRefIn {
  id?: string;
  group?: string;
}

export interface GroupListIn extends PageIn {
  search?: string;
  name?: string;
  required?: boolean;
  sort?: GroupSort;
}

export interface GroupIn {
  name: string;
  kitchen_name?: string;
  min_choices?: number;
  max_choices?: number;
  allow_repeat?: boolean;
  sort_order?: number;
}

/** Only what is sent changes. */
export interface GroupPatchIn extends GroupRefIn {
  name?: string;
  kitchen_name?: string;
  min_choices?: number;
  max_choices?: number;
  allow_repeat?: boolean;
  sort_order?: number;
}

export interface GroupOut {
  id: string;
  name: string;
  kitchen_name: string;
  min_choices: number;
  /** 0 = no ceiling. */
  max_choices: number;
  allow_repeat: boolean;
  is_required: boolean;
  sort_order: number;
  option_count: number;
  default_count: number;
  link_count: number;
  created_at: string;
  updated_at: string;
}

export interface OptionListIn extends PageIn {
  group_id?: string;
  group?: string;
  search?: string;
  sort?: OptionSort;
}

/** An option by its id, or by its name and, when two groups have one so named, its group. */
export interface OptionRefIn {
  id?: string;
  option?: string;
  group_id?: string;
  group?: string;
}

export interface OptionIn {
  group_id?: string;
  group?: string;
  name: string;
  kitchen_name?: string;
  price_delta?: number;
  /** Key or name of its own tax category; empty = the dish's. */
  tax_category_key?: string;
  is_default?: boolean;
  sort_order?: number;
}

/** Only what is sent changes; `tax_category_key: ''` gives it back the dish's. */
export interface OptionPatchIn extends OptionRefIn {
  name?: string;
  kitchen_name?: string;
  price_delta?: number;
  tax_category_key?: string;
  is_default?: boolean;
  sort_order?: number;
}

export interface OptionOut {
  id: string;
  group_id: string;
  group_name: string;
  name: string;
  kitchen_name: string;
  price_delta: number;
  tax_category_key: string | null;
  tax_category_name: string | null;
  is_default: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface LinkListIn extends PageIn {
  group_id?: string;
  group?: string;
  product_id?: string;
  category_id?: string;
}

/** Exactly one product (id, SKU or name) or one category (id or name). */
interface TargetRef {
  product_id?: string;
  product?: string;
  category_id?: string;
  category?: string;
}

export interface LinkIn extends TargetRef {
  group_id?: string;
  group?: string;
}

/** By the link's id, or by its group and its product or category. */
export interface LinkRefIn extends TargetRef {
  id?: string;
  group_id?: string;
  group?: string;
}

export interface LinkOut {
  id: string;
  group_id: string;
  group_name: string;
  target_kind: TargetKind;
  product_id: string | null;
  product_name: string | null;
  product_sku: string | null;
  category_id: string | null;
  category_name: string | null;
  created_at: string;
}

export interface TargetIn {
  product_id?: string;
  product?: string;
}

export interface TargetOptionOut {
  id: string;
  name: string;
  kitchen_name: string;
  price_delta: number;
  tax_category_key: string | null;
  is_default: boolean;
}

export interface TargetGroupOut {
  id: string;
  name: string;
  kitchen_name: string;
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
  is_required: boolean;
  options: TargetOptionOut[];
}

export interface TargetOut {
  product_id: string;
  product_name: string;
  groups: TargetGroupOut[];
}

export interface ResolveIn extends TargetIn {
  /** In the order chosen; repeated = chosen that many times. */
  option_ids?: string[];
}

export interface PickOut {
  option_id: string;
  group_id: string;
  group_name: string;
  name: string;
  kitchen_name: string;
  price_delta: number;
  tax_category_key: string | null;
  own_line: boolean;
}

/** A child line of the dish line: an option that taxes differently, with its quantity per unit of the dish. */
export interface OwnLineOut {
  option_id: string;
  group_id: string;
  name: string;
  kitchen_name: string;
  tax_category_key: string;
  price_delta: number;
  quantity: number;
}

export interface ResolveOut {
  product_id: string;
  picks: PickOut[];
  folded_delta: number;
  own_lines: OwnLineOut[];
  kitchen_text: string;
}

export interface DeletedOut {
  id: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'modifier.group.list': { input: GroupListIn; output: Page<GroupOut> };
    'modifier.group.get': { input: GroupRefIn; output: GroupOut };
    'modifier.group.for_target': { input: TargetIn; output: TargetOut };
    'modifier.group.create': { input: GroupIn; output: GroupOut };
    'modifier.group.update': { input: GroupPatchIn; output: GroupOut };
    'modifier.group.delete': { input: GroupRefIn; output: DeletedOut };
    'modifier.option.list': { input: OptionListIn; output: Page<OptionOut> };
    'modifier.option.create': { input: OptionIn; output: OptionOut };
    'modifier.option.update': { input: OptionPatchIn; output: OptionOut };
    'modifier.option.delete': { input: OptionRefIn; output: DeletedOut };
    'modifier.link.list': { input: LinkListIn; output: Page<LinkOut> };
    'modifier.link.attach': { input: LinkIn; output: LinkOut };
    'modifier.link.detach': { input: LinkRefIn; output: DeletedOut };
    'modifier.selection.resolve': { input: ResolveIn; output: ResolveOut };
  }
}
