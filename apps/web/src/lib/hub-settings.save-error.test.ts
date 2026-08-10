// The runtime's REFUSAL has to reach the screen (hub#684).
//
// `PUT /api/settings` answers `409 {error:{code,message}}` with a message written to be read by the
// person in front of it — the demo's is *"this is a demo hub: its tax id and legal name are
// read-only — to issue real invoices, create your own hub"*. The client threw
// `Error("settings PUT → 409")` and the page painted a flat *"could not save the settings"*, so the
// one explanation the product had was dropped on the floor and the visitor read a bug.
//
// Two rules, and the second is the one that keeps this honest:
//
//  * the server's `message` travels on the thrown error, and its stable `code` with it, so a caller
//    can say WHAT happened instead of THAT something happened;
//  * a body that carries no message degrades to the status line — never to `undefined` or to an
//    empty toast, which reads as "nothing went wrong".
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { updateHubSettings } from './hub-settings';

function answer(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe('updateHubSettings carries the runtime refusal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('keeps the message the runtime wrote, so the screen can explain the demo', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        answer(409, {
          ok: false,
          error: {
            code: 'demo_fiscal_identity_locked',
            message:
              'this is a demo hub: its tax id and legal name are read-only — to issue real invoices, create your own hub',
          },
        }),
      ),
    );

    await expect(updateHubSettings({ business_tax_id: 'B12345678' })).rejects.toThrow(
      /create your own hub/,
    );
  });

  it('carries the stable code too, so a caller can branch on it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        answer(409, { ok: false, error: { code: 'demo_fiscal_identity_locked', message: 'nope' } }),
      ),
    );

    const error = await updateHubSettings({ business_tax_id: 'B1' }).catch((e) => e);
    expect((error as { code?: string }).code).toBe('demo_fiscal_identity_locked');
  });

  it('degrades to the status when the body says nothing — never to an empty message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('unreachable');
      }),
    );
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        },
      })) as unknown as typeof fetch,
    );

    await expect(updateHubSettings({ currency: 'USD' })).rejects.toThrow(/500/);
  });
});
