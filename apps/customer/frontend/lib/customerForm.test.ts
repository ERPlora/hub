// The card's form, one shape for «Add» and «Edit» (WORKBOOK «Un solo formulario de ficha para el
// alta y la edición»: F01, F04): what it starts from, what «Add» sends and what «Save» sends (only
// what changed; clearing a field is a change).
import { describe, expect, it } from 'vitest';

import type { CustomerDetailOut } from '../operations';
import {
  blankCustomer,
  createInput,
  ESSENTIAL_FIELDS,
  fieldsFromDetail,
  MORE_FIELDS,
  patchInput,
  PICKABLE_SOURCES,
} from './customerForm';

const DETAIL: CustomerDetailOut = {
  id: 'c1',
  name: 'Ana García',
  email: 'ana@x.es',
  phone: '+34600111222',
  tax_id: '12345678Z',
  company_name: 'ACME',
  lifecycle_stage: 'active',
  source: 'import',
  is_active: true,
  total_purchases: 3,
  total_spent: 4500,
  last_purchase_at: '2026-10-01T10:00:00Z',
  address: 'Calle 1',
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
  custom_fields: [],
  consent: [],
  marketing_consent: false,
  consent_date: null,
};

describe('the fields of the form', () => {
  it('shows name, phone, email, tax id and company in sight; the rest behind «More details» (F01)', () => {
    expect(ESSENTIAL_FIELDS).toEqual(['name', 'phone', 'email', 'tax_id', 'company_name']);
    expect(MORE_FIELDS).toEqual([
      'address',
      'city',
      'postal_code',
      'country',
      'avatar',
      'birthday',
      'anniversary',
      'source',
      'lifecycle_stage',
      'preferred_channel',
      'notes',
    ]);
  });

  it('offers the sources a person picks; «Import» is the import\'s own', () => {
    expect(PICKABLE_SOURCES).toEqual(['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'other']);
  });
});

describe('blankCustomer and createInput (F01)', () => {
  it('starts as a walk-in lead with no preferred channel, active', () => {
    expect(blankCustomer()).toMatchObject({ name: '', source: 'walk_in', lifecycle_stage: 'lead', preferred_channel: 'none', is_active: true });
  });

  it('sends the whole card in one call, dates empty as null, without «Active» (a new card is active)', () => {
    const form = { ...blankCustomer(), name: 'Luis', phone: '600 111 222', birthday: '2000-01-01' };
    const input = createInput(form);
    expect(input).toMatchObject({ name: 'Luis', phone: '600 111 222', birthday: '2000-01-01', anniversary: null, source: 'walk_in' });
    expect(input).not.toHaveProperty('is_active');
  });
});

describe('fieldsFromDetail and patchInput (F04)', () => {
  it('opens the form with the card as saved; a missing date is empty', () => {
    expect(fieldsFromDetail(DETAIL)).toMatchObject({ name: 'Ana García', phone: '+34600111222', birthday: '1990-02-03', anniversary: '', is_active: true });
  });

  it('sends only what changed, and nothing when nothing did', () => {
    const original = fieldsFromDetail(DETAIL);
    expect(patchInput(original, original)).toEqual({});
    expect(patchInput(original, { ...original, city: 'Sevilla', is_active: false })).toEqual({ city: 'Sevilla', is_active: false });
  });

  it('clearing a field is a change: an emptied text is sent empty, an emptied date as null', () => {
    const original = fieldsFromDetail(DETAIL);
    expect(patchInput(original, { ...original, email: '', birthday: '' })).toEqual({ email: '', birthday: null });
  });
});
