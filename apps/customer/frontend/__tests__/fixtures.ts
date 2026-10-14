// Fixtures of the customer app's tests: a card as `customer.customer.detail` returns it, and a row of
// the list. Data of the tests only.
import type { CustomerDetailOut, CustomerRow } from '../operations';

export const DETAIL: CustomerDetailOut = {
  id: 'c1',
  name: 'Ana García',
  email: 'ana@x.es',
  phone: '+34600111222',
  tax_id: '12345678Z',
  company_name: 'ACME',
  lifecycle_stage: 'vip',
  source: 'walk_in',
  is_active: true,
  total_purchases: 3,
  total_spent: 4550,
  last_purchase_at: '2026-10-01T10:00:00Z',
  address: 'Calle Mayor 1',
  city: 'Madrid',
  postal_code: '28001',
  country: 'ES',
  avatar: '',
  birthday: '1990-02-03',
  anniversary: null,
  preferred_channel: 'email',
  notes: 'Likes tea',
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-10-01T10:00:00Z',
  group_ids: [],
  tag_ids: [],
  custom_fields: [
    { field_id: 'f1', name: 'Allergies', field_type: 'text', options: [], is_required: false, sort_order: 0, value: 'Nuts' },
    { field_id: 'f2', name: 'Newsletter', field_type: 'boolean', options: [], is_required: false, sort_order: 1, value: 'true' },
    { field_id: 'f3', name: 'Dye', field_type: 'select', options: ['A'], is_required: false, sort_order: 2, value: '' },
  ],
  consent: [],
  marketing_consent: false,
  consent_date: null,
};

/** A row of `customer.customer.list`. */
export function customerRow(id: string, name: string, extra: Partial<CustomerRow> = {}): CustomerRow {
  return {
    id,
    name,
    email: `${id}@x.es`,
    phone: '+34600111222',
    tax_id: '',
    company_name: '',
    lifecycle_stage: 'active',
    source: 'walk_in',
    is_active: true,
    total_purchases: 2,
    total_spent: 4550,
    last_purchase_at: null,
    ...extra,
  };
}

/** A page of a list. */
export const pageOf = <T>(rows: T[], total = rows.length) => ({ rows, total, limit: 50, offset: 0 });
