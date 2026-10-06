// **What a device IS when the hub is served in a browser** (hub#454).
//
// A browser has no serial number, so the only identity available is one the browser **mints for
// itself and keeps**. That makes this file the specification of a security boundary, not of a
// helper: everything the hub decides "per device" — the pinpad (hub#358), how long the session
// lives, the device-trust gate (§2.9, hub#330) — keys on the value tested here.
//
// The property that matters, and the one that was false: **two browsers against the same hub are
// two devices.** Before this, the web presented the `hub_id` as its device identity, so every
// browser in the world was the same device: marking the owner's laptop `personal` took the pinpad
// off the till at the counter, and the id that carried the whole thing was published unauthenticated
// by `GET /api/hub/context`.
//
// The identity is deliberately **client-held**: it may NAME a device, never authorise one. Which is
// why the tests below check what it survives (a tab, a reload) and what it does not (another
// browser, cleared site data, a private window) — those are the semantics the owner is promised.
import { afterEach, describe, expect, it, vi } from 'vitest';

/** The hub every browser in this file talks to. Public: `GET /api/hub/context` hands it to anyone. */
const HUB_ID = 'e5f1c0de-0000-4000-8000-000000000042';

/** Where a browser keeps the identity it minted for itself (the contract with the running fleet). */
const STORAGE_KEY = 'erplora.device_id';

/**
 * One browser profile: the site storage it keeps for this origin, and nothing else. Two of these
 * are two devices — a different browser, a different OS user, a private window, a machine that was
 * wiped. That is the whole model, and it is why "device" here means *browser profile on a machine*.
 */
function browserProfile(seed: Record<string, string> = {}) {
  const data = new Map<string, string>(Object.entries(seed));
  return {
    data,
    storage: {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => {
        data.set(key, value);
      },
      removeItem: (key: string) => {
        data.delete(key);
      },
    },
  };
}

type BrowserProfile = ReturnType<typeof browserProfile>;

// Booting a browser here means `resetModules` + re-importing the whole runtime module graph — slow
// enough under a parallel suite run that this file used to carry its own 30 s budget. It no longer
// needs one: hub#1367 made that budget global in `vite.config.ts`, because the problem was never
// this fixture but a wall-clock timeout being read as a verdict on the code. A local budget only
// hid the general case, and at 30 s it was still short enough to be killed by the fleet's load.

/** A hub context answer: what the runtime tells the shell when it boots (`/api/hub/context`). */
function hubContextResponse(machineRegistered = true) {
  return {
    ok: true,
    json: async () => ({ hub_id: HUB_ID, machine_registered: machineRegistered }),
  };
}

/**
 * Boot the web app inside `profile`, against the hub above, and read the device identity it would
 * present. `resetModules` is what makes each call a **separate browser**: module state (and with it
 * any memoised identity) starts from nothing, exactly as it does in a browser that was just opened.
 */
async function bootIn(profile: BrowserProfile, machineRegistered = true) {
  vi.resetModules();
  vi.stubGlobal('window', {});
  vi.stubGlobal('localStorage', profile.storage);
  vi.stubGlobal('fetch', vi.fn(async () => hubContextResponse(machineRegistered)));
  const { bootHubContext } = await import('./runtime');
  await bootHubContext();
  return import('./device');
}

async function deviceIdPresentedBy(profile: BrowserProfile): Promise<string | null> {
  const { resolveDeviceId } = await bootIn(profile);
  return resolveDeviceId();
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the device identity of a browser (hub#454)', () => {
  it('two browsers against the SAME hub are two devices', async () => {
    // The counter till and the owner's laptop, both pointed at the same Cloud hub. Nothing else
    // about them differs — same hub, same origin, same answer from `/api/hub/context`.
    const till = browserProfile();
    const laptop = browserProfile();

    const fromTill = await deviceIdPresentedBy(till);
    const fromLaptop = await deviceIdPresentedBy(laptop);

    expect(fromTill).toBeTruthy();
    expect(fromLaptop).toBeTruthy();
    expect(fromTill).not.toBe(fromLaptop);
  });

  it('never presents the hub id as a device: it names the hub, and every device shares it', async () => {
    // The hub id names the hub: every trusted till and every signed-in browser is told the same one
    // (hub#2510 withholds it from strangers, but not from them). An identity that every device
    // shares is not an identity.
    const browser = browserProfile();

    expect(await deviceIdPresentedBy(browser)).not.toBe(HUB_ID);
  });

  it('naming one device leaves the other one alone — id and storage', async () => {
    // The till is ALIVE and already has its identity written down. If minting one for the laptop
    // reached into it — same key, same shared value — the two would still be one device and the
    // isolation above would be passing by accident.
    const till = browserProfile({ [STORAGE_KEY]: 'dev_the-till-already-knows-who-it-is' });
    const laptop = browserProfile();

    const fromLaptop = await deviceIdPresentedBy(laptop);

    expect(till.data.get(STORAGE_KEY)).toBe('dev_the-till-already-knows-who-it-is');
    expect(fromLaptop).not.toBe(till.data.get(STORAGE_KEY));
    expect(await deviceIdPresentedBy(till)).toBe('dev_the-till-already-knows-who-it-is');
  });

  it('survives closing the tab and coming back: the same browser is the same device', async () => {
    // The gesture the promise rests on. An identity that changed on every reload would make
    // "this device is mine" (hub#357) a decision the owner had to take again every morning.
    const till = browserProfile();

    const first = await deviceIdPresentedBy(till);
    const second = await deviceIdPresentedBy(till);

    expect(second).toBe(first);
  });

  it('clearing the site data is a NEW device, not the old one coming back', async () => {
    // The honest consequence of keeping the identity in the browser, and the reason it can only
    // ever NAME a device: whoever holds the browser can drop it. What they get is a device the hub
    // has never met — the strict mode and no trust — never the standing of the one they erased.
    const browser = browserProfile();
    const before = await deviceIdPresentedBy(browser);

    browser.data.clear(); // "Forget this site" / a private window closing.

    const after = await deviceIdPresentedBy(browser);
    expect(after).toBeTruthy();
    expect(after).not.toBe(before);
  });

  it('is opaque: nothing about it is derived from the hub, the user or the moment', async () => {
    const browser = browserProfile();

    const id = await deviceIdPresentedBy(browser);

    expect(id).toMatch(/^dev_[0-9a-f-]{32,}$/);
    expect(id).not.toContain(HUB_ID);
  });

  it('a blank or padded value in storage is not a name, and a fresh one is minted', async () => {
    // Whatever wrote it — a half-finished write, a hand-edited devtools entry — blanks are not an
    // identity, and the surrounding space is not part of the name: on the wire `" x "` and `"x"`
    // would be two devices, and the hub would only ever know one of them.
    const blank = browserProfile({ [STORAGE_KEY]: '   ' });
    const padded = browserProfile({ [STORAGE_KEY]: '  dev_written-with-spaces  ' });

    expect(await deviceIdPresentedBy(blank)).toMatch(/^dev_[0-9a-f-]{32,}$/);
    expect(await deviceIdPresentedBy(padded)).toBe('dev_written-with-spaces');
  });
});

