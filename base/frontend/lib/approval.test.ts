// A manager's approval on the client (BASE-G136; the old hub's HUB_SHELL-F51): `withApproval` runs a command and, when
// the hub answers `requires_elevation`, asks who approves it (the dialog) and repeats the command once with the pass in
// `X-Elevation-Token` (the SDK's `getElevationToken` reads `approvalPass`). «Cancel» hands back the original refusal; a
// second question after approving is a refusal, never a second dialog; the same command repeated while the dialog is
// open (a double tap) joins it and gets its very result, without running again; a different one is refused, not stacked.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { approvalPass, approvalQuestion, withApproval } from './approval';

const QUESTION = { operation: 'sale.sale.void', label: 'Void a sale', fingerprint: 'f'.repeat(64) };

function asksApproval(question = QUESTION): ApiError {
  return new ApiError(403, 'requires_elevation', 'This needs a manager’s approval.', undefined, { approval: question });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('withApproval', () => {
  it('a command that goes through is left alone, and nobody is asked', async () => {
    const ask = vi.fn();
    await expect(withApproval(async () => 'done', { ask })).resolves.toBe('done');
    expect(ask).not.toHaveBeenCalled();
  });

  it('a refusal of another kind is the caller’s, untouched', async () => {
    const refusal = new ApiError(403, 'permission_denied', 'No.');
    const ask = vi.fn();
    await expect(withApproval(() => Promise.reject(refusal), { ask })).rejects.toBe(refusal);
    expect(ask).not.toHaveBeenCalled();
  });

  it('asks who approves it, then repeats the command once carrying the pass, and only for that call', async () => {
    const seen: (string | undefined)[] = [];
    const run = vi.fn(async () => {
      seen.push(approvalPass());
      if (run.mock.calls.length === 1) throw asksApproval();
      return 'voided';
    });
    const ask = vi.fn(async () => 'elev_pass');
    await expect(withApproval(run, { ask })).resolves.toBe('voided');
    expect(ask).toHaveBeenCalledWith(QUESTION);
    expect(seen).toEqual([undefined, 'elev_pass']);
    expect(approvalPass()).toBeUndefined();
  });

  it('«Cancel» hands back the original refusal', async () => {
    const refusal = asksApproval();
    await expect(withApproval(() => Promise.reject(refusal), { ask: async () => null })).rejects.toBe(refusal);
  });

  it('asked again after approving, it is a refusal and no second dialog', async () => {
    const ask = vi.fn(async () => 'elev_pass');
    const again = asksApproval();
    const run = vi.fn(async () => {
      throw run.mock.calls.length === 1 ? asksApproval() : again;
    });
    await expect(withApproval(run, { ask })).rejects.toBe(again);
    expect(ask).toHaveBeenCalledTimes(1);
    expect(approvalPass()).toBeUndefined();
  });

  it('the same command repeated while the dialog is open gets its result; another one is refused, not stacked', async () => {
    let answer: (token: string | null) => void = () => {};
    const ask = vi.fn(() => new Promise<string | null>((resolve) => (answer = resolve)));
    const first = vi.fn(async () => {
      if (first.mock.calls.length === 1) throw asksApproval();
      return 'first';
    });
    const twice = vi.fn(async () => {
      if (twice.mock.calls.length === 1) throw asksApproval();
      return 'twice';
    });
    const other = asksApproval({ ...QUESTION, operation: 'sale.sale.discount', fingerprint: 'e'.repeat(64) });
    const one = withApproval(first, { ask });
    await vi.waitFor(() => expect(approvalQuestion.value?.operation).toBe('sale.sale.void'));
    const same = withApproval(twice, { ask });
    await expect(withApproval(() => Promise.reject(other), { ask })).rejects.toBe(other);
    answer('elev_pass');
    await expect(one).resolves.toBe('first');
    await expect(same).resolves.toBe('first');
    expect(twice).toHaveBeenCalledTimes(1);
    expect(first).toHaveBeenCalledTimes(2);
    expect(ask).toHaveBeenCalledTimes(1);
    expect(approvalQuestion.value).toBeNull();
  });
});
