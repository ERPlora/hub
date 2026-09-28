// hub#1518 — the contract of the recovery, isolated from the router.
//
// A lazily-loaded view is a separate file the browser fetches when you open that screen. If that
// fetch dies mid-flight — the till hops from wifi to 4G, or the chunk went stale after a deploy —
// the router's navigation throws and, on the FIRST navigation, the app never mounts: the screen
// stays blank forever, with no message and no way out but reloading by hand. That is the failure
// the CI trace of run 33787767992 caught (`net::ERR_NETWORK_CHANGED` → `TypeError: Failed to fetch
// dynamically imported module: …/SettingsPage.vue`) and the reason the ImportPanel e2e times out
// waiting for an input that never exists.
//
// Retrying the same `import()` in place does NOT help: per the HTML module-map rules a failed
// module URL is remembered as failed, so the second call fails without touching the network. A
// fresh document is what clears it — hence a reload, once, and a visible message if even that is
// not enough.
import { describe, expect, it, vi } from 'vitest';

import {
  VIEW_LOAD_RECOVERY_KEY,
  clearViewLoadRecovery,
  isViewLoadError,
  recoverFromViewLoadError,
} from './view-load-recovery';

/** The three shapes of `Storage` this module touches, backed by a plain map. */
function fakeStorage(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    /** test-only view of what ended up stored */
    dump: () => Object.fromEntries(data),
  };
}

/** A fresh, empty in-app retry memory (hub#2312) for the cases that are not about it. */
function retryIo() {
  return { reopen: vi.fn(), failedInApp: new Set<string>(), isOnline: () => true };
}

/** The exact error Chromium hands the router when a view chunk dies mid-fetch. */
const CHUNK_ERROR = new TypeError(
  'Failed to fetch dynamically imported module: http://localhost:5173/src/views/SettingsPage.vue',
);

