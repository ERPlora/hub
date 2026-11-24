import { ApiError, type ApiClient } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';

import type { PublicBookingOut } from '../operations';
import { useCancelByLink } from './useCancelByLink';

const TOKEN = 't'.repeat(43);
const CANCELLED = { number: 'APT-1', status: 'cancelled', can_cancel: false } as PublicBookingOut;

function client(answer: () => Promise<unknown>) {
  const call = vi.fn(answer);
  return { api: { call } as unknown as Pick<ApiClient, 'call'>, call };
}

describe('useCancelByLink', () => {
  it('cancels through the link with the reason and hands over the cancelled booking', async () => {
    let resolve: (value: unknown) => void = () => {};
    const { api, call } = client(() => new Promise((done) => { resolve = done; }));
    const cancelled = vi.fn();
    const link = useCancelByLink(api, () => TOKEN, cancelled);
    const running = link.cancel('I cannot make it');
    expect(link.pending.value).toBe(true);
    expect(call).toHaveBeenCalledWith('online_booking.public.cancel', { token: TOKEN, reason: 'I cannot make it' });
    resolve(CANCELLED);
    await running;
    expect(link.pending.value).toBe(false);
    expect(link.error.value).toBeNull();
    expect(cancelled).toHaveBeenCalledWith(CANCELLED);
  });

  it('keeps the refusal, hands over nothing, and forgets it on the next try', async () => {
    const refusal = new ApiError(409, 'appointment.cannot_cancel', 'This appointment can no longer be cancelled.');
    const { api, call } = client(() => Promise.reject(refusal));
    const cancelled = vi.fn();
    const link = useCancelByLink(api, () => TOKEN, cancelled);
    await link.cancel('');
    expect(link.error.value).toBe(refusal);
    expect(link.pending.value).toBe(false);
    expect(cancelled).not.toHaveBeenCalled();
    call.mockImplementationOnce(() => Promise.resolve(CANCELLED));
    await link.cancel('');
    expect(link.error.value).toBeNull();
    expect(cancelled).toHaveBeenCalledWith(CANCELLED);
  });

  it('says a failure that is not the server’s as an error too', async () => {
    const { api } = client(() => Promise.reject(new TypeError('Failed to fetch')));
    const link = useCancelByLink(api, () => TOKEN, vi.fn());
    await link.cancel('');
    expect(link.error.value).toBeInstanceOf(ApiError);
    expect(link.error.value?.message).toContain('Failed to fetch');
  });
});
