// @vitest-environment happy-dom
// hub#358 — the web client of the **device mode** (`GET`/`PUT /api/device/mode`, hub#357).
//
// The mode decides whether the login screen shows the pinpad, so this client is a security
// component wearing the clothes of a preference reader. Everything it does leans one way:
//
//   - **The hub answers, the browser never decides.** There is no local default worth the name
//     other than the strict one, and no cache: a mode kept in `localStorage` would be a switch
//     that removes the pinpad and that anybody holding the device can flip in devtools.
//   - **Anything that is not exactly `personal` is `shared`.** A network failure, a 500, a typo,
//     a spelling from a newer build — all of them are "the hub did not say personal", and the
//     answer to that is maximum friction, never the lax mode.
//   - **A success does not become permanent.** If a later read fails, the device goes BACK to
//     strict; otherwise a single lucky answer would outlive the trust that granted it (a revoked
//     laptop, hub#357: `untrust_device` deletes the row and the mode with it).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const resolveDeviceId = vi.fn<() => Promise<string | null>>();
vi.mock('./device', () => ({ resolveDeviceId: () => resolveDeviceId() }));
vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({ 'X-Hub-Session': 'sess-1' }) }));

import {
  DeviceModeError,
  deviceMode,
  deviceModeReady,
  loadDeviceMode,
  offersPinLogin,
  setDeviceMode,
} from './device-mode';

