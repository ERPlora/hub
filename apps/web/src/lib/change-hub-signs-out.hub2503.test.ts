// @vitest-environment happy-dom
// hub#2503 — **«Switch business» signs out for real before the app forgets the business.**
//
// The confirmation says «This device will sign out of this business», and until now nothing was
// signed out: `forget_hub` only dropped the remembered address. The previous business's hub
// session (up to 30 days on a personal device), the person's name and email and their erplora.com
// tokens stayed in the window's storage, the hub never revoked the session, and on Android the
// «ERPlora is listening» service kept running. Whoever picked the tablet up next could open the
// previous business with a link and be inside without being asked for anything.
//
// `forget_hub` navigates the whole window, so everything has to be DONE before it is called: a
// revocation still in flight dies with the page, and once the hub is forgotten the page is no longer
// the linked business, so the native side would refuse to stop the listening (hub#2642).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeTauri, dialog, create, log } = vi.hoisted(() => {
  const dialog: { role?: string } = {};
  const log: string[] = [];
  return {
    dialog,
    log,
    invokeTauri: vi.fn(),
    create: vi.fn(async () => ({
      present: vi.fn(),
      onDidDismiss: async () => ({ role: dialog.role }),
    })),
  };
});

vi.mock('./device', () => ({
  invokeTauri: (cmd: string, args?: Record<string, unknown>) => invokeTauri(cmd, args),
  isTauri: () => true,
}));
vi.mock('@ionic/vue', () => ({ alertController: { create } }));

import { LEAVE_HUB_REVOKE_WAIT_MS, requestChangeHub, signOutAndForgetHub, type ChangeHubLabels } from './change-hub';
import { setTokens } from './cloud';
import main from '../main.ts?raw';
import { createNoticeListening, KEEP_LISTENING_COMMAND, registerNoticeListening } from './notice-listening';
import { setHubSession, setUser } from './session';

const labels: ChangeHubLabels = {
  header: 'Switch business?',
  message: 'This device will sign out of this business and show your list of businesses.',
  cancel: 'Cancel',
  confirm: 'Switch',
};

/** What a person who signed in with their account leaves in the window's storage. */
const CREDENTIAL_KEYS = ['erplora.hub_session', 'erplora.session', 'erplora.access', 'erplora.refresh'];

function storedCredentials(): string[] {
  return CREDENTIAL_KEYS.filter((k) => localStorage.getItem(k) !== null);
}

let revoke: { resolve: () => void } | null;
let leftBehindAtForget: string[] | null;

