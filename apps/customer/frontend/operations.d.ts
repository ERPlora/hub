// Types of the customer app's operations for the SDK (`useLive`, `useCommand`, `client.api.call`).
// WRITTEN BY HAND for the PoC from apps/customer/schemas.py, like frontend/sdk-types.d.ts; V3
// generates them from `/api/openapi.json`. Keep them in step with `frontend/generated/operations.json`.
// One input per operation: no path parameters, ids travel in the query string (GET) or the body.
// Money is in cents; dates are ISO 8601 strings (`YYYY-MM-DD` for a day).

export type CustomerStage =
  | 'lead'
  | 'prospect'
  | 'first_purchase'
  | 'active'
  | 'at_risk'
  | 'dormant'
  | 'churned'
  | 'vip';

export type CustomerSource = 'walk_in' | 'website' | 'phone' | 'referral' | 'social' | 'whatsapp' | 'import' | 'other';

export type PreferredChannel = 'none' | 'email' | 'sms' | 'whatsapp' | 'phone';

export type CustomFieldType = 'text' | 'number' | 'date' | 'boolean' | 'select' | 'textarea';

export type ConsentChannel = 'email' | 'sms' | 'whatsapp' | 'phone' | 'postal';

export type ConsentSource = 'counter' | 'web_form' | 'phone' | 'email' | 'import' | 'receipt';

export type CustomerSort =
  | 'name'
  | 'email'
  | 'phone'
  | 'tax_id'
  | 'company_name'
  | 'lifecycle_stage'
  | 'source'
  | 'is_active'
  | 'total_purchases'
  | 'total_spent'
  | 'last_purchase_at'
  | 'created_at';

/** A page of a paginated list (`limit` ≤ 100). */
export interface CustomerPageOf<T> {
  rows: T[];
  total: number;
  limit: number;
  offset: number;
}

interface PageIn {
  limit?: number;
  offset?: number;
}

/** A card by its id, or by its exact name, phone or email. */
export interface CustomerRefIn {
  id?: string;
  customer?: string;
}

/** What a card belongs to: `customer_id`, or the card's exact name, phone or email. */
export interface CustomerOfIn {
  customer_id?: string;
  customer?: string;
}

export interface CustomerFilters {
  search?: string;
  name?: string;
  email?: string;
  phone?: string;
  tax_id?: string;
  company_name?: string;
  lifecycle_stage?: CustomerStage;
  source?: CustomerSource;
  is_active?: boolean;
  purchases_min?: number;
  purchases_max?: number;
  spent_min?: number;
  spent_max?: number;
  last_purchase_from?: string;
  last_purchase_to?: string;
  sort?: CustomerSort;
  descending?: boolean;
}

export type CustomerListIn = CustomerFilters & PageIn;

export interface CustomerIn {
  name: string;
  email?: string;
  phone?: string;
  tax_id?: string;
  company_name?: string;
  address?: string;
  city?: string;
  postal_code?: string;
  country?: string;
  avatar?: string;
  birthday?: string | null;
  anniversary?: string | null;
  source?: CustomerSource;
  lifecycle_stage?: CustomerStage;
  preferred_channel?: PreferredChannel;
  notes?: string;
}

export interface FieldValueIn {
  field_id: string;
  value: string;
}

/** Only the fields sent change. */
export interface CustomerPatchIn extends CustomerRefIn, Partial<Omit<CustomerIn, 'name'>> {
  name?: string;
  is_active?: boolean;
  field_values?: FieldValueIn[];
}

/** A CSV row as text: the server checks each one on its own. */
export interface ImportRowIn {
  name?: string;
  email?: string;
  phone?: string;
  tax_id?: string;
  company_name?: string;
  address?: string;
  city?: string;
  postal_code?: string;
  country?: string;
  avatar?: string;
  birthday?: string;
  anniversary?: string;
  lifecycle_stage?: string;
  source?: string;
  preferred_channel?: string;
  notes?: string;
}

