// `refusal(error, fallback)`: what a person reads when a command of the sale app failed (a FormModal's
// `error`, a window's or a page's notice). The server's refusals arrive translated
// (`sale.department_not_found`: «That section is no longer in this business…»), with their 422
// `fields`; a failure the server did not word (the network dropped, an answer that is not the API's
// envelope, something that is not an API error at all) says the screen's own sentence («The quick note
// could not be saved.»), never the SDK's English.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
    expect(refusal(new ApiError(0, 'network_error', 'Network error (Failed to fetch)'), FALLBACK)).toEqual({ message: FALLBACK, code: 'network_error', status: 0 });
  });

  it('a failure of the server itself is not a refusal: `internal_error` (the API’s «Internal error», the live executor’s English «The live query failed.») and any 5xx say the screen’s sentence', () => {
    expect(refusal(new ApiError(500, 'internal_error', 'Internal error'), FALLBACK)).toEqual({ message: FALLBACK, code: 'internal_error', status: 500 });
    expect(refusal(new ApiError(0, 'internal_error', 'The live query failed.'), FALLBACK)?.message).toBe(FALLBACK);
    expect(refusal(new ApiError(503, 'sale.something', 'Service unavailable'), FALLBACK)?.message).toBe(FALLBACK);
    expect(refusal(new ApiError(409, 'sale.order_changed', 'The check changed.'), FALLBACK)?.message).toBe('The check changed.');
  });

  it('anything that is not an API error says the screen’s sentence', () => {
    expect(refusal(new TypeError('boom'), FALLBACK)).toEqual({ message: FALLBACK });
    expect(refusal('boom', FALLBACK)).toEqual({ message: FALLBACK });
  });
});

describe('one refusal helper in the app', () => {
  it('no other source of the sale app defines its own `refusal`', () => {
    const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..');
    const sources = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) return entry.name === '__tests__' ? [] : sources(path);
        return /\.(vue|ts)$/.test(entry.name) && !/\.(test|d)\.ts$/.test(entry.name) ? [path] : [];
      });
    const defining = sources(FRONTEND)
      .filter((file) => /export function refusal\b/.test(readFileSync(file, 'utf8')))
      .map((file) => file.slice(FRONTEND.length));
    expect(defining).toEqual(['/lib/refusal.ts']);
  });
});