beforeEach(() => {
  localStorage.clear();
  log.length = 0;
  dialog.role = 'destructive';
  leftBehindAtForget = null;
  revoke = null;

  setUser({ id: 'u-ana', name: 'Ana', email: 'ana@example.com', role: 'admin' });
  setHubSession('sess-ana', 'cloud');
  setTokens('access-ana', 'refresh-ana');

  invokeTauri.mockReset().mockImplementation(async (cmd: string, args?: Record<string, unknown>) => {
    if (cmd === 'forget_hub') leftBehindAtForget = storedCredentials();
    log.push(cmd === KEEP_LISTENING_COMMAND ? `listening:${String(args?.on)}` : cmd);
    return null;
  });
  // The hub answers the revocation when the test says so: the forget has to wait for it.
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      if (!String(url).endsWith('/api/auth/logout')) return Promise.reject(new Error(`unexpected ${url}`));
      const session = new Headers(init?.headers).get('X-Hub-Session');
      log.push(`revoke:${session}`);
      return new Promise<Response>((resolve) => {
        revoke = {
          resolve: () => {
            log.push('revoke:done');
            resolve(new Response(null, { status: 204 }));
          },
        };
      });
    }),
  );
  // The boot registers the listening the same way (`main.ts`); this one always listens.
  registerNoticeListening(
    createNoticeListening({
      hasSomethingToTell: async () => true,
      permission: async () => 'granted',
      t: (key) => key,
      invoke: (cmd, args) => invokeTauri(cmd, args),
    }),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Lets the pending promises run until the revocation request is out. */
async function untilRevocationIsAsked(): Promise<void> {
  await vi.waitFor(() => expect(revoke).not.toBeNull());
}

describe('switching business (hub#2503)', () => {
  it('leaves no session, name, email or erplora.com token on the device when the hub is forgotten', async () => {
    const switching = requestChangeHub(labels);
    await untilRevocationIsAsked();
    revoke!.resolve();

    expect(await switching).toBe(true);
    expect(leftBehindAtForget).toEqual([]);
    expect(storedCredentials()).toEqual([]);
  });

  it('has the hub revoke the session BEFORE forgetting it — the navigation would cut the request', async () => {
    const switching = requestChangeHub(labels);
    await untilRevocationIsAsked();

    // Revocation asked with the session that is leaving, and the hub is not forgotten meanwhile.
    expect(log).toContain('revoke:sess-ana');
    expect(log).not.toContain('forget_hub');

    revoke!.resolve();
    await switching;

    expect(log.indexOf('revoke:done')).toBeLessThan(log.indexOf('forget_hub'));
  });

  it('stops listening on Android while the page is still the linked business', async () => {
    const switching = requestChangeHub(labels);
    await untilRevocationIsAsked();
    revoke!.resolve();
    await switching;

    expect(log).toContain('listening:false');
    expect(log.indexOf('listening:false')).toBeLessThan(log.indexOf('forget_hub'));
  });

  it('a hub that never answers the revocation does not keep the person from leaving', async () => {
    vi.useFakeTimers();
    const switching = requestChangeHub(labels);
    await vi.waitFor(() => expect(revoke).not.toBeNull());

    await vi.advanceTimersByTimeAsync(LEAVE_HUB_REVOKE_WAIT_MS);

    expect(await switching).toBe(true);
    expect(log).toContain('forget_hub');
    // Nothing the next person could use is left behind; the session row expires on its own.
    expect(leftBehindAtForget).toEqual([]);
  });

  it('cancelling signs nobody out and forgets nothing', async () => {
    dialog.role = 'cancel';

    expect(await requestChangeHub(labels)).toBe(false);

    expect(storedCredentials()).toEqual(CREDENTIAL_KEYS);
    expect(fetch).not.toHaveBeenCalled();
    expect(log).toEqual([]);
  });
});

// The other door that forgets the hub: the Cloud answered 410 «hub not found» (HUB_APP-F05). It
// used to forget FIRST and sign out after, so the order to stop the Android listening arrived when
// the page was no longer the linked business and the app refused it (hub#2642).
describe('forgetting a hub the Cloud says is gone (410)', () => {
  it('stops listening and signs out before forgetting, without forcing the list of businesses', async () => {
    const forgetting = signOutAndForgetHub(false);
    await untilRevocationIsAsked();
    revoke!.resolve();
    await forgetting;

    expect(log).toEqual(['listening:false', 'revoke:sess-ana', 'revoke:done', 'forget_hub']);
    expect(invokeTauri).toHaveBeenLastCalledWith('forget_hub', undefined);
    expect(leftBehindAtForget).toEqual([]);
  });

  it('is what the boot wires to the 410 — `main.ts` cannot be mounted, so this reads its source', () => {
    const start = main.indexOf('setOnHubGone(');
    const end = main.indexOf('\n});', start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const hook = main.slice(start, end);

    // Anchored to a statement at the start of a line: a commented-out `// signOutAndForgetHub(false)`
    // left next to the old forget-then-logout code would still "contain" the call (hub#2696, same trap).
    expect(hook).toMatch(/^\s*void signOutAndForgetHub\(false\)/m);
    expect(hook).not.toContain("invokeTauri('forget_hub'");
  });
});