export interface CustomerRow {
  id: string;
  name: string;
  email: string;
  phone: string;
  tax_id: string;
  company_name: string;
  lifecycle_stage: CustomerStage;
  source: CustomerSource;
  is_active: boolean;
  total_purchases: number;
  total_spent: number;
  last_purchase_at: string | null;
}

export interface CustomFieldValueOut {
  field_id: string;
  name: string;
  field_type: CustomFieldType;
  options: string[];
  is_required: boolean;
  sort_order: number;
  value: string;
}

export interface ConsentStateRow {
  purpose: string;
  channel: ConsentChannel | '';
  state: 'granted' | 'withdrawn';
  contact_point: string;
  source: ConsentSource;
  notice_version: string;
  occurred_at: string;
  recorded_by: string;
  evidence: string;
}

export interface CustomerDetailOut extends CustomerRow {
  address: string;
  city: string;
  postal_code: string;
  country: string;
  avatar: string;
  birthday: string | null;
  anniversary: string | null;
  preferred_channel: PreferredChannel;
  notes: string;
  created_at: string;
  updated_at: string;
  group_ids: string[];
  tag_ids: string[];
  custom_fields: CustomFieldValueOut[];
  consent: ConsentStateRow[];
  marketing_consent: boolean;
  consent_date: string | null;
}

export interface CustomerStatsOut {
  total: number;
  active: number;
  vip: number;
  total_revenue: number;
}

export interface PhoneMatch {
  id: string;
  name: string;
  email: string;
  phone: string;
}

export interface ExportOut {
  filename: string;
  content_type: string;
  rows: number;
  csv: string;
}

export interface ImportRowOut {
  index: number;
  id: string | null;
  errors: Record<string, string>;
  warnings: Record<string, string>;
}

export interface ImportOut {
  created: number;
  skipped: number;
  rows: ImportRowOut[];
}

export interface ActivityRow {
  id: string;
  customer_id: string;
  kind: string;
  title: string;
  text: string;
  data: Record<string, unknown>;
  /** The decimals of the currency its data carries (2 in EUR, 0 in JPY); `null` when it carries none. */
  currency_decimals: number | null;
  related_id: string;
  related_type: string;
  actor: string;
  created_at: string;
}

export interface ConsentRow {
  id: string;
  customer_id: string;
  purpose: string;
  /** Empty for a permission that is not about reaching the person (health data, CUSTOMER-F32). */
  channel: ConsentChannel | '';
  state: 'granted' | 'withdrawn';
  contact_point: string;
  source: ConsentSource;
  notice_text: string;
  notice_version: string;
  evidence: string;
  reason: string;
  recorded_by: string;
  occurred_at: string;
  created_at: string;
}

export interface OrderRow {
  order_id: string;
  customer_id: string;
  linked_at: string;
}

export interface PurchaseRow {
  id: string;
  customer_id: string;
  sale_id: string | null;
  /** In cents; negative on a refund line (CUSTOMER-F22). */
  amount: number;
  currency: string;
  /** The decimals of its currency as the server counts them (0 in JPY); `null` without a currency. */
  currency_decimals: number | null;
  status: 'confirmed' | 'voided' | 'refunded';
  recorded_at: string;
  voided_at: string | null;
  void_reason: string;
}

export interface DivergenceRow {
  id: string;
  name: string;
  total_purchases: number;
  total_spent: number;
  ledger_purchases: number;
  ledger_spent: number;
}

export interface GroupRow {
  id: string;
  name: string;
  description: string;
  color: string;
  sort_order: number;
  is_active: boolean;
  customer_count: number;
}

export interface TagRow {
  id: string;
  name: string;
  color: string;
  is_active: boolean;
  customer_count: number;
}

export interface FieldRow {
  id: string;
  name: string;
  field_type: CustomFieldType;
  options: string[];
  is_required: boolean;
  sort_order: number;
  is_active: boolean;
}

