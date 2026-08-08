// **The permission model of an API key** (hub#504, ADR-0057 extended).
//
// A key says what it may do the same way a user's role does: full access · read only · write only ·
// or the per-app checkboxes. The blanket modes are not sugar over the matrix — they are the only
// way to say "everything this business reads", including an app installed next month, which is
// exactly what our own read-only key needs to keep meaning.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { createApiKey, listApiKeys } from './api-keys';

function captureFetch(body: unknown): Array<{ url: string; init?: RequestInit }> {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api keys · what a key may do', () => {
  it('sends the access mode alongside the per-module matrix', async () => {
    const calls = captureFetch({ ok: true, data: { id: 'k1', secret: 'erpl_live_x' } });

    await createApiKey({ name: 'Read bot', access: 'read_only', scope: [], rate_limit_per_minute: 60 });

    const sent = JSON.parse(String(calls[0]?.init?.body));
    expect(sent.access).toBe('read_only');
    expect(sent.name).toBe('Read bot');
  });

  it('reads back the mode and the "issued by the hub" mark of each key', async () => {
    captureFetch({
      ok: true,
      data: [
        {
          id: 'k-app',
          name: 'ERPlora app',
          prefix: 'erpl_live_aaaa…',
          scope: [],
          access: 'read_only',
          system: true,
          status: 'active',
          created_at: '2026-08-08T10:00:00Z',
          last_used_at: null,
          rate_limit_per_minute: 60,
        },
      ],
    });

    const [key] = await listApiKeys();
    expect(key?.access).toBe('read_only');
    // The flag the screen needs so it does not offer a delete the hub will refuse.
    expect(key?.system).toBe(true);
  });
});