describe('isViewLoadError', () => {
  it('recognises the error the CI trace captured', () => {
    expect(isViewLoadError(CHUNK_ERROR)).toBe(true);
  });

  it('recognises the other wordings browsers use for the same failure', () => {
    // Firefox / Safari / Vite's own preload helper each phrase it differently; all of them mean
    // "the file that holds this screen never arrived".
    expect(isViewLoadError(new TypeError('error loading dynamically imported module'))).toBe(true);
    expect(isViewLoadError(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isViewLoadError(new Error('Unable to preload CSS for /assets/SettingsPage-a1b2.css'))).toBe(true);
  });

  it('does NOT swallow a genuine error thrown by the view itself', () => {
    // A view whose own code throws must keep surfacing as the bug it is: reloading the page over
    // and over would hide it, which is the opposite of "every error path visible".
    expect(isViewLoadError(new TypeError("Cannot read properties of undefined (reading 'id')"))).toBe(false);
    expect(isViewLoadError(new Error('boom'))).toBe(false);
    expect(isViewLoadError('Failed to fetch dynamically imported module')).toBe(false);
    expect(isViewLoadError(null)).toBe(false);
  });
});

describe('recoverFromViewLoadError · first navigation (the blank screen)', () => {
  it('reloads the document once, so the retry starts from a clean module map', () => {
    const storage = fakeStorage();
    const reload = vi.fn();

    const outcome = recoverFromViewLoadError(
      CHUNK_ERROR,
      { toPath: '/settings#data', isInitial: true },
      { storage, reload, ...retryIo() },
    );

    expect(outcome).toBe('reload');
    expect(reload).toHaveBeenCalledTimes(1);
    expect(storage.dump()[VIEW_LOAD_RECOVERY_KEY]).toBe('/settings#data');
  });

  it('does NOT reload a second time for the same path — a reload loop is worse than a blank screen', () => {
    const storage = fakeStorage({ [VIEW_LOAD_RECOVERY_KEY]: '/settings#data' });
    const reload = vi.fn();

    const outcome = recoverFromViewLoadError(
      CHUNK_ERROR,
      { toPath: '/settings#data', isInitial: true },
      { storage, reload, ...retryIo() },
    );

    expect(outcome).toBe('exhausted');
    expect(reload).not.toHaveBeenCalled();
  });

  it('still reloads when the mark belongs to a DIFFERENT screen', () => {
    // One screen that failed an hour ago must not condemn the next one to a blank page.
    const storage = fakeStorage({ [VIEW_LOAD_RECOVERY_KEY]: '/employees' });
    const reload = vi.fn();

    const outcome = recoverFromViewLoadError(
      CHUNK_ERROR,
      { toPath: '/settings#data', isInitial: true },
      { storage, reload, ...retryIo() },
    );

    expect(outcome).toBe('reload');
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('refuses to reload when the mark cannot be stored — that would be an endless reload loop', () => {
    // A browser with storage blocked cannot remember that it already tried. Reloading anyway would
    // land on the same failure, forget it again, and reload forever: a till stuck in a boot loop is
    // worse than a till showing an error. So the ladder skips straight to the visible message.
    const denied = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
      removeItem: () => {
        throw new Error('denied');
      },
    };
    const reload = vi.fn();

    expect(
      recoverFromViewLoadError(
        CHUNK_ERROR,
        { toPath: '/settings', isInitial: true },
        { storage: denied, reload, ...retryIo() },
      ),
    ).toBe('exhausted');
    expect(reload).not.toHaveBeenCalled();
  });
});

describe('recoverFromViewLoadError · navigating inside the app', () => {
  it('never reloads: the person keeps the screen (and the half-typed order) they were on', () => {
    const storage = fakeStorage();
    const reload = vi.fn();

    const outcome = recoverFromViewLoadError(
      CHUNK_ERROR,
      { toPath: '/settings#data', isInitial: false },
      { storage, reload, ...retryIo() },
    );

    // The router already aborted the navigation, so nothing goes blank — but the tap did nothing,
    // and a mute failure is not an option: the caller has to say so.
    expect(outcome).toBe('notify');
    expect(reload).not.toHaveBeenCalled();
  });
});

describe('recoverFromViewLoadError · retrying a section that failed with the app open (hub#2312)', () => {
  // The browser remembers a module URL that failed to fetch for as long as the DOCUMENT lives, so
  // tapping the section again re-runs the same `import()` and fails without touching the network —
  // measured in Chromium: second `import()` rejects with 0 new requests, a document navigation
  // fetches it fine. The toast says "try again"; the retry has to be the one that can work.
  function inApp(overrides: Partial<Parameters<typeof recoverFromViewLoadError>[2]> = {}) {
    return {
      storage: fakeStorage(),
      reload: vi.fn(),
      reopen: vi.fn(),
      failedInApp: new Set<string>(),
      isOnline: () => true,
      ...overrides,
    };
  }

  it('the first failure keeps the person where they are and only remembers the section', () => {
    const io = inApp();

    const outcome = recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings#data', isInitial: false }, io);

    expect(outcome).toBe('notify');
    expect(io.reopen).not.toHaveBeenCalled();
    expect(io.reload).not.toHaveBeenCalled();
  });

  it('asking for the same section again opens it in a fresh document', () => {
    const io = inApp();
    recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings#data', isInitial: false }, io);

    const outcome = recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings#data', isInitial: false }, io);

    expect(outcome).toBe('reopen');
    expect(io.reopen).toHaveBeenCalledTimes(1);
    expect(io.reopen).toHaveBeenCalledWith('/settings#data');
    expect(io.reload).not.toHaveBeenCalled();
  });

  it('counts the same section reached with another fragment or query as the same retry', () => {
    // The menu opens `/settings`; the failed tap may have been a deep link to `/settings#data`.
    // Both need the very same file, which is what the browser has marked as failed.
    const io = inApp();
    recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings#data', isInitial: false }, io);

    const outcome = recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings?tab=1', isInitial: false }, io);

    expect(outcome).toBe('reopen');
    expect(io.reopen).toHaveBeenCalledWith('/settings?tab=1');
  });

  it('a DIFFERENT section failing for the first time still only notifies', () => {
    // The person did not ask to retry this one: throwing away the screen they are on would lose
    // whatever they had half-typed, for a section they never tried before.
    const io = inApp();
    recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings', isInitial: false }, io);

    const outcome = recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/employees', isInitial: false }, io);

    expect(outcome).toBe('notify');
    expect(io.reopen).not.toHaveBeenCalled();
  });

  it('does not leave the app while the device says it is offline', () => {
    // A document navigation without network is the browser's own error page: in the installed app
    // or a full-screen till there is no way back from it. Staying put and saying so is better.
    const io = inApp({ isOnline: () => false });
    recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings', isInitial: false }, io);

    const outcome = recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings', isInitial: false }, io);

    expect(outcome).toBe('notify');
    expect(io.reopen).not.toHaveBeenCalled();
  });

  it('a failure that is not a missing file is never remembered as one', () => {
    const io = inApp();
    recoverFromViewLoadError(new Error('boom'), { toPath: '/settings', isInitial: false }, io);

    const outcome = recoverFromViewLoadError(CHUNK_ERROR, { toPath: '/settings', isInitial: false }, io);

    expect(outcome).toBe('notify');
    expect(io.reopen).not.toHaveBeenCalled();
  });
});

describe('recoverFromViewLoadError · anything else', () => {
  it('leaves unrelated navigation errors alone for the caller to report', () => {
    const storage = fakeStorage();
    const reload = vi.fn();

    expect(
      recoverFromViewLoadError(
        new Error('boom'),
        { toPath: '/dashboard', isInitial: true },
        { storage, reload, ...retryIo() },
      ),
    ).toBe('ignored');
    expect(reload).not.toHaveBeenCalled();
  });
});

describe('clearViewLoadRecovery', () => {
  it('forgets the mark once a navigation lands, so a later hiccup can recover too', () => {
    const storage = fakeStorage({ [VIEW_LOAD_RECOVERY_KEY]: '/settings' });

    clearViewLoadRecovery(storage);

    expect(storage.dump()[VIEW_LOAD_RECOVERY_KEY]).toBeUndefined();
  });

  it('does not throw when storage is denied', () => {
    expect(() =>
      clearViewLoadRecovery({
        getItem: () => null,
        setItem: () => {
          throw new Error('denied');
        },
        removeItem: () => {
          throw new Error('denied');
        },
      }),
    ).not.toThrow();
  });
});
