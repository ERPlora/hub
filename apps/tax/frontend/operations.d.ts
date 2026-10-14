// Types of the tax app's operations for the SDK (`useLive`, `useCommand`), from apps/tax/schemas.py.
// Written by hand, as `frontend/sdk-types.d.ts` is for the PoC, until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and with `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, a rule's `id` travels in the input.
// Decimals (`rate_pct`) are JSON strings on the way out («21.00»); dates are ISO `YYYY-MM-DD`.
import type { Page } from '../../../frontend/sdk-types';

/** Tax family (`TaxRule.TaxType`). */
export type TaxType = 'vat' | 'igic' | 'ipsi' | 'surcharge' | 'sales_tax' | 'withholding' | 'excise' | 'import_duty';

/** Fiscal qualification (`TaxRule.OperationClass`); every class but `subject` charges no tax. */
export type OperationClass = 'subject' | 'subject_reverse' | 'exempt' | 'not_subject' | 'not_subject_location';

/** Where an alias comes from (`TaxAlias.Source`). */
export type AliasSource = 'shipped' | 'learned';

export type SortDir = 'asc' | 'desc';

interface PageIn {
  limit?: number;
  offset?: number;
}

// ── Categories ─────────────────────────────────────────────────────────────────────────────────

export interface CategoryListIn extends PageIn {
  search?: string;
  key?: string;
  name?: string;
  display_name?: string;
  display_description?: string;
  is_system?: boolean;
  sort?: 'key' | 'name' | 'display_name' | 'display_description' | 'is_system' | 'is_active' | 'id';
  dir?: SortDir;
  /** Where the rate column is read; Spain by default. */
  country_code?: string;
  region_code?: string;
}

export interface CategoryGetIn {
  key: string;
}

export interface CategoryIn {
  key: string;
  name: string;
  description?: string;
  is_system?: boolean;
}

export interface CategoryOut {
  id: string;
  key: string;
  name: string;
  description: string;
  display_name: string;
  display_description: string;
  is_system: boolean;
  is_active: boolean;
}

export interface CategoryRowOut extends CategoryOut {
  /** The rate in force today where asked, components included; `null` without a rule. */
  rate_pct: string | null;
  operation_class: OperationClass | null;
}

// ── Rules ──────────────────────────────────────────────────────────────────────────────────────

export type RuleStatusFilter = 'active' | 'inactive' | 'all';

export interface RuleListIn extends PageIn {
  search?: string;
  country_code?: string;
  /** Part of the region. */
  region_code?: string;
  tax_category_key?: string;
  tax_type?: TaxType;
  operation_class?: OperationClass;
  regime_key?: string;
  parent_id?: string;
  rate_min?: string | number;
  rate_max?: string | number;
  status?: RuleStatusFilter;
  sort?:
    | 'tax_category_key'
    | 'country_code'
    | 'region_code'
    | 'rate_pct'
    | 'tax_type'
    | 'valid_from'
    | 'valid_to'
    | 'is_active'
    | 'operation_class'
    | 'regime_key'
    | 'id';
  dir?: SortDir;
}

/** The slot of a new component: the server says which roots it may hang from. */
export interface RuleParentIn extends PageIn {
  country_code: string;
  region_code?: string;
  tax_category_key: string;
  /** At 0 a root that charges no tax takes the component too. */
  rate_pct?: string | number;
}

export interface RuleCountriesIn {
  status?: RuleStatusFilter;
}

export interface RuleCountriesOut {
  countries: string[];
}

export interface RuleStatusIn {
  country_code?: string;
}

/** A root rule's fields (`RuleFields`): what the batch takes, one each. */
export interface RuleFieldsIn {
  country_code: string;
  region_code?: string;
  /** Its key, its name or an alias. */
  tax_category_key: string;
  operation_class?: OperationClass;
  rate_pct: string | number;
  tax_type?: TaxType;
  exempt_reason?: string;
  regime_key?: string;
  valid_from?: string;
  valid_to?: string;
}

export interface RuleIn extends RuleFieldsIn {
  /** The root rule this one is a component of. */
  parent_id?: string;
  component_label?: string;
}

