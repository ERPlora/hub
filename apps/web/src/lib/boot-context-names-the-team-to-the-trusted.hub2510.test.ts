// @vitest-environment happy-dom
// ERPlora/hub#2510 — **the boot context names the team only to whoever the PIN door would let in**.
//
// `GET /api/hub/context` used to hand ANY caller on the internet the name and role of everybody with
// a PIN, and the hub id. The hub now answers `pin_users: []` and `hub_id: null` unless the caller
// has a live session or is a device the PIN door trusts
// (`crates/server/tests/hub_context_trusted_device_hub2510.rs` pins that half). This file pins the
// shell half:
//
// - the boot read SAYS which device is asking (`X-Device-Id`) and presents the session it holds
//   (`X-Hub-Session`): without them a trusted till would lose its grid of faces;
// - after signing in on a browser the hub did not trust yet (account form, or the panel courier),
//   the shell asks again with the new session and learns the hub id and the faces it was not given
//   at boot — the hub id is what every later call sends as `X-Hub-Id`, and the faces are what the
//   «does this person already have a PIN?» check of the login screen reads (hub#772);
// - a withheld answer never invents an identity, and a failed re-read keeps what was known.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { config } from './config';
import { resolveDeviceId } from './device';
import { bootHubContext, pinUsers, refreshHubIdentity } from './runtime';
import { setHubSession } from './session';

type Answer = { hub_id: string | null; pin_users: Array<{ id: string; name: string; role: string }> };

const MARTA = { id: 'u-marta', name: 'Marta', role: 'cashier' };

/** Stubs `fetch` with the context answer and returns the spy, to read the headers it was sent. */
function contextAnswers(answer: Answer) {
  const spy = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: true,
    status: 200,
    json: async () => ({ user: null, currency: 'EUR', language: 'es', timezone: 'UTC', ...answer }),
  }));
  vi.stubGlobal('fetch', spy);
  return spy;
}

function headersOf(spy: ReturnType<typeof contextAnswers>): Record<string, string> {
  const init = spy.mock.calls.at(-1)?.[1];
  return (init?.headers ?? {}) as Record<string, string>;
}

beforeEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  setHubSession(null);
  config.hubId = '';
  pinUsers.value = [];
});

describe('hub#2510 — the boot read says who is asking', () => {
  it('names this device, so a trusted till keeps its grid of faces', async () => {
    const spy = contextAnswers({ hub_id: 'hub-1', pin_users: [MARTA] });

    await bootHubContext();

    const device = await resolveDeviceId();
    expect(device).toBeTruthy();
    expect(headersOf(spy)['X-Device-Id']).toBe(device);
    // Nobody signed in: no session is invented.
    expect(headersOf(spy)['X-Hub-Session']).toBeUndefined();
  });

  it('presents the session it holds, so a reload behind a session keeps the hub id', async () => {
    setHubSession('sess-1', 'cloud');
    const spy = contextAnswers({ hub_id: 'hub-1', pin_users: [MARTA] });

    await bootHubContext();

    expect(headersOf(spy)['X-Hub-Session']).toBe('sess-1');
    expect(config.hubId).toBe('hub-1');
  });

  it('a withheld answer leaves the hub id unknown and the grid empty — nothing is invented', async () => {
    contextAnswers({ hub_id: null, pin_users: [] });

    await bootHubContext();

    expect(config.hubId).toBe('');
    expect(pinUsers.value).toEqual([]);
  });
});

describe('hub#2510 — after signing in, the shell learns what the boot was not told', () => {
  it('re-reads the context with the new session and publishes the hub id and the faces', async () => {
    setHubSession('sess-1', 'cloud');
    const spy = contextAnswers({ hub_id: 'hub-1', pin_users: [MARTA] });

    await refreshHubIdentity();

    expect(headersOf(spy)['X-Hub-Session']).toBe('sess-1');
    expect(config.hubId).toBe('hub-1');
    expect(pinUsers.value).toEqual([MARTA]);
  });

  it('a re-read that fails keeps what was known and never throws', async () => {
    config.hubId = 'hub-1';
    pinUsers.value = [MARTA];
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('network down');
      }),
    );

    await expect(refreshHubIdentity()).resolves.toBeUndefined();

    expect(config.hubId).toBe('hub-1');
    expect(pinUsers.value).toEqual([MARTA]);
  });

  it('a re-read that is refused keeps what was known', async () => {
    config.hubId = 'hub-1';
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));

    await refreshHubIdentity();

    expect(config.hubId).toBe('hub-1');
  });
});
