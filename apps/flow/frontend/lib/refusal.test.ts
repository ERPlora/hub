// What a person reads when something of Automations fails (hub#2320): the server's own sentence when it
// worded one; when it did not — the network, an answer that is not the API's, the server's own failure,
// anything that is not an API error — the screen's sentence, never «Network error (Failed to fetch)».
import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { wording } from './refusal';

const FALLBACK = 'It could not be done right now. Try again in a moment.';

describe('wording', () => {
  it('keeps the sentence the server wrote', () => {
    expect(wording(new ApiError(409, 'flow.disabled', 'This automation is paused: turn it on to run it.'), FALLBACK)).toBe(
      'This automation is paused: turn it on to run it.',
    );
    expect(wording(new ApiError(422, 'invalid_payload', 'Choose what this step must do.'), FALLBACK)).toBe('Choose what this step must do.');
  });

  it('says the screen’s sentence for what nobody worded', () => {
    expect(wording(new ApiError(0, 'network_error', 'Network error (Failed to fetch)'), FALLBACK)).toBe(FALLBACK);
    expect(wording(new ApiError(502, 'unexpected_response', 'Unexpected response (HTTP 502)'), FALLBACK)).toBe(FALLBACK);
    expect(wording(new ApiError(500, 'internal_error', 'Internal error'), FALLBACK)).toBe(FALLBACK);
    expect(wording(new ApiError(0, 'client_error', 'TypeError: x is undefined'), FALLBACK)).toBe(FALLBACK);
    expect(wording(new TypeError('Failed to fetch'), FALLBACK)).toBe(FALLBACK);
    expect(wording(new ApiError(403, 'permission_denied', ''), FALLBACK)).toBe(FALLBACK);
  });

  it('a live error frame the server worded keeps its sentence', () => {
    // The SDK hands a live query's error frame as an `ApiError` with status 0 (`LIVE_ERROR_STATUS`): the
    // server's sentence is kept the same as over HTTP; only its own breakdown says the screen's.
    expect(wording(new ApiError(0, 'permission_denied', 'You do not have permission.'), FALLBACK)).toBe('You do not have permission.');
    expect(wording(new ApiError(0, 'app_inactive', 'Automations is off.'), FALLBACK)).toBe('Automations is off.');
    expect(wording(new ApiError(0, 'internal_error', 'Internal error'), FALLBACK)).toBe(FALLBACK);
    expect(wording({ code: 'permission_denied', message: 'You do not have permission.' }, FALLBACK)).toBe('You do not have permission.');
    expect(wording({ code: 'internal_error', message: 'boom' }, FALLBACK)).toBe(FALLBACK);
  });

  it('nothing failed, nothing to say', () => {
    expect(wording(null, FALLBACK)).toBe('');
    expect(wording(undefined, FALLBACK)).toBe('');
  });
});
