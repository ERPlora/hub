// The headers a login carries to the Cloud: what KIND of client is signing in, and WHICH device.
//
// The two halves come from different places on purpose (hub#454). The kind is what the runtime
// reported about the deployment; the device is the shell's installation id, or — in a browser —
// the identity that browser minted for itself. The hub cannot supply the second one: the only
// stable id it owns names the *hub*, and a header saying that would make every browser one device.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { loginHeaders, setRuntimeClientKind } from './device';

/** A browser profile with nothing written down yet: the identity is minted on first use. */
function emptySiteStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
    removeItem: (key: string) => {
      data.delete(key);
    },
  };
}

afterEach(() => {
  setRuntimeClientKind(null);
  vi.unstubAllGlobals();
});

describe('machine login headers', () => {
  it('says an already provisioned Cloud machine, and names THIS browser as the device', async () => {
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', emptySiteStorage());
    setRuntimeClientKind({ clientType: 'hub-cloud', platform: 'cloud' });

    const headers = await loginHeaders();

    expect(headers['X-Client-Type']).toBe('hub-cloud');
    expect(headers['X-Device-Platform']).toBe('cloud');
    // The device is the browser's own — never the hub's id, which every browser shares and anyone
    // can read from `GET /api/hub/context`.
    expect(headers['X-Device-Id']).toMatch(/^dev_[0-9a-f]{32}$/);
  });

  it('prefers the native installation id on Windows/Android/Desktop shells', async () => {
    vi.stubGlobal('window', {
      __TAURI__: {
        core: {
          invoke: vi.fn().mockResolvedValue({
            id: 'native-device-1',
            client_type: 'hub-desktop',
            platform: 'android',
          }),
        },
      },
    });
    vi.stubGlobal('localStorage', emptySiteStorage());
    setRuntimeClientKind({ clientType: 'hub-cloud', platform: 'cloud' });

    await expect(loginHeaders()).resolves.toEqual({
      'X-Client-Type': 'hub-desktop',
      'X-Device-Id': 'native-device-1',
      'X-Device-Platform': 'android',
    });
  });

  it('is a plain `hub` client before the machine is provisioned', async () => {
    // Nothing to say about the deployment yet, so nothing is claimed about it. The device identity
    // exists all the same (the browser minted it) — it just does not travel to the Cloud here.
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', emptySiteStorage());

    await expect(loginHeaders()).resolves.toEqual({ 'X-Client-Type': 'hub' });
  });
});
