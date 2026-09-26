// Tests of the update channel of the INSTALLED app (hub#400).
//
// The three sentences this module is allowed to say are the three states of `lib/system-health.ts`,
// and the third one is the reason these tests exist: a till with no line out must end up in
// `unknown` — silent — and never in `ok` (a lie) nor in `attention` (an alarm about nothing).
//
// Node environment: `window` is stubbed, and the installed app is simulated exactly the way
// `lib/device.ts` detects it — by the presence of `window.__TAURI__.core.invoke`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// `toast.ts` reaches for Ionic's `toastController`, which needs a document. The notice itself is
// asserted through `localStorage` (said once per version) and in the component's own suite; what
// this stub buys is that the announcement path really RUNS here instead of being skipped.
const toastInfo = vi.hoisted(() => vi.fn());
vi.mock('./toast', () => ({ toastInfo, toastError: vi.fn(), toastSuccess: vi.fn(), toast: vi.fn() }));

import {
  APP_VERSION_COMMAND,
  appDownloadUrl,
  checkAppUpdate,
  downloadPlatform,
  isNewerVersion,
  parseVersion,
} from './app-update';

/** A shell that answers `plugin:app|version` with `version` and every other command with `null`. */
function installedApp(version: string | Error): { invoke: ReturnType<typeof vi.fn> } {
  const invoke = vi.fn(async (command: string) => {
    if (command !== APP_VERSION_COMMAND) return null;
    if (version instanceof Error) throw version;
    return version;
  });
  vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });
  return { invoke };
}

