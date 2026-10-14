// `refusal(error, fallback)`: what a person reads when a back-office command failed. The server's
// refusals arrive translated (`sale.department_not_found`: «That department is no longer in this
// business…»), with their 422 `fields`; a failure the server did not word (the network dropped, an
// answer that is not the API's envelope) says the screen's own sentence («The quick note could not be
// saved.»).
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { refusal } from './refusal';

const FALLBACK = 'The quick note could not be saved.';

describe('refusal', () => {
  it('is nothing without an error', () => {
    expect(refusal(null, FALLBACK)).toBeNull();
    expect(refusal(undefined, FALLBACK)).toBeNull();
  });

  it('keeps the server’s sentence, its code and its fields', () => {
    const notFound = new ApiError(404, 'sale.quick_note_not_found', 'That quick note is no longer in this business. Reload the list and try again.');
    expect(refusal(notFound, FALLBACK)).toEqual({
      message: 'That quick note is no longer in this business. Reload the list and try again.',
      code: 'sale.quick_note_not_found',
      status: 404,
    });
    const invalid = new ApiError(422, 'invalid_field', 'That tax category does not exist in Taxes.', {
      tax_category_key: 'That tax category does not exist in Taxes.',
    });
    expect(refusal(invalid, FALLBACK)).toMatchObject({ message: 'That tax category does not exist in Taxes.', fields: { tax_category_key: 'That tax category does not exist in Taxes.' } });
  });

  it('says the screen’s sentence when the server did not answer in words', () => {
    expect(refusal(new ApiError(0, 'client_error', 'Failed to fetch'), FALLBACK)).toEqual({ message: FALLBACK, code: 'client_error', status: 0 });
    expect(refusal(new ApiError(502, 'unexpected_response', 'Unexpected response (HTTP 502)'), FALLBACK)?.message).toBe(FALLBACK);
    expect(refusal(new ApiError(500, 'server_error', '  '), FALLBACK)?.message).toBe(FALLBACK);
  });
});
