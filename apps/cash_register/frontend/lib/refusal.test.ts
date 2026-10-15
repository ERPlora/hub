// `refusal(error, fallback)`: what a person reads when a command of the drawer failed (a FormModal's
// `error`, a page's notice). The server's refusals arrive translated, with their 422 `fields`; a failure
// the server did not word (the network, an answer that is not the API's envelope, a 5xx) says the
// screen's own sentence («Could not close the session»), never the SDK's English.
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { refusal } from './refusal';

const FALLBACK = 'Could not close the session';

describe('refusal', () => {
  it('is nothing without an error', () => {
    expect(refusal(null, FALLBACK)).toBeNull();
    expect(refusal(undefined, FALLBACK)).toBeNull();
  });

  it('keeps the server’s sentence, its code and its fields', () => {
    const refused = new ApiError(409, 'cash_register.closing_balance_required', 'Give the counted cash to close the session.', {
      closing_balance: 'Give the counted cash to close the session.',
    });
    expect(refusal(refused, FALLBACK)).toEqual({
      message: 'Give the counted cash to close the session.',
      code: 'cash_register.closing_balance_required',
      status: 409,
      fields: { closing_balance: 'Give the counted cash to close the session.' },
    });
  });

  it('says the screen’s sentence when the server did not answer in words', () => {
    expect(refusal(new ApiError(0, 'client_error', 'Failed to fetch'), FALLBACK)).toEqual({ message: FALLBACK, code: 'client_error', status: 0 });
    expect(refusal(new ApiError(500, 'internal_error', 'Internal error'), FALLBACK)?.message).toBe(FALLBACK);
    expect(refusal(new ApiError(503, 'cash_register.x', 'Unavailable'), FALLBACK)?.message).toBe(FALLBACK);
    expect(refusal(new TypeError('boom'), FALLBACK)).toEqual({ message: FALLBACK });
  });
});
