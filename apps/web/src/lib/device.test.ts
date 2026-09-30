// The headers a login carries to the Cloud: what KIND of client is signing in, and WHICH device.
//
// The two halves come from different places on purpose (hub#454). The kind is what the runtime
// reported about the deployment; the device is the shell's installation id, or — in a browser —
// the identity that browser minted for itself. The hub cannot supply the second one: the only
// stable id it owns names the *hub*, and a header saying that would make every browser one device.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { listenTauriEvent, listenTauriPlugin, loginHeaders, setRuntimeClientKind } from './device';

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

// hub#2305 — the tap on a system notice comes back as a PLUGIN event (`actionPerformed` of the
// notification plugin), which `invoke` cannot hear. `withGlobalTauri` exposes the plugin listener
// next to `invoke`, so the shell keeps its rule of no `@tauri-apps/api` dependency.
describe('listening to a plugin event of the installed app', () => {
  it('subscribes through the Tauri global and stops through the listener it got back', async () => {
    const unregister = vi.fn(async () => {});
    const addPluginListener = vi.fn(async () => ({ unregister }));
    vi.stubGlobal('window', { __TAURI__: { core: { invoke: vi.fn(), addPluginListener } } });
    const cb = vi.fn();

    const stop = await listenTauriPlugin('notification', 'actionPerformed', cb);

    expect(addPluginListener).toHaveBeenCalledWith('notification', 'actionPerformed', cb);
    expect(stop).toBeTypeOf('function');
    stop!();
    expect(unregister).toHaveBeenCalledTimes(1);
  });

  it('is null in a browser, and in a shell whose global has no plugin listener', async () => {
    vi.stubGlobal('window', {});
    await expect(listenTauriPlugin('notification', 'actionPerformed', () => {})).resolves.toBeNull();

    vi.stubGlobal('window', { __TAURI__: { core: { invoke: vi.fn() } } });
    await expect(listenTauriPlugin('notification', 'actionPerformed', () => {})).resolves.toBeNull();
  });

  it('a refused subscription reaches the caller, who decides what it means', async () => {
    const addPluginListener = vi.fn(async () => {
      throw new Error('notification.register_listener not allowed');
    });
    vi.stubGlobal('window', { __TAURI__: { core: { invoke: vi.fn(), addPluginListener } } });

    await expect(listenTauriPlugin('notification', 'actionPerformed', () => {})).rejects.toThrow('not allowed');
  });
});

// hub#2360 — the shell's own event, not a plugin's: on the computer the shell says «a tap is
// waiting» when a notice is clicked. `withGlobalTauri` exposes the event API next to `invoke`.
describe('listening to an event of the installed app (hub#2360)', () => {
  it('subscribes through the Tauri global and stops through the function it got back', async () => {
    const unlisten = vi.fn();
    const listen = vi.fn(async () => unlisten);
    vi.stubGlobal('window', { __TAURI__: { core: { invoke: vi.fn() }, event: { listen } } });
    const cb = vi.fn();

    const stop = await listenTauriEvent('erplora://notice-tapped', cb);

    expect(listen).toHaveBeenCalledWith('erplora://notice-tapped', expect.any(Function));
    const handler = (listen.mock.calls[0] as unknown as [string, (e: unknown) => void])[1];
    handler({ event: 'erplora://notice-tapped', payload: null });
    expect(cb).toHaveBeenCalledTimes(1);
    stop!();
    expect(unlisten).toHaveBeenCalledTimes(1);
  });

  it('is null in a browser, and in a shell whose global has no event API', async () => {
    vi.stubGlobal('window', {});
    await expect(listenTauriEvent('erplora://notice-tapped', () => {})).resolves.toBeNull();

    vi.stubGlobal('window', { __TAURI__: { core: { invoke: vi.fn() } } });
    await expect(listenTauriEvent('erplora://notice-tapped', () => {})).resolves.toBeNull();
  });
});
