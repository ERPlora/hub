// @vitest-environment happy-dom
// hub#456 (2/2) — **the next person takes over the till without the sale being lost**.
//
// The first half of hub#456 is done: a counter till nobody touches signs the cashier out
// (`idle-logout.ts`, hub#628 / ADR-0281). This is the other half, and it is a different gesture:
// somebody IS at the till, mid-sale, and somebody else has to take over — the shift changes, the
// manager rings the awkward one up, the queue moves to the second till.
//
// What the hub does today is the thing this file exists to stop: `login.changeUser` walks back to
// the grid of faces **outside the session**, i.e. through a sign-out, so whatever the shell was
// holding is gone. The lines of an open sale do survive (they are written on every tap, ADR-0144),
// but the screen, the route and the half-finished gesture do not — and in the sector's standard
// (Square, Toast; decision #658) taking over is a lock screen over the app, never a trip through
// the login page.
//
// So the contract pinned here is:
//
//   - **the till is never signed out.** `switchUser` mints the new session and swaps who the
//     screen attributes to; it never calls `logout()`, which would tear the shell's world down and
//     bounce the router to /login around a cashier holding a queue;
//   - **the erplora.com credentials leave with the person who leaves** (hub#1538). They are hers,
//     not the till's: her pass to the plan, the invoices and the payment methods cannot sit in the
//     box for the whole of somebody else's shift. This is the half that used to be pinned to
//     signing out — the one gesture this feature exists to avoid — so it never happened at all;
//   - **a refused PIN changes nothing at all.** The person who was signed in is still signed in,
//     and so are her credentials: a mistyped digit is not a hand-over;
//   - **the previous session dies server-side** — the point of switching is attribution, and a
//     live token for the person who walked away is the opposite of it — but only AFTER the new one
//     exists, so a failed hand-over never strands the till with no session;
//   - **preferences follow the person**, not the till: language, theme and avatar are the new
//     cashier's from the first frame;
//   - **only the counter till offers it** (`shared` + device-trust + a dial that still asks). On a
//     `personal` device there is nobody to switch to, and where the PIN is not usable the offer
//     would be a button that always fails.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { watch } from 'vue';

const runtimePinLogin = vi.fn();
const runtimeLogout = vi.fn(async (_token: string) => {});
// **The token store is deliberately NOT mocked** (hub#1538). Whether the previous person's
// erplora.com credentials really leave the till is a statement about `localStorage`, and a
// `vi.fn()` standing in for `clearTokens` can only say that a call happened — which is how this
// file used to read the opposite behaviour into the code (see «never signs the till out»). Only
// the two runtime doors are stubbed; `setTokens`/`getAccessToken`/`clearTokens` are the real ones.
vi.mock('./cloud', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./cloud')>()),
  runtimePinLogin: (name: string, pin: string) => runtimePinLogin(name, pin),
  runtimeLogout: (token: string) => runtimeLogout(token),
}));

// Adopting a session makes `setHubSession` reach for these two through a dynamic import: the
// cookie the browser fetches photos with (hub#791) and the SDK's active-module set (hub#1211).
// Neither is part of the hand-over, and with the real `./cloud` now in the graph they are no
// longer inert — left alone they fire actual requests at a runtime that is not running.
vi.mock('./runtime', () => ({
  ensureMediaCookie: vi.fn(async () => {}),
  refreshActiveModuleIds: vi.fn(async () => {}),
}));

const getUserProfile = vi.fn(async () => null);
const resetUserProfile = vi.fn();
vi.mock('./user-profile', () => ({
  getUserProfile: () => getUserProfile(),
  resetUserProfile: () => resetUserProfile(),
}));
const resetUserThemePreferences = vi.fn();
vi.mock('./theme', () => ({ resetUserThemePreferences: () => resetUserThemePreferences() }));
const resetUserLocale = vi.fn();
vi.mock('../i18n', () => ({
  resetUserLocale: () => resetUserLocale(),
  // The real `./cloud` imports this to stamp `Accept-Language` on its requests. Nothing here
  // reaches a request, but the binding has to exist for the module to load.
  getLocale: () => 'es',
}));

