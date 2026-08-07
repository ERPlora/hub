// The **online login has to say which device it happened on** (§2.9 device-trust, hub#330).
//
// Found while wiring hub#358: the hub only ever writes a `hub_trusted_device` row from
// `POST /api/auth/cloud`, and only when that request carries a `device_id` — but the web never sent
// one. The shell courier (Tauri) did; the browser did not. Two things hang off that row and both
// were dead in the browser:
//
//   - the **device mode** lives in it (hub#357), so `PUT /api/device/mode` answered
//     `hub.device.unknown_device` on a hub whose only device had signed in a hundred times;
//   - the PIN gate (`HUB_DEVICE_TRUST=enforce`) would refuse every PIN login for the same reason —
//     a guard that only holds because it is switched off by default is not a guard.
//
// The PIN login already names its device (`runtimePinLogin`). This is the same identifier on the
// login that is supposed to EARN the trust, which is the one place it was missing.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const resolveDeviceId = vi.fn<() => Promise<string | null>>();
vi.mock('./device', () => ({
  isTauri: () => false,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub' })),
  resolveDeviceId: () => resolveDeviceId(),
}));
vi.mock('./shell', () => ({ beginRequest: vi.fn(), endRequest: vi.fn() }));

import { runtimeCloudSession } from './cloud';

/** The body the runtime received, parsed. */
function bodyOf(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return JSON.parse(String(init.body)) as Record<string, unknown>;
}

function okFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ ok: true, token: 't', user: { id: 'u1', role: 'admin' } }),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  resolveDeviceId.mockResolvedValue('laptop-1');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('runtimeCloudSession', () => {
  it('names the device the online login happened on, so the hub can trust it', async () => {
    const fetchMock = okFetch();

    await runtimeCloudSession('jwt', 'Marta Ruiz', 'marta@bar.example');

    expect(bodyOf(fetchMock)).toEqual({
      name: 'Marta Ruiz',
      email: 'marta@bar.example',
      device_id: 'laptop-1',
    });
  });

  it('omits it entirely when this client cannot identify a device', async () => {
    // A `device_id: null` would be a device called "null": the field is left out, exactly as the
    // PIN login does, and the hub keeps treating the caller as an unidentified client.
    resolveDeviceId.mockResolvedValue(null);
    const fetchMock = okFetch();

    await runtimeCloudSession('jwt', 'Marta Ruiz');

    expect(bodyOf(fetchMock)).not.toHaveProperty('device_id');
  });
});