/** The runtime answers `GET /api/app/release` with `body` under `status`. */
function cloudSays(status: number, body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.stubGlobal('localStorage', {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('parseVersion', () => {
  it('reads the three numbers of a release', () => {
    expect(parseVersion('1.2.3')).toEqual([1, 2, 3]);
  });

  it('accepts the `v` the git tag carries', () => {
    expect(parseVersion('v1.2.3')).toEqual([1, 2, 3]);
  });

  it('reads numbers as NUMBERS, not as text', () => {
    // `'10' < '9'` as text. A release that reads its own version alphabetically stops offering
    // updates at x.9 forever, and nothing in the product says anything is wrong.
    expect(parseVersion('1.10.0')).toEqual([1, 10, 0]);
  });

  it.each([
    ['1.2', 'two numbers is not a release of ours'],
    ['1.2.3.4', 'four is not either'],
    ['1.2.3-beta.1', 'a pre-release is not a version we publish'],
    ['1.2.x', 'a placeholder is not a number'],
    ['latest', 'the name of a folder is not a version'],
    ['', 'nothing at all'],
    ['  ', 'blanks'],
  ])('refuses %j — %s', (raw) => {
    // Refusing is what produces `unknown` upstream. Guessing here is how a till would be told to
    // update to something that does not exist.
    expect(parseVersion(raw)).toBeNull();
  });

  it('ignores the blanks a hand-edited manifest can carry', () => {
    expect(parseVersion(' 1.2.3\n')).toEqual([1, 2, 3]);
  });

  it('refuses null and undefined without throwing', () => {
    expect(parseVersion(null)).toBeNull();
    expect(parseVersion(undefined)).toBeNull();
  });
});

describe('isNewerVersion', () => {
  it('says yes only when the published one is STRICTLY greater', () => {
    expect(isNewerVersion('1.2.4', '1.2.3')).toBe(true);
    expect(isNewerVersion('1.3.0', '1.2.9')).toBe(true);
    expect(isNewerVersion('2.0.0', '1.99.99')).toBe(true);
  });

  it('says no when they are the same', () => {
    expect(isNewerVersion('1.2.3', '1.2.3')).toBe(false);
    expect(isNewerVersion('v1.2.3', '1.2.3')).toBe(false);
  });

  it('says no when the installed one is AHEAD', () => {
    // A machine running a build newer than `latest/` is a developer's, and telling them to
    // "update" to an older installer is how you downgrade a till.
    expect(isNewerVersion('1.2.3', '1.2.4')).toBe(false);
    expect(isNewerVersion('1.9.0', '1.10.0')).toBe(false);
  });

  it('compares number by number, not letter by letter', () => {
    expect(isNewerVersion('1.10.0', '1.9.0')).toBe(true);
    expect(isNewerVersion('0.2.0', '0.10.0')).toBe(false);
  });

  it('says no when either side is not a version it understands', () => {
    expect(isNewerVersion('1.2.4', null)).toBe(false);
    expect(isNewerVersion(null, '1.2.3')).toBe(false);
    expect(isNewerVersion('nope', '1.2.3')).toBe(false);
    expect(isNewerVersion('1.2.4', 'nope')).toBe(false);
  });
});

describe('downloadPlatform', () => {
  it('names the three the Cloud serves', () => {
    expect(downloadPlatform('windows')).toBe('windows');
    expect(downloadPlatform('linux')).toBe('linux');
    expect(downloadPlatform('android')).toBe('android');
  });

  it('has nowhere to send macOS, and says so instead of inventing a link', () => {
    // macOS is built locally only — there is no Apple Developer ID cert, so the Cloud publishes no
    // macOS installer. A button pointing at a 404 is the mute failure this whole issue is about.
    expect(downloadPlatform('macos')).toBeNull();
  });

  it('has nowhere to send a platform it does not know', () => {
    expect(downloadPlatform(undefined)).toBeNull();
    expect(downloadPlatform('cloud')).toBeNull();
    expect(downloadPlatform('desktop')).toBeNull();
  });
});

describe('appDownloadUrl', () => {
  it('points at the CLOUD, which decides the channel — never at a versioned file', () => {
    // Two reasons it is the Cloud and not the bucket: the Cloud is what redirects to the STORE the
    // day a listing goes live (`store_url_for`), and it is an address the shell will open
    // (`external_browser_url` accepts the apex; a signed Object Storage URL it would refuse).
    expect(appDownloadUrl('windows')).toBe('https://erplora.com/app/download/windows/');
    expect(appDownloadUrl('android')).toBe('https://erplora.com/app/download/android/');
  });

  it('carries no version in the address', () => {
    // The whole of point 1 of hub#400: a page that cached `v1.2.3` keeps handing out 1.2.3 forever.
    expect(appDownloadUrl('linux')).not.toMatch(/\d+\.\d+\.\d+/);
  });
});

describe('checkAppUpdate', () => {
  it('does not even ask in a browser: there is no installed app to update', async () => {
    const fetchMock = cloudSays(200, { version: '9.9.9' });
    vi.stubGlobal('window', {});

    const update = await checkAppUpdate();

    expect(update.state).toBe('unknown');
    expect(update.installed).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports an update when the Cloud publishes a newer one', async () => {
    installedApp('1.2.3');
    cloudSays(200, { version: '1.3.0' });

    const update = await checkAppUpdate();

    expect(update).toEqual({ state: 'attention', installed: '1.2.3', latest: '1.3.0' });
  });

  it('reports up to date when they match', async () => {
    installedApp('1.2.3');
    cloudSays(200, { version: '1.2.3' });

    expect((await checkAppUpdate()).state).toBe('ok');
  });

  it('asks the runtime, same origin — never the Cloud directly', async () => {
    // The page is served under `connect-src 'self' ipc:`: a fetch straight to erplora.com is killed
    // by the CSP, and it would be killed silently.
    installedApp('1.2.3');
    const fetchMock = cloudSays(200, { version: '1.2.3' });

    await checkAppUpdate();

    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toBe('/api/app/release');
  });

  it('asks the shell for the version with the command the ACL already grants', async () => {
    const { invoke } = installedApp('1.2.3');
    cloudSays(200, { version: '1.2.3' });

    await checkAppUpdate();

    // The literal, not the constant: `core:default` — already granted to the hub PWA — carries
    // `core:app:allow-version`, and that is the ONLY reason an app installed BEFORE this feature
    // can answer at all. Asserting against the constant would rename in lockstep and pass while
    // every till already in the field went silent.
    expect(invoke).toHaveBeenCalledWith('plugin:app|version', undefined);
  });

  it('stays quiet when there is no network — it does not know, and it does not throw', async () => {
    installedApp('1.2.3');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );

    const update = await checkAppUpdate();

    expect(update.state).toBe('unknown');
    expect(update.latest).toBeNull();
    // `installed` is still known: it came from the shell, not from the network.
    expect(update.installed).toBe('1.2.3');
  });

  it('stays quiet when the Cloud answers an error', async () => {
    installedApp('1.2.3');
    cloudSays(502, { ok: false, error: 'bad gateway' });

    expect((await checkAppUpdate()).state).toBe('unknown');
  });

  it('stays quiet when the answer is not a version', async () => {
    installedApp('1.2.3');
    cloudSays(200, { version: null });

    expect((await checkAppUpdate()).state).toBe('unknown');
  });

  it('stays quiet when the answer is not even JSON', async () => {
    installedApp('1.2.3');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected token <');
        },
      })),
    );

    expect((await checkAppUpdate()).state).toBe('unknown');
  });

  it('stays quiet when the shell will not say which version it is', async () => {
    // An app built before this feature, or one whose capability lost `core:default`. It cannot
    // compare, so it says nothing — the one thing it must not do is claim to be up to date.
    installedApp(new Error('command plugin:app|version not allowed'));
    cloudSays(200, { version: '9.9.9' });

    const update = await checkAppUpdate();

    expect(update.state).toBe('unknown');
    expect(update.installed).toBeNull();
  });

  it('never says `ok` when it could not check', async () => {
    installedApp(new Error('nope'));
    cloudSays(200, { version: '1.2.3' });

    expect((await checkAppUpdate()).state).not.toBe('ok');
  });
});

