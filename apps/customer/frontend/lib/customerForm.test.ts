// The card's form, one shape for «Add» and «Edit» (WORKBOOK «Un solo formulario de ficha para el
// alta y la edición»: F01, F04): what it starts from, what «Add» sends and what «Save» sends (only
// what changed; clearing a field is a change).
import { describe, expect, it } from 'vitest';

import { DETAIL } from '../__tests__/fixtures';
import {
  blankCustomer,
  createInput,
  ESSENTIAL_FIELDS,
  fieldsFromDetail,
  MORE_FIELDS,
  patchInput,
  PICKABLE_SOURCES,
} from './customerForm';

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

  it('sends the whole card in one call, a day without its year as typed, without «Active» (a new card is active)', () => {
    const form = { ...blankCustomer(), name: 'Luis', phone: '600 111 222', birthday: '--03-12' };
    const input = createInput(form);
    expect(input).toMatchObject({ name: 'Luis', phone: '600 111 222', birthday: '--03-12', anniversary: '', source: 'walk_in' });
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

  it('clearing a field is a change: an emptied text or day is sent empty', () => {
    const original = fieldsFromDetail(DETAIL);
    expect(patchInput(original, { ...original, email: '', birthday: '' })).toEqual({ email: '', birthday: '' });
  });
});
