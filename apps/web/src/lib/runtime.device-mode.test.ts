// @vitest-environment happy-dom
// The module client sees the device mode the hub answered (`erplora.deviceMode`).
//
// The shell resolves the mode server-side (`GET /api/device/mode` with the NATIVE device id,
// hub#357/#358) into its reactive `deviceMode`. A module cannot ask on its own: in the installable
// app the device id is native and the runtime URL is not the page origin, so its own
// `fetch('/api/device/mode')` always degrades to `shared`. The client the shell hands to every Web
// Component must therefore carry the shell's answer — and follow it when it changes, because the
// trust behind `personal` is revocable (`untrust_device`, hub#357).
//
// First consumer: the attendance time clock (geofence only on `personal` devices).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./device', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./device')>()),
  // The native id the installable app would report (Tauri `device_context`).
  resolveDeviceId: () => Promise.resolve('phone-1'),
}));

import { deviceMode, loadDeviceMode } from './device-mode';
import { getClient } from './runtime';

/** Network-level stub: the device-mode endpoint answers `mode`; anything else never answers. */
function hubAnswersMode(answer: { status: number; mode?: unknown }) {
  const spy = vi.fn().mockImplementation((url: string) => {
    if (!String(url).includes('/api/device/mode')) return new Promise(() => {});
    return Promise.resolve({
      ok: answer.status >= 200 && answer.status < 300,
      status: answer.status,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ ok: true, data: { mode: answer.mode, trusted: true } }),
    });
  });
  vi.stubGlobal('fetch', spy);
  return spy;
}

beforeEach(() => {
  deviceMode.value = 'shared';
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('erplora.deviceMode on the module client', () => {
  it('is shared before the hub has answered (the strict mode)', () => {
    hubAnswersMode({ status: 200, mode: 'personal' });

    expect(getClient().deviceMode).toBe('shared');
  });

  it('is personal once the hub answered personal for this device', async () => {
    const spy = hubAnswersMode({ status: 200, mode: 'personal' });

    await loadDeviceMode();

    const [, init] = spy.mock.calls.find(([url]) => String(url).includes('/api/device/mode')) as [string, RequestInit];
    expect((init.headers as Record<string, string>)['X-Device-Id']).toBe('phone-1');
    expect(getClient().deviceMode).toBe('personal');
  });

  it('goes back to shared when a later answer revokes personal', async () => {
    hubAnswersMode({ status: 200, mode: 'personal' });
    await loadDeviceMode();
    expect(getClient().deviceMode).toBe('personal');

    hubAnswersMode({ status: 500 });
    await loadDeviceMode();

    expect(getClient().deviceMode).toBe('shared');
  });
});