describe('refreshAppUpdate', () => {
  /** The shell also answers `device_context`, which is how the destination gets resolved. */
  function installedAppOn(platform: string, version: string): void {
    const invoke = vi.fn(async (command: string) => {
      if (command === APP_VERSION_COMMAND) return version;
      if (command === 'device_context') {
        return { id: 'dev_1', clientType: 'hub-desktop', platform };
      }
      return null;
    });
    vi.stubGlobal('window', { __TAURI__: { core: { invoke } } });
  }

  /** A session that may administer, so the offer is this session's to act on (ADR-0248). */
  async function signInAdministrator(): Promise<void> {
    const { setUser } = await import('./session');
    setUser({
      id: 'u1',
      name: 'Owner',
      email: 'owner@example.com',
      role: 'owner',
      permissions: ['hub.administer'],
    });
  }

  beforeEach(async () => {
    const { appUpdate, appUpdateDestination, appUpdatePlatform } = await import('./app-update');
    appUpdate.value = { state: 'unknown', installed: null, latest: null };
    appUpdateDestination.value = null;
    appUpdatePlatform.value = null;
    const { setUser } = await import('./session');
    setUser(null);
  });

  it('publishes both halves of the offer: the verdict AND where to go', async () => {
    // Without the destination the entry never paints, so "there is an update" would be a fact the
    // product knows and cannot act on.
    installedAppOn('windows', '1.2.3');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    const { refreshAppUpdate, appUpdate, appUpdateDestination } = await import('./app-update');
    await refreshAppUpdate();

    expect(appUpdate.value.state).toBe('attention');
    expect(appUpdateDestination.value).toBe('https://erplora.com/app/download/windows/');
  });

  it('says which platform the offer is for, so the notice can speak its language (hub#1898)', async () => {
    // An APK installed by hand is sent to the Cloud's Android page, which hands it to Google Play:
    // there is no file to download there, and the confirmation must not promise one.
    installedAppOn('android', '1.2.3');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    const { refreshAppUpdate, appUpdateDestination, appUpdatePlatform } = await import('./app-update');
    await refreshAppUpdate();

    expect(appUpdateDestination.value).toBe('https://erplora.com/app/download/android/');
    expect(appUpdatePlatform.value).toBe('android');
  });

  it('keeps the desktop platform for a desktop offer', async () => {
    installedAppOn('windows', '1.2.3');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    const { refreshAppUpdate, appUpdatePlatform } = await import('./app-update');
    await refreshAppUpdate();

    expect(appUpdatePlatform.value).toBe('windows');
  });

  it('forgets the platform when there is nothing to offer', async () => {
    const { refreshAppUpdate, appUpdatePlatform } = await import('./app-update');
    appUpdatePlatform.value = 'android';
    installedAppOn('android', '1.4.0');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    await refreshAppUpdate();

    expect(appUpdatePlatform.value).toBeNull();
  });

  it('does not look for a destination when there is nothing to offer', async () => {
    installedAppOn('windows', '1.4.0');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    const { refreshAppUpdate, appUpdate, appUpdateDestination } = await import('./app-update');
    await refreshAppUpdate();

    expect(appUpdate.value.state).toBe('ok');
    expect(appUpdateDestination.value).toBeNull();
  });

  it('has nowhere to send a macOS build, and says so by leaving the destination empty', async () => {
    const announced: string[] = [];
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: (key: string, value: string) => {
        if (key === 'erplora.app_update.announced') announced.push(value);
      },
      removeItem: () => undefined,
    });
    installedAppOn('macos', '1.2.3');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    const { refreshAppUpdate, appUpdate, appUpdateDestination } = await import('./app-update');
    await refreshAppUpdate();

    // The verdict is still honest — there IS a newer one — but there is no button, because there is
    // no macOS installer to point at.
    expect(appUpdate.value.state).toBe('attention');
    expect(appUpdateDestination.value).toBeNull();
    // And nothing is said either: announcing an update the user cannot get is a notice with no way
    // out of it, which is the shape of every mute failure this issue exists to end.
    expect(announced).toEqual([]);
  });

  it('says it out loud ONCE per version, not on every six-hour round', async () => {
    // A toast every six hours is how people learn to dismiss the till without reading it.
    const announced: string[] = [];
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => (key === 'erplora.app_update.announced' ? (announced.at(-1) ?? null) : null),
      setItem: (key: string, value: string) => {
        if (key === 'erplora.app_update.announced') announced.push(value);
      },
      removeItem: () => undefined,
    });
    installedAppOn('windows', '1.2.3');
    cloudSays(200, { version: '1.4.0' });
    await signInAdministrator();

    const { refreshAppUpdate } = await import('./app-update');
    await refreshAppUpdate();
    await refreshAppUpdate();
    await refreshAppUpdate();

    expect(announced).toEqual(['1.4.0']);
  });

  it('says nothing to whoever is on shift — it is not their task', async () => {
    // ADR-0248 again, and it has to hold for the toast as well: filtering the entry away while
    // still interrupting the same person with a notice would be the worst of both.
    const announced: string[] = [];
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: (key: string, value: string) => {
        // Only the announcement key: `setUser` also writes the session, and a stub that recorded
        // everything would make "nothing was said" pass for the wrong reason.
        if (key === 'erplora.app_update.announced') announced.push(value);
      },
      removeItem: () => undefined,
    });
    installedAppOn('windows', '1.2.3');
    cloudSays(200, { version: '1.4.0' });
    const { setUser } = await import('./session');
    setUser({ id: 'u2', name: 'Ana', email: 'ana@example.com', role: 'employee', permissions: [] });

    const { refreshAppUpdate, appUpdate } = await import('./app-update');
    await refreshAppUpdate();

    expect(appUpdate.value.state).toBe('attention');
    expect(announced).toEqual([]);
  });

  it('says nothing when it could not check', async () => {
    const announced: string[] = [];
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: (key: string, value: string) => {
        // Only the announcement key: `setUser` also writes the session, and a stub that recorded
        // everything would make "nothing was said" pass for the wrong reason.
        if (key === 'erplora.app_update.announced') announced.push(value);
      },
      removeItem: () => undefined,
    });
    installedAppOn('windows', '1.2.3');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('Failed to fetch');
      }),
    );
    await signInAdministrator();

    const { refreshAppUpdate, appUpdate } = await import('./app-update');
    await refreshAppUpdate();

    expect(appUpdate.value.state).toBe('unknown');
    expect(announced).toEqual([]);
  });
});