import {
  closeUserSwitch,
  offersUserSwitch,
  openUserSwitch,
  switchUser,
  userSwitchOffered,
  userSwitchOpen,
  userSwitchRefusalKey,
} from './user-switch';
import { deviceMode, deviceTrusted } from './device-mode';
import { pinPolicy } from './pin-policy';
import { getAccessToken, setTokens } from './cloud';
import { getHubSession, isAuthed, setHubSession, setUser, user } from './session';

/** Who was at the till before the hand-over, session token included. */
function seedCashier(): void {
  setUser({
    id: 'u-nacho',
    name: 'Nacho',
    email: 'nacho@erplora.test',
    avatarUrl: 'https://cdn.test/nacho.png',
    role: 'employee',
    permissions: ['till.sell'],
  });
  setHubSession('sess-nacho');
}

/**
 * The owner's erplora.com credentials, exactly as her password login left them in this box
 * (`setTokens`, `LoginPage.vue`). Unrelated to the till session: two planes, two credentials
 * (ADR-0003).
 */
function seedCloudLogin(): void {
  setTokens('acc-owner', 'ref-owner');
}

/** The runtime accepting four digits: a fresh session for somebody else. */
function accepts(): void {
  runtimePinLogin.mockResolvedValue({
    token: 'sess-sofia',
    user: { id: 'u-sofia', name: 'Sofía', role: 'manager' },
    permissions: ['till.sell', 'till.void_sale'],
  });
}

/** A refusal shaped like the runtime's (`RuntimeError`: prose + a stable code, or none at all). */
function refusal(code?: string): Error & { code?: string } {
  return Object.assign(new Error('nope'), code ? { code } : {});
}

/** The counter till as the hub last answered: shared, enrolled, and a dial that still asks. */
function seedCounterTill(): void {
  deviceMode.value = 'shared';
  deviceTrusted.value = true;
  pinPolicy.value = 'per_shift';
}

beforeEach(() => {
  setUser(null);
  setHubSession(null);
  closeUserSwitch();
  deviceMode.value = 'shared';
  deviceTrusted.value = false;
  pinPolicy.value = 'per_shift';
  localStorage.clear();
  runtimePinLogin.mockReset();
  runtimeLogout.mockClear();
  getUserProfile.mockClear();
  resetUserProfile.mockClear();
  resetUserThemePreferences.mockClear();
  resetUserLocale.mockClear();
});

describe('who is offered the hand-over at all', () => {
  it('offers it on a signed-in, enrolled `shared` till whose dial still asks', () => {
    expect(offersUserSwitch('shared', true, 'per_shift', true)).toBe(true);
    expect(offersUserSwitch('shared', true, 'always', true)).toBe(true);
  });

  it('never offers it on a `personal` device', () => {
    // Somebody's own laptop has one user by definition (hub#358). The gesture would have nobody to
    // switch to, and the grid of faces would publish the staff list on a device that never asks.
    expect(offersUserSwitch('personal', true, 'per_shift', true)).toBe(false);
  });

  it('never offers it where the PIN is not usable', () => {
    // Device-trust is what makes four digits work at all (§2.9, hub#330). Without it the runtime
    // answers `device_untrusted`, so the offer would be a button that cannot ever succeed.
    expect(offersUserSwitch('shared', false, 'per_shift', true)).toBe(false);
  });

  it('never offers it in a shop that decided not to identify who sells', () => {
    // `never` is the one-person shop (hub#359). Nothing to hand over, and asking would reintroduce
    // exactly the friction that dial exists to remove.
    expect(offersUserSwitch('shared', true, 'never', true)).toBe(false);
  });

  it('never offers it without a session — that is the login screen, not a hand-over', () => {
    expect(offersUserSwitch('shared', true, 'per_shift', false)).toBe(false);
  });

  it('reads the live answer of the hub, so revoking trust takes the offer away', () => {
    seedCashier();
    seedCounterTill();
    expect(userSwitchOffered.value).toBe(true);
    deviceTrusted.value = false;
    expect(userSwitchOffered.value).toBe(false);
  });
});

