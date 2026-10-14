// What a refused command says per field. A 422 (`invalid_field`) and a domain 409 that names its
// field (a SKU taken, a quantity off the unit's step, a unit that cannot change with stock) both go
// under that field; a line of a reception («items.0.qty») goes under its field name too.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { errorFields } from './errors';

describe('errorFields', () => {
  it('takes the fields of a 422 and of a 409', () => {
    expect(errorFields(new ApiError(422, 'invalid_field', 'Invalid', { price: 'Too big' }))).toEqual({ price: 'Too big' });
    expect(errorFields(new ApiError(409, 'inventory.sku_taken', 'Taken', { sku: 'Taken' }))).toEqual({ sku: 'Taken' });
  });

  it('also files a nested field under its own name', () => {
    expect(errorFields(new ApiError(409, 'inventory.off_grid_quantity', 'Step', { 'items.0.qty': 'Step' }))).toEqual({
      'items.0.qty': 'Step',
      qty: 'Step',
    });
  });

  it('nothing else has fields', () => {
    expect(errorFields(new ApiError(403, 'permission_denied', 'No', { x: 'y' }))).toEqual({});
    expect(errorFields(new Error('boom'))).toEqual({});
    expect(errorFields(null)).toEqual({});
  });
});
