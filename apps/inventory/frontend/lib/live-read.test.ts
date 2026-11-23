import { ApiError } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { readFailed } from './live-read';

const FAILURE = new ApiError(502, 'unexpected_response', 'The operation could not be completed.');

describe('readFailed', () => {
  it('says an error frame, with or without an answer before it', () => {
    expect(readFailed('error', FAILURE, false)).toBe(true);
    expect(readFailed('error', FAILURE, true)).toBe(true);
  });

  it('says a failure heard before the read ever answered, while the stream tries again', () => {
    expect(readFailed('reconnecting', FAILURE, false)).toBe(true);
  });

  it('says nothing while the stream tries again over what it already answered: what is painted stays', () => {
    expect(readFailed('reconnecting', FAILURE, true)).toBe(false);
  });

  it('says nothing without a failure: loading, live, or a stream that dropped without an answer', () => {
    expect(readFailed('loading', null, false)).toBe(false);
    expect(readFailed('live', null, true)).toBe(false);
    expect(readFailed('reconnecting', null, false)).toBe(false);
  });
});