describe('what the login says about this client (hub#454)', () => {
  it('a provisioned Cloud machine says so, and names this browser', async () => {
    const browser = browserProfile();

    const { loginHeaders } = await bootIn(browser, true);

    await expect(loginHeaders()).resolves.toEqual({
      'X-Client-Type': 'hub-cloud',
      'X-Device-Id': expect.stringMatching(/^dev_[0-9a-f-]{32,}$/),
      'X-Device-Platform': 'cloud',
    });
  });

  it('a hub whose machine is not registered claims nothing about the deployment', async () => {
    // Nothing is known yet, so nothing is asserted — the browser still HAS its identity, it just
    // does not travel to the Cloud on a login that cannot be about a provisioned machine.
    const browser = browserProfile();

    const { loginHeaders, resolveDeviceId } = await bootIn(browser, false);

    await expect(loginHeaders()).resolves.toEqual({ 'X-Client-Type': 'hub' });
    await expect(resolveDeviceId()).resolves.toMatch(/^dev_[0-9a-f-]{32,}$/);
  });
});

describe('who names the device when there is a shell', () => {
  it('the installation id of the shell wins over the browser identity', async () => {
    // The shell's id lives outside the webview: it survives a cleanup of the site data, which the
    // browser's own cannot. Two ids in play means the order matters, and this is the order.
    vi.resetModules();
    vi.stubGlobal('window', {
      __TAURI__: {
        core: {
          invoke: vi.fn().mockResolvedValue({
            id: 'native-device-1',
            client_type: 'hub-desktop',
            platform: 'windows',
          }),
        },
      },
    });
    vi.stubGlobal('localStorage', browserProfile({ [STORAGE_KEY]: 'dev_the-webview-store' }).storage);
    const { resolveDeviceId } = await import('./device');

    await expect(resolveDeviceId()).resolves.toBe('native-device-1');
  });
});

describe('a browser that cannot mint or keep an identity', () => {
  it('has no identity at all rather than a guessable one', async () => {
    // No CSPRNG (`crypto` missing entirely). Falling back to something predictable would hand out
    // ids an attacker can enumerate — and device-trust and the device mode both key on this value.
    // Nothing is the safe answer: an unnamed client is answered `shared` and, under
    // `HUB_DEVICE_TRUST=enforce`, refused.
    vi.resetModules();
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', browserProfile().storage);
    vi.stubGlobal('crypto', undefined);
    const { resolveDeviceId } = await import('./device');

    await expect(resolveDeviceId()).resolves.toBeNull();
  });

  it('uses randomUUID where the browser offers it', async () => {
    vi.resetModules();
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', browserProfile().storage);
    // A secure context with `randomUUID` and nothing else: the id must come out of it.
    vi.stubGlobal('crypto', { randomUUID: () => '11111111-2222-4333-8444-555555555555' });
    const { resolveDeviceId } = await import('./device');

    await expect(resolveDeviceId()).resolves.toBe('dev_11111111222243338444555555555555');
  });

  it('falls back to getRandomValues in an insecure context, where randomUUID does not exist', async () => {
    // A hub reached over plain http on a LAN: `crypto.randomUUID` is not exposed, `getRandomValues`
    // is. Without this branch such a browser would have no identity at all — and no PIN login under
    // enforcement — for a reason that has nothing to do with it.
    vi.resetModules();
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', browserProfile().storage);
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.fill(0xab);
        return bytes;
      },
    });
    const { resolveDeviceId } = await import('./device');

    await expect(resolveDeviceId()).resolves.toBe(`dev_${'ab'.repeat(16)}`);
  });

  it('still names itself for as long as the page lives when storage is refused', async () => {
    // Safari with site data blocked, a sandboxed frame: `setItem` throws. The identity then lasts
    // one page load — which means the browser is never a *known* device, and that is fail-closed,
    // not broken.
    vi.resetModules();
    vi.stubGlobal('window', {});
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('site data is blocked');
      },
      setItem: () => {
        throw new Error('site data is blocked');
      },
      removeItem: () => {},
    });
    const { resolveDeviceId } = await import('./device');

    const first = await resolveDeviceId();
    expect(first).toBeTruthy();
    expect(await resolveDeviceId()).toBe(first);
  });
});