export interface GroupListIn extends PageIn {
  search?: string;
  is_active?: boolean;
  color?: string;
  customers_min?: number;
  customers_max?: number;
  sort?: 'name' | 'description' | 'color' | 'sort_order' | 'is_active' | 'customer_count';
  descending?: boolean;
}

export interface GroupIn {
  name: string;
  description?: string;
  color?: string;
  sort_order?: number;
}

export interface GroupPatchIn {
  id?: string;
  group?: string;
  name?: string;
  description?: string;
  color?: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface TagListIn extends PageIn {
  search?: string;
  is_active?: boolean;
  color?: string;
  sort?: 'name' | 'color' | 'is_active' | 'customer_count';
  descending?: boolean;
}

export interface TagIn {
  name: string;
  color?: string;
}

export interface TagPatchIn {
  id?: string;
  tag?: string;
  name?: string;
  color?: string;
  is_active?: boolean;
}

export interface FieldListIn extends PageIn {
  search?: string;
  field_type?: CustomFieldType;
  is_required?: boolean;
  is_active?: boolean;
  sort?: 'name' | 'field_type' | 'is_required' | 'sort_order' | 'is_active';
  descending?: boolean;
}

export interface FieldIn {
  name: string;
  field_type?: CustomFieldType;
  options?: string[];
  is_required?: boolean;
  sort_order?: number;
}

export interface FieldPatchIn {
  id?: string;
  field?: string;
  name?: string;
  field_type?: CustomFieldType;
  options?: string[];
  is_required?: boolean;
  sort_order?: number;
  is_active?: boolean;
}

/** Health data of a card (CUSTOMER-F32): its own block, only with the person's explicit permission. */
export type HealthTestResult = '' | 'negative' | 'positive';

export interface HealthOut {
  customer_id: string;
  consent: 'none' | 'granted' | 'withdrawn';
  consent_at: string | null;
  consent_by: string;
  notice_text: string;
  allergies: string;
  /** `YYYY-MM-DD`. */
  sensitivity_test_on: string | null;
  sensitivity_test_result: HealthTestResult;
  updated_at: string | null;
  updated_by: string;
}

export interface HealthGrantIn extends CustomerOfIn {
  notice_text: string;
  notice_version?: string;
  source?: ConsentSource;
  evidence?: string;
  occurred_at?: string | null;
}

export interface HealthWithdrawIn extends CustomerOfIn {
  source?: ConsentSource;
  reason?: string;
}

export interface HealthIn extends CustomerOfIn {
  allergies?: string;
  sensitivity_test_on?: string | null;
  sensitivity_test_result?: HealthTestResult;
}

export interface ConsentGrantIn extends CustomerOfIn {
  channel: ConsentChannel;
  notice_text: string;
  notice_version?: string;
  purpose?: string;
  source?: ConsentSource;
  evidence?: string;
  occurred_at?: string | null;
}

export interface ConsentWithdrawIn extends CustomerOfIn {
  channel: ConsentChannel;
  purpose?: string;
  source?: ConsentSource;
  reason?: string;
  evidence?: string;
  occurred_at?: string | null;
}

export interface PurchaseListIn extends CustomerOfIn, PageIn {
  search?: string;
  status?: 'confirmed' | 'voided' | 'refunded';
  recorded_from?: string;
  recorded_to?: string;
  sort?: 'recorded_at' | 'amount' | 'status';
  descending?: boolean;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'customer.customer.list': { input: CustomerListIn; output: CustomerPageOf<CustomerRow> };
    'customer.customer.detail': { input: CustomerRefIn; output: CustomerDetailOut };
    'customer.customer.stats': { input: Record<string, never>; output: CustomerStatsOut };
    'customer.customer.by_phone': { input: { phone?: string }; output: { rows: PhoneMatch[] } };
    'customer.customer.export': { input: CustomerFilters; output: ExportOut };
    'customer.customer.create': { input: CustomerIn; output: CustomerDetailOut };
    'customer.customer.update': { input: CustomerPatchIn; output: CustomerDetailOut };
    'customer.customer.import': { input: { rows: ImportRowIn[] }; output: ImportOut };
    'customer.customer.set_groups': {
      input: CustomerRefIn & { group_ids?: string[]; groups?: string[] };
      output: CustomerDetailOut;
    };
    'customer.customer.set_tags': {
      input: CustomerRefIn & { tag_ids?: string[]; tags?: string[] };
      output: CustomerDetailOut;
    };
    'customer.customer.delete': { input: CustomerRefIn; output: { id: string } };
    'customer.customer.merge': {
      input: CustomerRefIn & { absorbed_id?: string; absorbed?: string };
      output: CustomerDetailOut;
    };
    'customer.customer.erase': { input: CustomerRefIn & { reason?: string }; output: { id: string } };
    'customer.group.list': { input: GroupListIn; output: CustomerPageOf<GroupRow> };
    'customer.group.create': { input: GroupIn; output: GroupRow };
    'customer.group.update': { input: GroupPatchIn; output: GroupRow };
    'customer.group.delete': { input: { id?: string; group?: string }; output: { id: string } };
    'customer.tag.list': { input: TagListIn; output: CustomerPageOf<TagRow> };
    'customer.tag.create': { input: TagIn; output: TagRow };
    'customer.tag.update': { input: TagPatchIn; output: TagRow };
    'customer.tag.delete': { input: { id?: string; tag?: string }; output: { id: string } };
    'customer.field.list': { input: FieldListIn; output: CustomerPageOf<FieldRow> };
    'customer.field.create': { input: FieldIn; output: FieldRow };
    'customer.field.update': { input: FieldPatchIn; output: FieldRow };
    'customer.field.delete': { input: { id?: string; field?: string }; output: { id: string } };
    'customer.activity.list': {
      input: CustomerOfIn & PageIn & { search?: string };
      output: CustomerPageOf<ActivityRow>;
    };
    'customer.activity.add': {
      input: CustomerOfIn & {
        kind: string;
        title: string;
        text?: string;
        data?: Record<string, unknown>;
        related_id?: string;
        related_type?: string;
      };
      output: ActivityRow;
    };
    'customer.note.add': {
      input: CustomerOfIn & { content: string; title?: string; author_name?: string };
      output: ActivityRow;
    };
    'customer.purchase.list': { input: PurchaseListIn; output: CustomerPageOf<PurchaseRow> };
    'customer.purchase.divergences': {
      input: PageIn & { search?: string };
      output: CustomerPageOf<DivergenceRow>;
    };
    'customer.consent.history': {
      input: CustomerOfIn & PageIn & { search?: string };
      output: CustomerPageOf<ConsentRow>;
    };
    'customer.consent.state': { input: CustomerOfIn; output: { customer_id: string; rows: ConsentStateRow[] } };
    'customer.consent.grant': { input: ConsentGrantIn; output: ConsentRow };
    'customer.consent.withdraw': { input: ConsentWithdrawIn; output: ConsentRow };
    'customer.order.list': {
      input: CustomerOfIn & PageIn & { search?: string };
      output: CustomerPageOf<OrderRow>;
    };
    'customer.order.customer': { input: { order_id: string }; output: { order_id: string; customer_id: string | null } };
    'customer.health.detail': { input: CustomerOfIn; output: HealthOut };
    'customer.health.grant': { input: HealthGrantIn; output: HealthOut };
    'customer.health.withdraw': { input: HealthWithdrawIn; output: HealthOut };
    'customer.health.update': { input: HealthIn; output: HealthOut };
    'customer.order.link': {
      input: { order_id: string; customer_id?: string | null; customer?: string | null };
      output: { order_id: string; customer_id: string | null };
    };
  }
}
