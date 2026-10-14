// A refusal of the server, painted where it belongs: a 422 under its fields and the 409 «a group
// with that name already exists» under «Name» (CUSTOMER-F27–F29), anything else as one message.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { refusalFields, refusalOutsideFields } from './apiErrors';

const invalid = new ApiError(422, 'customer.phone_invalid', 'Not a valid phone', { phone: 'Not a valid phone' });
const taken = new ApiError(409, 'customer.group_name_taken', 'Name taken', { name: 'Name taken' });
const gone = new ApiError(404, 'customer.customer_unavailable', 'This customer is no longer available.');

describe('refusalFields', () => {
  it('gives the per-field messages of a 422 and of a 409 that names its field', () => {
    expect(refusalFields(invalid)).toEqual({ phone: 'Not a valid phone' });
    expect(refusalFields(taken)).toEqual({ name: 'Name taken' });
  });

  it('gives nothing for any other error, or none', () => {
    expect(refusalFields(gone)).toEqual({});
    expect(refusalFields(new Error('boom'))).toEqual({});
    expect(refusalFields(null)).toEqual({});
  });
});

describe('refusalOutsideFields', () => {
  it('is empty when every per-field message has a field on screen to sit under', () => {
    expect(refusalOutsideFields(invalid, ['name', 'phone'])).toBe('');
  });

  it('is the message when the refusal names no field shown (a custom field of a closed section, a 404, a network failure)', () => {
    expect(refusalOutsideFields(invalid, ['name'])).toBe('Not a valid phone');
    expect(refusalOutsideFields(gone, ['name'])).toBe('This customer is no longer available.');
    expect(refusalOutsideFields(new Error('offline'), [])).toBe('offline');
  });

  it('is empty without an error', () => {
    expect(refusalOutsideFields(null, [])).toBe('');
    expect(refusalOutsideFields(undefined, [])).toBe('');
  });
});
