// hub#455 — the client of the devices door ("somebody walked off with the tablet").
//
// This module is a thin client, and the tests are about the two ways a thin client can lie to the
// person using it:
//
//   - **Reporting a revocation that did not happen.** The owner has just told the hub a device was
//     stolen. A rejection swallowed into "done" is the worst possible outcome of this screen, so
//     every non-2xx throws and carries the runtime's own reason.
//   - **Painting a device it cannot vouch for.** A row with no `device_id` cannot be revoked and
//     cannot be recognised; a `current` flag guessed client-side would put the "this is the one you
//     are holding" warning on the wrong row. Everything shown comes from the answer, and anything
//     unreadable is dropped rather than filled in.
//
// It also pins what the list is ALLOWED to be believed about: `device_id` and `label` are chosen by
// the device itself (ADR-0257 — the browser mints its own id; the label is the `name` the login
// body carried), so they are memory aids. Nothing here decides anything from them.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: 'http://runtime.test',
  runtimeHeaders: () => ({ 'X-Hub-Session': 'admin-token' }),
}));
vi.mock('./device', () => ({ resolveDeviceId: vi.fn(async () => 'dev_self') }));

import { DevicesError, listDevices, revokeDevice } from './devices';

const fetchMock = vi.fn();

function answering(status: number, body: unknown): void {
  fetchMock.mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

/** One row as the hub sends it. */
function device(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    device_id: 'dev_abc',
    label: 'Office laptop',
    trusted_at: '2026-08-01T08:00:00+00:00',
    mode: 'personal',
    mode_set_at: '2026-08-02T09:00:00+00:00',
    mode_set_by: 'u1',
    open_sessions: 1,
    last_sign_in: '2026-08-07T10:00:00+00:00',
    signed_in_until: '2026-09-06T10:00:00+00:00',
    current: false,
    ...overrides,
  };
}

describe('listDevices', () => {
  it('asks with the session AND names this device, so the hub can flag the current row', async () => {
    answering(200, { ok: true, data: { devices: [device()] } });

    await listDevices();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://runtime.test/api/devices');
    expect(init.method).toBe('GET');
    // The session is what AUTHORISES (admin, ADR-0248); the device id only NAMES (ADR-0257), and
    // it is what lets the screen warn before the owner signs themselves out.
    expect(init.headers['X-Hub-Session']).toBe('admin-token');
    expect(init.headers['X-Device-Id']).toBe('dev_self');
  });

  it('reads every signal a person needs to point at the device they lost', async () => {
    answering(200, { ok: true, data: { devices: [device({ current: true })] } });

    const [only] = await listDevices();

    expect(only).toEqual({
      deviceId: 'dev_abc',
      label: 'Office laptop',
      trustedAt: '2026-08-01T08:00:00+00:00',
      mode: 'personal',
      openSessions: 1,
      lastSignIn: '2026-08-07T10:00:00+00:00',
      signedInUntil: '2026-09-06T10:00:00+00:00',
      current: true,
    });
  });

  it('drops a row it could not identify instead of painting a button that revokes nothing', async () => {
    answering(200, {
      ok: true,
      data: { devices: [device(), { label: 'ghost' }, device({ device_id: '   ' })] },
    });

    const listed = await listDevices();

    expect(listed.map((d) => d.deviceId)).toEqual(['dev_abc']);
  });

  it('never invents a mode: anything but the two spellings is the strict one', async () => {
    // Same closed set and same direction as the runtime and `device-mode.ts`. A list that showed a
    // device as `personal` on a value the hub reads as `shared` would be a list that contradicts
    // the login screen.
    answering(200, {
      ok: true,
      data: {
        devices: [
          device({ device_id: 'a', mode: 'Personal' }),
          device({ device_id: 'b', mode: undefined }),
          device({ device_id: 'c', mode: 'personal' }),
        ],
      },
    });

    const listed = await listDevices();

    expect(listed.map((d) => d.mode)).toEqual(['shared', 'shared', 'personal']);
  });

  it('a refusal is a refusal, with the hub reason attached', async () => {
    answering(401, { ok: false, error: 'se requiere rol owner/admin para gestionar el Hub' });

    await expect(listDevices()).rejects.toBeInstanceOf(DevicesError);
  });

  it('an unreadable answer is not an empty business', async () => {
    // `{}` and a 200 with no list are not "this business has no devices": showing an empty list
    // there would tell an owner looking for a stolen tablet that there is nothing to revoke.
    answering(200, { ok: true, data: {} });
    await expect(listDevices()).rejects.toBeInstanceOf(DevicesError);

    fetchMock.mockRejectedValue(new Error('offline'));
    await expect(listDevices()).rejects.toBeInstanceOf(DevicesError);
  });
});

describe('revokeDevice', () => {
  it('names the device in the path and identifies the one it is asking from', async () => {
    answering(200, {
      ok: true,
      data: { device_id: 'dev_abc', was_known: true, sessions_closed: 1, was_current: false },
    });

    const outcome = await revokeDevice('dev_abc');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://runtime.test/api/devices/dev_abc');
    expect(init.method).toBe('DELETE');
    expect(init.headers['X-Device-Id']).toBe('dev_self');
    expect(outcome).toEqual({ wasKnown: true, sessionsClosed: 1, wasCurrent: false });
  });

  it('escapes the id: it is a string the device chose, not a path', async () => {
    answering(200, {
      ok: true,
      data: { device_id: 'a/b', was_known: true, sessions_closed: 0, was_current: false },
    });

    await revokeDevice('a/b');

    // Without encoding, an id with a slash would address a different route (or none) and the owner
    // would be told a device was cut off while it kept working.
    expect(fetchMock.mock.calls[0][0]).toBe('http://runtime.test/api/devices/a%2Fb');
  });

  it('refuses to call at all without a device to name', async () => {
    await expect(revokeDevice('   ')).rejects.toBeInstanceOf(DevicesError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('a rejection reaches the screen instead of looking like success', async () => {
    answering(401, { ok: false, error: 'sesión inválida o caducada' });

    // This is the one that matters: the owner has just said "this was stolen". Being told it worked
    // when it did not is worse than any error message.
    await expect(revokeDevice('dev_abc')).rejects.toThrow(/sesión inválida/);
  });

  it('says when the device just cut off was the one in the owner hands', async () => {
    answering(200, {
      ok: true,
      data: { device_id: 'dev_self', was_known: true, sessions_closed: 1, was_current: true },
    });

    const outcome = await revokeDevice('dev_self');

    // The screen needs this to send them to the login rather than leave them tapping a dead session.
    expect(outcome.wasCurrent).toBe(true);
  });
});