describe('opening the overlay', () => {
  it('opens on the counter till and closes again', () => {
    seedCashier();
    seedCounterTill();
    expect(userSwitchOpen.value).toBe(false);
    openUserSwitch();
    expect(userSwitchOpen.value).toBe(true);
    closeUserSwitch();
    expect(userSwitchOpen.value).toBe(false);
  });

  it('refuses to open where the hand-over is not offered', () => {
    // A second lock behind the hidden menu entry: a stale piece of chrome, a keyboard shortcut or
    // a module calling in must not be able to paint a grid of faces on a `personal` device.
    seedCashier();
    deviceMode.value = 'personal';
    deviceTrusted.value = true;
    openUserSwitch();
    expect(userSwitchOpen.value).toBe(false);
  });
});

describe('the hand-over itself', () => {
  it('mints the new session through the runtime and attributes the till to whoever typed', async () => {
    seedCashier();
    seedCounterTill();
    accepts();

    await switchUser('Sofía', '8317');

    expect(runtimePinLogin).toHaveBeenCalledWith('Sofía', '8317');
    expect(getHubSession()).toBe('sess-sofia');
    expect(user.value?.id).toBe('u-sofia');
    expect(user.value?.name).toBe('Sofía');
    expect(user.value?.role).toBe('manager');
    expect(user.value?.permissions).toEqual(['till.sell', 'till.void_sale']);
  });

  it('never signs the till out — the sale is still on screen', async () => {
    // The whole point. `logout()` nulls the session, so `isAuthed` goes false and the router guard
    // (`router/index.ts`) sends the app to /login: the cashier's screen, route and half-typed
    // gesture are gone.
    //
    // 🔴 This used to be pinned as `expect(clearTokens).not.toHaveBeenCalled()` — `clearTokens` as
    // a FINGERPRINT of `logout()` rather than as itself. hub#1538 showed what that costs: nobody
    // had decided to keep the previous person's erplora.com credentials on the till, yet the
    // assertion read as if somebody had, and it would have failed the fix that takes them away.
    // What was always meant is asserted directly here — the till session never blinks out, not
    // even for a single frame in the middle of the swap, and the route is untouched.
    seedCashier();
    seedCounterTill();
    seedCloudLogin();
    accepts();

    const authedDuringSwap: boolean[] = [];
    const stop = watch(isAuthed, (v) => authedDuringSwap.push(v), { flush: 'sync' });
    const routeBefore = window.location.pathname;

    await switchUser('Sofía', '8317');
    stop();

    expect(authedDuringSwap).not.toContain(false);
    expect(isAuthed.value).toBe(true);
    expect(getHubSession()).toBe('sess-sofia');
    expect(window.location.pathname).toBe(routeBefore);
  });

  it('takes the previous person’s erplora.com credentials off the till', async () => {
    // hub#1538. Handing the counter over is not «the owner is still here under another name»: her
    // pass to erplora.com — plan, invoices, payment methods — has to leave with her. Until this,
    // only signing out cleared it, and signing out is the one gesture this feature exists to
    // avoid, so the credentials sat in the box for the whole of the next person's shift.
    //
    // The runtime's own check stays where it is (`handoff_identity_mismatch`,
    // `crates/server/src/auth_api.rs`, hub#1400): that is defence in depth on the door, and the
    // door is not the same thing as not leaving the keys on the counter.
    seedCashier();
    seedCounterTill();
    seedCloudLogin();
    accepts();
    expect(getAccessToken()).toBe('acc-owner'); // the positive: the box really does hold them

    await switchUser('Sofía', '8317');

    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('erplora.refresh')).toBeNull();
  });

  it('revokes the session of the person who walked away, and only once the new one exists', async () => {
    // Attribution is the reason this feature exists: a live token for the previous cashier is a
    // second, unattended door into the till. Ordered on purpose — revoking first would leave a
    // refused PIN with nothing signed in at all.
    seedCashier();
    seedCounterTill();
    accepts();

    await switchUser('Sofía', '8317');

    expect(runtimeLogout).toHaveBeenCalledWith('sess-nacho');
    expect(runtimePinLogin.mock.invocationCallOrder[0]).toBeLessThan(
      runtimeLogout.mock.invocationCallOrder[0],
    );
  });

  it('loads the new person’s own preferences instead of inheriting the previous ones', async () => {
    // Language, theme and avatar are per-user rows (`/api/profile`). Left alone, the new cashier
    // would work under the previous one's language — and, worse, under their FACE in the sidebar,
    // which is the one thing on screen that says who this sale belongs to.
    seedCashier();
    seedCounterTill();
    accepts();

    await switchUser('Sofía', '8317');

    expect(resetUserProfile).toHaveBeenCalled();
    expect(resetUserThemePreferences).toHaveBeenCalled();
    expect(resetUserLocale).toHaveBeenCalled();
    expect(getUserProfile).toHaveBeenCalled();
    expect(user.value?.avatarUrl ?? null).toBeNull();
  });

  it('survives a hub that cannot serve the new profile', async () => {
    // The identity is already swapped by then; a 500 on `/api/profile` must not undo it or throw
    // at a cashier who is holding a queue.
    seedCashier();
    seedCounterTill();
    accepts();
    getUserProfile.mockRejectedValueOnce(new Error('profile → 500'));

    await expect(switchUser('Sofía', '8317')).resolves.toBeUndefined();
    expect(user.value?.id).toBe('u-sofia');
  });

  it('changes NOTHING when the runtime refuses the PIN', async () => {
    // A typo at a busy counter is the common case. Whoever was signed in stays signed in — an
    // attempt that logs the previous cashier out would make a mistyped digit cost the shift. And
    // «nothing» now has to be read literally, credentials included (hub#1538): a refused PIN is
    // not a hand-over, so there is nobody yet to take erplora.com away from. Asserted on the
    // store itself, not on a spy, because that is the state somebody would be robbed of.
    seedCashier();
    seedCounterTill();
    seedCloudLogin();
    runtimePinLogin.mockRejectedValue(refusal());

    await expect(switchUser('Sofía', '0000')).rejects.toThrow();

    expect(user.value?.id).toBe('u-nacho');
    expect(getHubSession()).toBe('sess-nacho');
    expect(runtimeLogout).not.toHaveBeenCalled();
    expect(getAccessToken()).toBe('acc-owner');
  });
});

describe('what a refusal is allowed to say', () => {
  it('names the gesture that fixes an unenrolled device', () => {
    expect(userSwitchRefusalKey(refusal('device_untrusted'))).toBe('userSwitch.deviceNotEnrolled');
    expect(userSwitchRefusalKey(refusal('device_unidentified'))).toBe(
      'userSwitch.deviceUnidentified',
    );
  });

  it('says «wait», not «wrong PIN», when the brute-force guard closes the door', () => {
    // Two guards, two sentences (hub#329). Telling somebody whose PIN is right to check it sends
    // them round the loop that earned the lock.
    expect(userSwitchRefusalKey(refusal('too_many_attempts'))).toBe('userSwitch.tooManyAttempts');
  });

  it('falls back to «incorrect PIN» for anything it has never seen', () => {
    // Merely unhelpful, where an instruction invented for an unknown code would be actively wrong.
    // A plain wrong PIN carries no code at all — that IS the fallback's main case.
    expect(userSwitchRefusalKey(refusal())).toBe('userSwitch.rejected');
    expect(userSwitchRefusalKey(refusal('something_new'))).toBe('userSwitch.rejected');
    expect(userSwitchRefusalKey(null)).toBe('userSwitch.rejected');
  });
});