// ── hub#757: a build that came from a STORE must not point at a download ───────────────────────
//
// Google Play forbids an app it distributed from fetching an APK anywhere else, and Microsoft
// updates its own installs too. The notice itself is not the problem — pointing a Play install at
// `/app/download/android/` is, and a reviewer opening the app is exactly who finds it.
//
// The signal has to come from the SHELL and not from a build flag of this bundle: the web app is
// served by the hub, so one bundle answers every install at once (ADR-0154/0159) and could never
// tell a Play install from a sideloaded one. `distribution` travels in the device context, which
// the shell fills at compile time — the only place that knows where the binary came from.
describe('updateDestination and the distribution channel (hub#757)', () => {
  /** A shell that reports itself as `platform`, installed through `distribution`. */
  function shellFrom(platform: string, distribution: string) {
    vi.stubGlobal('window', {
      __TAURI__: {
        core: {
          invoke: vi.fn(async (command: string) =>
            command === 'device_context'
              ? { id: 'device-1', clientType: 'hub-desktop', platform, distribution }
              : null,
          ),
        },
      },
    });
  }

  it('sends a DIRECT install to its download, because nobody else will update it', async () => {
    shellFrom('linux', 'direct');
    const { updateDestination } = await import('./app-update');
    expect(await updateDestination()).toContain('/app/download/linux/');
  });

  it('sends NOWHERE an install that came from Google Play', async () => {
    shellFrom('android', 'play');
    const { updateDestination } = await import('./app-update');
    expect(await updateDestination()).toBeNull();
  });

  it('sends NOWHERE an install that came from the Microsoft Store', async () => {
    shellFrom('windows', 'msstore');
    const { updateDestination } = await import('./app-update');
    expect(await updateDestination()).toBeNull();
  });

  it('treats a shell that says nothing as a direct install, so an old build keeps its notice', async () => {
    shellFrom('windows', undefined as unknown as string);
    const { updateDestination } = await import('./app-update');
    expect(await updateDestination()).toContain('/app/download/windows/');
  });
});
