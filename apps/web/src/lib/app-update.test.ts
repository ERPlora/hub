// Tests of the update channel of the INSTALLED app (hub#400).
//
// The three sentences this module is allowed to say are the three states of `lib/system-health.ts`,
// and the third one is the reason these tests exist: a till with no line out must end up in
// `unknown` — silent — and never in `ok` (a lie) nor in `attention` (an alarm about nothing).
//
// Node environment: `window` is stubbed, and the installed app is simulated exactly the way
// `lib/device.ts` detects it — by the presence of `window.__TAURI__.core.invoke`.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
