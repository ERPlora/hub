// Types of the service app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`), from
// apps/service/schemas.py. Written by hand, as the other apps', until V3 generates them from
// `/api/openapi.json`. Keep it in step with schemas.py and `frontend/generated/operations.json`.
// One input per operation (ninja's parity): no path parameters, an id travels in the input.
// On the wire: money in whole minor units of the business's currency, minutes as integers, dates and moments ISO 8601.
import type { Page } from '../../../frontend/sdk-types';

export type PricingType = 'fixed' | 'hourly' | 'from' | 'variable' | 'free';
export type ServiceStatus = 'active' | 'unconfigured' | 'archived';
export type DiscountType = 'percentage' | 'fixed';
export type PackageStatus = 'active' | 'archived' | 'deleted';
export type GrantStatus = 'active' | 'voided';
export type MovementKind =
  | 'held'
  | 'consumed'
  | 'released'
  | 'expired'
  | 'returned'
  | 'adjusted'
  | 'corrected';
/** Why a voucher is the one the till spends first (only on the first option). */
export type TenderReason =
  | ''
  | 'only_option'
  | 'finite_before_unlimited'
  | 'expires_first'
  | 'already_started'
  | 'fewest_sessions_left'
  | 'oldest_voucher'
  | 'stable_order';

interface PageIn {
  limit?: number;
  offset?: number;
}

type NoInput = Record<string, never>;

export interface ByIdIn {
  id: string;
}

export interface DeletedOut {
  id: string;
}

// ── Services ───────────────────────────────────────────────────────────────────────────────────

export interface ServiceRefIn {
  id?: string | null;
  service?: string | null;
}

export interface ServiceListIn extends PageIn {
  search?: string;
  name?: string;
  category_id?: string;
  category?: string;
  pricing_type?: PricingType;
  price_min?: number;
  price_max?: number;
  duration_min?: number;
  duration_max?: number;
  status?: ServiceStatus;
  /** A column, `-` first for descending. */
  sort?: string;
}

export interface ServiceForSaleIn extends PageIn {
  search?: string;
  category_id?: string;
}

export interface ServiceIn {
  name: string;
  tax_category_key?: string | null;
  pricing_type?: PricingType;
  price?: number;
  min_price?: number | null;
  max_price?: number | null;
  cost?: number;
  duration_minutes?: number | null;
  buffer_before?: number | null;
  buffer_after?: number | null;
  max_capacity?: number;
  category_id?: string | null;
  category?: string | null;
  description?: string;
  short_description?: string;
  is_bookable?: boolean;
  requires_confirmation?: boolean;
  allow_online_booking?: boolean | null;
  sort_order?: number;
  is_featured?: boolean;
  sku?: string;
  barcode?: string;
  notes?: string;
}

/** Only the fields sent change; `category_id: null` leaves it without a category. */
export interface ServicePatchIn extends ServiceRefIn {
  name?: string;
  tax_category_key?: string;
  pricing_type?: PricingType;
  price?: number;
  min_price?: number | null;
  max_price?: number | null;
  duration_minutes?: number;
  category_id?: string | null;
}

