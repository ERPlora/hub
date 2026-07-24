import { afterEach, describe, expect, it, vi } from 'vitest';

import { loginHeaders, setRuntimeDeviceContext } from './device';

afterEach(() => {
  setRuntimeDeviceContext(null);
  vi.unstubAllGlobals();
});

describe('machine login headers', () => {
  it('identifies an already provisioned Cloud machine with its stable deployment id', async () => {
    vi.stubGlobal('window', {});
    setRuntimeDeviceContext({
      id: 'hub-cloud-1',
      clientType: 'hub-cloud',
      platform: 'cloud',
    });

    await expect(loginHeaders()).resolves.toEqual({
      'X-Client-Type': 'hub-cloud',
      'X-Device-Id': 'hub-cloud-1',
      'X-Device-Platform': 'cloud',
    });
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
    setRuntimeDeviceContext({
      id: 'cloud-fallback',
      clientType: 'hub-cloud',
      platform: 'cloud',
    });

    await expect(loginHeaders()).resolves.toEqual({
      'X-Client-Type': 'hub-desktop',
      'X-Device-Id': 'native-device-1',
      'X-Device-Platform': 'android',
    });
  });
});