export interface RuleBulkIn {
  rules: RuleFieldsIn[];
}

/** Which rule: its `id`, or its country, region and category. */
export interface RuleRefIn {
  id?: string;
  country_code?: string;
  region_code?: string;
  tax_category_key?: string;
}

export interface RuleEndIn extends RuleRefIn {
  /** The last day the rule applies (inclusive). */
  valid_to: string;
}

export interface RuleOut {
  id: string;
  country_code: string;
  region_code: string | null;
  tax_category_key: string;
  tax_category_name: string;
  rate_pct: string;
  tax_type: TaxType;
  operation_class: OperationClass;
  exempt_reason: string | null;
  regime_key: string | null;
  parent_id: string | null;
  component_label: string | null;
  valid_from: string | null;
  valid_to: string | null;
  is_active: boolean;
  updated_at: string;
}

export interface RuleBulkOut {
  rules: RuleOut[];
}

export interface RuleStatusOut {
  country_code: string | null;
  matching_rules: number;
  configured: boolean;
}

// ── Aliases ────────────────────────────────────────────────────────────────────────────────────

export interface AliasListIn extends PageIn {
  search?: string;
  alias?: string;
  tax_category_key?: string;
  source?: AliasSource;
  sort?: 'alias' | 'tax_category_key' | 'source' | 'is_active' | 'id';
  dir?: SortDir;
}

export interface AliasResolveIn {
  text: string;
}

export interface AliasIn {
  alias: string;
  /** Its key, its name or an alias. */
  tax_category_key: string;
  source?: AliasSource;
}

export interface AliasOut {
  id: string;
  alias: string;
  tax_category_key: string;
  tax_category_name: string;
  source: AliasSource;
  is_active: boolean;
}

export interface AliasResolveOut {
  text: string;
  tax_category_key: string | null;
  matched_by: 'key' | 'name' | 'alias' | null;
}

// ── The calculation ────────────────────────────────────────────────────────────────────────────

export interface CalculateIn {
  /** Whole cents. */
  amount: number;
  tax_category_key: string;
  country_code?: string;
  region_code?: string;
  date?: string;
  tax_included?: boolean;
  allow_missing_rate?: boolean;
}

export interface ComponentOut {
  rule_id: string;
  label: string;
  tax_type: string;
  rate_pct: string;
  base: number;
  tax: number;
}

export interface CalculationOut {
  base: number;
  tax: number;
  total: number;
  tax_category_key: string;
  tax_rate_pct: string;
  tax_country_code: string;
  tax_region_code: string | null;
  tax_rule_id: string | null;
  tax_kind: string;
  tax_operation_class: OperationClass;
  tax_regime_key: string;
  tax_exempt_reason: string;
  tax_included: boolean;
  source: 'rule' | 'fallback_zero';
  date: string;
  components: ComponentOut[];
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'tax.category.list': { input: CategoryListIn; output: Page<CategoryRowOut> };
    'tax.category.get': { input: CategoryGetIn; output: CategoryOut };
    'tax.category.create': { input: CategoryIn; output: CategoryOut };
    'tax.rule.list': { input: RuleListIn; output: Page<RuleOut> };
    'tax.rule.status': { input: RuleStatusIn; output: RuleStatusOut };
    'tax.rule.parent_candidates': { input: RuleParentIn; output: Page<RuleOut> };
    'tax.rule.countries': { input: RuleCountriesIn; output: RuleCountriesOut };
    'tax.rule.create': { input: RuleIn; output: RuleOut };
    'tax.rule.bulk_create': { input: RuleBulkIn; output: RuleBulkOut };
    'tax.rule.end': { input: RuleEndIn; output: RuleOut };
    'tax.rule.deactivate': { input: RuleRefIn; output: RuleOut };
    'tax.rule.activate': { input: RuleRefIn; output: RuleOut };
    'tax.alias.list': { input: AliasListIn; output: Page<AliasOut> };
    'tax.alias.resolve': { input: AliasResolveIn; output: AliasResolveOut };
    'tax.alias.create': { input: AliasIn; output: AliasOut };
    'tax.rate.calculate': { input: CalculateIn; output: CalculationOut };
  }
}