export interface ServiceOut {
  id: string;
  name: string;
  description: string;
  short_description: string;
  category_id: string | null;
  category_name: string | null;
  pricing_type: PricingType;
  price: number;
  min_price: number | null;
  max_price: number | null;
  cost: number;
  duration_minutes: number;
  buffer_before: number;
  buffer_after: number;
  max_capacity: number;
  is_bookable: boolean;
  requires_confirmation: boolean;
  allow_online_booking: boolean;
  sort_order: number;
  is_featured: boolean;
  sku: string;
  barcode: string;
  notes: string;
  tax_category_id: string | null;
  tax_category_key: string | null;
  tax_category_name: string | null;
  needs_tax_setup: boolean;
  status: ServiceStatus;
  is_active: boolean;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ServiceSaleOut {
  id: string;
  name: string;
  pricing_type: PricingType;
  price: number;
  min_price: number | null;
  max_price: number | null;
  duration_minutes: number;
  buffer_before: number;
  buffer_after: number;
  is_bookable: boolean;
  allow_online_booking: boolean;
  category_id: string | null;
  category_name: string | null;
  tax_category_id: string | null;
  tax_category_key: string | null;
  needs_tax_setup: boolean;
}

export interface ServiceBulkIn {
  services: ServiceIn[];
}

export interface ServicesOut {
  created: number;
  ids: string[];
}

export interface CatalogStatusOut {
  services: number;
  sellable_services: number;
  needs_tax_setup: number;
}

// ── Categories ─────────────────────────────────────────────────────────────────────────────────

export interface CategoryRefIn {
  id?: string | null;
  category?: string | null;
}

export interface CategoryListIn extends PageIn {
  search?: string;
  parent_id?: string;
  sort?: string;
}

export interface CategoryIn {
  name: string;
  description?: string;
  parent_id?: string | null;
  parent?: string | null;
  icon?: string;
  color?: string;
  sort_order?: number;
}

/** Only the fields sent change; `parent_id: null` makes it a root category. */
export interface CategoryPatchIn extends CategoryRefIn {
  name?: string;
  description?: string;
  parent_id?: string | null;
  icon?: string;
  color?: string;
  sort_order?: number;
}

export interface CategoryOut {
  id: string;
  name: string;
  description: string;
  parent_id: string | null;
  parent_name: string | null;
  icon: string;
  color: string;
  sort_order: number;
  service_count: number;
  created_at: string;
  updated_at: string;
}

// ── Settings ───────────────────────────────────────────────────────────────────────────────────

export interface SettingsIn {
  default_duration?: number;
  default_buffer_time?: number;
  default_tax_category_key?: string | null;
  show_prices?: boolean;
  show_duration?: boolean;
  allow_online_booking?: boolean;
}

export interface SettingsOut {
  default_duration: number;
  default_buffer_time: number;
  default_tax_category_id: string | null;
  default_tax_category_key: string | null;
  default_tax_category_name: string | null;
  show_prices: boolean;
  show_duration: boolean;
  allow_online_booking: boolean;
  updated_at: string | null;
}

// ── Who performs each service ──────────────────────────────────────────────────────────────────

export interface AssignmentListIn extends PageIn {
  service_id?: string;
  service?: string;
  member_id?: string;
  member?: string;
}

export interface EligibleIn extends PageIn {
  service_id?: string;
  service?: string;
}

export interface AssignIn {
  service_id?: string | null;
  service?: string | null;
  member_id?: string | null;
  member?: string | null;
  custom_duration?: number | null;
  custom_price?: number | null;
  is_primary?: boolean;
}

/** Only the fields sent change; `null` brings back the service's duration or price. */
export interface AssignmentPatchIn extends ByIdIn {
  custom_duration?: number | null;
  custom_price?: number | null;
  is_primary?: boolean;
  is_active?: boolean;
}

export interface AssignmentOut {
  id: string;
  service_id: string;
  service_name: string;
  member_id: string;
  member_name: string;
  custom_duration: number | null;
  custom_price: number | null;
  is_primary: boolean;
  is_active: boolean;
  duration: number;
  price: number;
}

export interface EligibleOut {
  member_id: string;
  full_name: string;
  color: string;
  booking_buffer: number;
  custom_duration: number | null;
  custom_price: number | null;
  is_primary: boolean;
  duration: number;
  price: number;
}

// ── Packages ───────────────────────────────────────────────────────────────────────────────────

export interface PackageRefIn {
  id?: string | null;
  package?: string | null;
}

export interface PackageListIn extends PageIn {
  search?: string;
  name?: string;
  status?: PackageStatus;
  sort?: string;
}

export interface PackageLineIn {
  service_id?: string | null;
  service?: string | null;
  sessions?: number;
}

export interface PackageIn {
  name: string;
  description?: string;
  discount_type?: DiscountType;
  discount_percent_bp?: number;
  discount_amount?: number;
  fixed_price?: number | null;
  validity_days?: number | null;
  max_uses?: number | null;
  is_active?: boolean;
  is_featured?: boolean;
  sort_order?: number;
  items: PackageLineIn[];
}

/** Only the fields sent change; `null` removes the closed price, the validity or the uses limit. */
export interface PackagePatchIn extends PackageRefIn {
  name?: string;
  description?: string;
  discount_type?: DiscountType;
  discount_percent_bp?: number;
  discount_amount?: number;
  fixed_price?: number | null;
  validity_days?: number | null;
  max_uses?: number | null;
  is_active?: boolean;
}

export interface PackageItemOut {
  id: string;
  service_id: string;
  service_name: string;
  service_price: number;
  sessions: number;
  sort_order: number;
}

export interface PackageOut {
  id: string;
  name: string;
  description: string;
  discount_type: DiscountType;
  discount_percent_bp: number;
  discount_amount: number;
  fixed_price: number | null;
  validity_days: number | null;
  max_uses: number | null;
  is_active: boolean;
  is_featured: boolean;
  sort_order: number;
  status: PackageStatus;
  item_count: number;
  items: PackageItemOut[];
  grant_count: number;
  created_at: string;
  updated_at: string;
}

// ── Vouchers sold ──────────────────────────────────────────────────────────────────────────────

export interface GrantListIn extends PageIn {
  package_id?: string;
  package?: string;
  customer_id?: string;
  customer?: string;
  status?: GrantStatus;
}

export interface GrantIn {
  package_id?: string | null;
  package?: string | null;
  customer_id?: string | null;
  customer?: string | null;
  amount?: number;
  net_amount?: number;
  tax_amount?: number;
  sale_id?: string | null;
  granted_at?: string | null;
  note?: string;
}

export interface GrantOut {
  id: string;
  package_id: string;
  package_name: string;
  customer_id: string;
  customer_name: string | null;
  customer_deleted_at: string | null;
  granted_at: string;
  source: 'manual' | 'sale';
  sale_id: string | null;
  amount: number;
  net_amount: number;
  tax_amount: number;
  note: string;
  max_uses: number | null;
  uses_added: number;
  uses_removed: number;
  days_added: number;
  used: number;
  remaining: number | null;
  expires_at: string | null;
  is_expired: boolean;
  status: GrantStatus;
  voided_at: string | null;
  voided_by: string;
  void_reason: string;
  can_void: boolean;
  can_adjust: boolean;
}

export interface OrphanOut {
  id: string;
  package_id: string;
  package_name: string;
  customer_id: string;
  customer_deleted_at: string;
  granted_at: string;
  amount: number;
  remaining: number | null;
  is_expired: boolean;
}

export interface VoidIn extends ByIdIn {
  reason: string;
}

export interface VoidCheckOut {
  id: string;
  voidable: boolean;
  reason: '' | 'already_voided' | 'in_use';
  used: number;
}

export interface AdjustIn extends ByIdIn {
  uses_delta?: number;
  days_delta?: number;
  reason: string;
}

export interface AdjustCheckOut {
  id: string;
  can_add_uses: boolean;
  can_extend: boolean;
  uses_left: number | null;
  expires_at: string | null;
  reason: '' | 'already_voided';
}

export interface RedeemIn extends ByIdIn {
  service_id?: string | null;
  service?: string | null;
  appointment_id?: string | null;
  sale_id?: string | null;
  note?: string;
}

export interface RedeemCheckIn extends ByIdIn {
  service_id?: string | null;
  service?: string | null;
}

export interface RedeemCheckOut {
  id: string;
  redeemable: boolean;
  reason: '' | 'voided' | 'expired' | 'no_uses_left' | 'does_not_cover_service';
  remaining: number | null;
}

export interface RedemptionOut {
  id: string;
  grant_id: string;
  service_id: string | null;
  service_name: string | null;
  redeemed_at: string;
  remaining: number | null;
}

// ── Movements ──────────────────────────────────────────────────────────────────────────────────

/** SERVICE-F22: the customer's vouchers that can pay a line of the service. */
export interface TenderOptionsIn extends PageIn {
  customer_id?: string;
  customer?: string;
  service_id?: string;
  service?: string;
}

export interface TenderOptionOut {
  grant_id: string;
  package_id: string;
  package_name: string;
  granted_at: string;
  /** Adjustments included; null = unlimited. */
  max_uses: number | null;
  used: number;
  remaining_before: number | null;
  remaining_after: number | null;
  is_unlimited: boolean;
  expires_at: string | null;
  /** The one the till spends first. */
  is_default: boolean;
  default_reason: TenderReason;
  candidate_count: number;
}

export interface MovementListIn extends PageIn {
  package_id?: string;
  package?: string;
}

export interface MovementOut {
  id: string;
  kind: MovementKind;
  at: string;
  grant_id: string;
  customer_id: string;
  customer_name: string | null;
  service_id: string | null;
  service_name: string | null;
  sale_id: string | null;
  appointment_id: string | null;
  note: string;
  actor: string;
  uses_delta: number;
  days_delta: number;
  reason: string;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'service.service.list': { input: ServiceListIn; output: Page<ServiceOut> };
    'service.service.get': { input: ServiceRefIn; output: ServiceOut };
    'service.service.list_for_sale': { input: ServiceForSaleIn; output: Page<ServiceSaleOut> };
    'service.service.create': { input: ServiceIn; output: ServiceOut };
    'service.service.bulk_create': { input: ServiceBulkIn; output: ServicesOut };
    'service.service.update': { input: ServicePatchIn; output: ServiceOut };
    'service.service.archive': { input: ServiceRefIn; output: ServiceOut };
    'service.service.restore': { input: ServiceRefIn; output: ServiceOut };
    'service.catalog.status': { input: NoInput; output: CatalogStatusOut };
    'service.category.list': { input: CategoryListIn; output: Page<CategoryOut> };
    'service.category.get': { input: CategoryRefIn; output: CategoryOut };
    'service.category.create': { input: CategoryIn; output: CategoryOut };
    'service.category.update': { input: CategoryPatchIn; output: CategoryOut };
    'service.category.delete': { input: CategoryRefIn; output: DeletedOut };
    'service.settings.get': { input: NoInput; output: SettingsOut };
    'service.settings.update': { input: SettingsIn; output: SettingsOut };
    'service.assignment.list': { input: AssignmentListIn; output: Page<AssignmentOut> };
    'service.assignment.eligible': { input: EligibleIn; output: Page<EligibleOut> };
    'service.assignment.assign': { input: AssignIn; output: AssignmentOut };
    'service.assignment.update': { input: AssignmentPatchIn; output: AssignmentOut };
    'service.assignment.remove': { input: ByIdIn; output: DeletedOut };
    'service.package.list': { input: PackageListIn; output: Page<PackageOut> };
    'service.package.get': { input: PackageRefIn; output: PackageOut };
    'service.package.create': { input: PackageIn; output: PackageOut };
    'service.package.update': { input: PackagePatchIn; output: PackageOut };
    'service.package.delete': { input: PackageRefIn; output: DeletedOut };
    'service.grant.list': { input: GrantListIn; output: Page<GrantOut> };
    'service.grant.list_orphans': { input: PageIn; output: Page<OrphanOut> };
    'service.grant.void_check': { input: ByIdIn; output: VoidCheckOut };
    'service.grant.adjust_check': { input: ByIdIn; output: AdjustCheckOut };
    'service.grant.redeem_check': { input: RedeemCheckIn; output: RedeemCheckOut };
    'service.grant.create': { input: GrantIn; output: GrantOut };
    'service.grant.void': { input: VoidIn; output: GrantOut };
    'service.grant.adjust': { input: AdjustIn; output: GrantOut };
    'service.grant.redeem': { input: RedeemIn; output: RedemptionOut };
    'service.movement.list': { input: MovementListIn; output: Page<MovementOut> };
    'service.grant.tender_options': { input: TenderOptionsIn; output: Page<TenderOptionOut> };
  }
}