/** A `fetch` double answering once with `status` + `body`. */
function respondWith(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** A `fetch` double that fails the way an offline runtime does. */
function failWith(error: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockRejectedValue(error);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  resolveDeviceId.mockResolvedValue('till-1');
  deviceMode.value = 'shared';
  deviceModeReady.value = false;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('loadDeviceMode', () => {
  it('starts strict: before the hub has answered, this is a shared device', () => {
    // The window between mounting the login screen and the answer arriving is not a grey area —
    // it is a device the hub has not vouched for yet, which is exactly `shared`.
    expect(deviceMode.value).toBe('shared');
    expect(deviceModeReady.value).toBe(false);
  });

  it('asks the hub for the mode of THIS device, naming it in the header', async () => {
    const fetchMock = respondWith(200, { ok: true, data: { mode: 'personal' } });

    await loadDeviceMode();

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/device/mode');
    expect(init?.method ?? 'GET').toBe('GET');
    expect((init?.headers as Record<string, string>)['X-Device-Id']).toBe('till-1');
    expect(deviceMode.value).toBe('personal');
    expect(deviceModeReady.value).toBe(true);
  });

  it('does not cache the answer anywhere the browser could edit it', async () => {
    respondWith(200, { ok: true, data: { mode: 'personal' } });
    localStorage.clear();

    await loadDeviceMode();

    // A `personal` written to localStorage is a pinpad switch inside devtools. The hub is asked
    // every time; the cost of that is one request, and the alternative has no floor. Asserted on
    // the store itself, not on a spy: a spy on the prototype misses a write through the instance.
    expect(localStorage.length).toBe(0);
  });

  it('is shared when the runtime cannot be reached, and never throws', async () => {
    failWith(new TypeError('Failed to fetch'));

    await expect(loadDeviceMode()).resolves.toBe('shared');
    expect(deviceMode.value).toBe('shared');
  });

  it('is shared when the hub answers an error, whatever the body says', async () => {
    // The body deliberately carries a valid-looking `personal`: the status is checked FIRST, so a
    // 500 from a proxy, an error page or a half-written handler cannot lower the friction.
    respondWith(500, { ok: false, data: { mode: 'personal' }, error: { code: 'error' } });

    await expect(loadDeviceMode()).resolves.toBe('shared');
    expect(deviceMode.value).toBe('shared');
  });

  it('accepts exactly the two spellings the hub knows, and nothing near them', async () => {
    // Mirror of `DeviceMode::parse` in the runtime: the pair is CLOSED, with no trimming and no
    // case folding. Two spellings on the wire means the one that slips through is the lax one.
    for (const answer of ['Personal', 'personal ', ' personal', 'PERSONAL', 'trusted', '', null, 42]) {
      respondWith(200, { ok: true, data: { mode: answer } });
      await expect(loadDeviceMode(), `mode: ${JSON.stringify(answer)}`).resolves.toBe('shared');
    }

    respondWith(200, { ok: true, data: { mode: 'personal' } });
    await expect(loadDeviceMode()).resolves.toBe('personal');

    respondWith(200, { ok: true, data: { mode: 'shared' } });
    await expect(loadDeviceMode()).resolves.toBe('shared');
  });

  it('goes back to strict when a later read fails, instead of keeping the lax answer', async () => {
    respondWith(200, { ok: true, data: { mode: 'personal' } });
    await loadDeviceMode();
    expect(deviceMode.value).toBe('personal');

    // The trust behind `personal` can be revoked (a stolen laptop drops the row, hub#357). If the
    // last good answer survived every later failure, the browser would keep the friction off on a
    // device the hub no longer vouches for.
    failWith(new TypeError('Failed to fetch'));
    await expect(loadDeviceMode()).resolves.toBe('shared');
    expect(deviceMode.value).toBe('shared');
  });

  it('is shared when this client cannot name a device at all', async () => {
    // A browser with no device identity is the shape of the attack, not somebody's own laptop.
    resolveDeviceId.mockResolvedValue(null);
    const fetchMock = respondWith(200, { ok: true, data: { mode: 'personal' } });

    await expect(loadDeviceMode()).resolves.toBe('shared');
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('setDeviceMode', () => {
  it('names the device and the mode, and keeps the mode the SERVER confirms', async () => {
    const fetchMock = respondWith(200, { ok: true, data: { mode: 'personal' } });

    await expect(setDeviceMode('personal', 'laptop-1')).resolves.toBe('personal');

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/device/mode');
    expect(init.method).toBe('PUT');
    expect(JSON.parse(String(init.body))).toEqual({ device_id: 'laptop-1', mode: 'personal' });
    // The session is what authorises the write; the header only names a device.
    expect((init.headers as Record<string, string>)['X-Hub-Session']).toBe('sess-1');
    expect(deviceMode.value).toBe('personal');
  });

  it('without a device id it describes the device making the request', async () => {
    const fetchMock = respondWith(200, { ok: true, data: { mode: 'personal' } });

    await setDeviceMode('personal');

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ mode: 'personal' });
    expect((init.headers as Record<string, string>)['X-Device-Id']).toBe('till-1');
  });

  it('keeps the REASON of a refusal, so the admin knows what to do about it', async () => {
    respondWith(409, {
      ok: false,
      error: {
        code: 'hub.device.unknown_device',
        message: 'this hub does not know the device `laptop-9`',
      },
    });

    const refused = await setDeviceMode('personal', 'laptop-9').catch((e: unknown) => e);

    expect(refused).toBeInstanceOf(DeviceModeError);
    expect((refused as DeviceModeError).code).toBe('hub.device.unknown_device');
    expect((refused as DeviceModeError).message).toContain('laptop-9');
  });

  it('a refused write leaves the mode where it was: the screen never shows a wish', async () => {
    respondWith(200, { ok: true, data: { mode: 'personal' } });
    await setDeviceMode('personal', 'laptop-1');

    respondWith(401, { ok: false, error: 'falta la sesión' });
    await expect(setDeviceMode('shared', 'laptop-1')).rejects.toBeInstanceOf(DeviceModeError);

    expect(deviceMode.value).toBe('personal');
  });

  it('a write that answers something outside the pair is refused, not adopted', async () => {
    respondWith(200, { ok: true, data: { mode: 'Personal' } });

    await expect(setDeviceMode('personal', 'laptop-1')).rejects.toBeInstanceOf(DeviceModeError);
    expect(deviceMode.value).toBe('shared');
  });
});

describe('offersPinLogin', () => {
  it('is the whole decision: the pinpad belongs to a shared device that proved itself', () => {
    expect(offersPinLogin('shared', true)).toBe(true);
    // Somebody's own laptop signs in with the account, not with four digits typed in front of a
    // queue. That is the point of the mode.
    expect(offersPinLogin('personal', true)).toBe(false);
    // And no mode substitutes for device-trust: a PIN is only usable where an online login already
    // happened (§2.9, hub#330), so an untrusted device offers the account route and nothing else.
    expect(offersPinLogin('shared', false)).toBe(false);
    expect(offersPinLogin('personal', false)).toBe(false);
  });
});
