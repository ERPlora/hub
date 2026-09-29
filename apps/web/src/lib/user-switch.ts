// **Quick user switch on a shared till** (hub#456, 2/2) — the next person takes over WITHOUT the
// sale being lost.
//
// The other half of hub#456 already ships: a counter till nobody touches signs the cashier out
// (`idle-logout.ts`, hub#628 / ADR-0281). This is the deliberate hand-over — the shift changes, a
// manager rings the awkward one up, the queue moves — and it is a different gesture, because
// somebody is at the till right now, mid-sale.
//
// Until this file, the only way to change operator was `login.changeUser`: back to the grid of
// faces **outside the session**, i.e. through a sign-out. The lines of an open sale survive that
// (they are written on every tap, ADR-0144), but the screen, the route and the half-finished
// gesture do not. In the sector's standard — Square, Toast; decision #658 — taking over is a lock
// screen ON TOP of the app: the other employee types their PIN and the sale carries on where it
// was, attributed to them from that moment.
//
// So what happens here is a **session swap, never a sign-out**:
//
//   - the new session is minted first (`POST /api/auth/pin`, exactly the login screen's door — the
//     plate and the PIN are the same identity, and this module invents no second one);
//   - only then is the previous token revoked, because a refused PIN must leave the till exactly as
//     it was, not signed out of everything;
//   - `logout()` is never called. It tears the shell's world down — the assistant, the entitlement,
//     the profile — and bounces to `/login`, the very loss this feature exists to avoid;
//   - the **cloud credentials are cleared on their own** (hub#1538). They belong to the PERSON, not
//     to the till, and until this they only ever left through `logout()` — i.e. never, here. That
//     is the separation this module was missing: forgetting erplora.com and throwing somebody off
//     the TPV used to be a single gesture, and only one of the two is wanted;
//   - the **assistant conversation leaves with her too** (hub#1544), and for the same reason and by
//     the same route: it is hers, it was pinned to that same sign-out, and it is the one piece of
//     the previous shift the next person can sit and READ;
//   - the per-user preferences (language, theme, avatar) are re-read for the person who just
//     arrived, so the sidebar stops showing the face of the one who left.
//
// **Only the counter till is offered this.** The gate is the same AND as the login pinpad's
// (`offersPinLogin`): `shared`, device-trusted, and a dial that still asks. Not offering it never
// grants anything — what remains is signing out and back in, which is strictly stronger.
import { computed, ref } from 'vue';

import { deviceMode, deviceTrusted, type DeviceMode } from './device-mode';
import { asksForPin, pinPolicy, type PinPolicy } from './pin-policy';
import { clearTokens, runtimeLogout, runtimePinLogin } from './cloud';
import { clearAssistantHistory } from './assistant-history';
import { getHubSession, isAuthed, setHubSession, setUser } from './session';
import { getUserProfile, resetUserProfile } from './user-profile';
import { resetUserThemePreferences } from './theme';
import { resetUserLocale } from '../i18n';
import { lockRefusal, type Refusal } from './lock-refusal';

/**
 * Does this device get the hand-over gesture at all?
 *
 * The same three conditions as the login pinpad, and for the same reasons: `shared` is what makes
 * several people at one device a real situation (hub#358); device-trust is what makes four digits
 * usable at all (§2.9, hub#330) — without it the runtime answers `device_untrusted`, so the offer
 * would be a button that can only fail; and `never` is the one-person shop that decided not to
 * identify who sells (hub#359), where there is nothing to hand over.
 *
 * Plus a session: with nobody signed in this is the login screen, not a hand-over.
 *
 * All four parameters are required on purpose — a default would let a caller keep an older, blinder
 * behaviour by simply not knowing about one of them.
 */
export function offersUserSwitch(
  mode: DeviceMode,
  trusted: boolean,
  policy: PinPolicy,
  authed: boolean,
): boolean {
  return authed && mode === 'shared' && trusted && asksForPin(policy);
}

/** {@link offersUserSwitch} against the hub's live answer — what the shell's menu entry reads. */
export const userSwitchOffered = computed<boolean>(() =>
  offersUserSwitch(deviceMode.value, deviceTrusted.value, pinPolicy.value, isAuthed.value),
);

/** Is the hand-over overlay on screen? `UserSwitchOverlay` renders it; nothing else writes it. */
export const userSwitchOpen = ref(false);

/**
 * Show the overlay — **if this device is offered the gesture at all**.
 *
 * The check is deliberately repeated here and not left to the menu entry that hides itself. A grid
 * of the shop's faces is a small staff directory; a stale piece of chrome, a keyboard shortcut or a
 * module calling in must not be able to paint it on somebody's personal laptop.
 */
export function openUserSwitch(): void {
  if (!userSwitchOffered.value) return;
  userSwitchOpen.value = true;
}

/** Take the overlay away. Idempotent: the backdrop, the button and a successful swap all land here. */
export function closeUserSwitch(): void {
  userSwitchOpen.value = false;
}

/**
 * Hand the till over to `name`, verified by `pin`.
 *
 * Throws whatever the runtime refused with (see {@link userSwitchRefusal}) and, when it does,
 * **nothing has changed**: the person who was signed in still is, with their session token intact.
 *
 * The order is the contract. Mint → adopt → revoke the old one → forget erplora.com → re-read the
 * arriving person's preferences. Revoking first would mean a mistyped digit costs the shift;
 * revoking not at all would leave a live, unattended session for whoever just walked away, which
 * defeats the attribution this whole gesture is for.
 */
export async function switchUser(name: string, pin: string): Promise<void> {
  const previous = getHubSession();
  const session = await runtimePinLogin(name, pin);

  setHubSession(session.token, session.credential_kind);
  // A FRESH user, never a spread of the previous one: the old avatar must not survive the swap
  // (`applyProfile` keeps the session's current avatar when the arriving profile has none, and the
  // face in the sidebar is the one thing on screen that says whose sale this is). The e-mail is
  // left empty because `POST /api/auth/pin` does not carry one; the profile below fills it in.
  setUser({
    id: session.user.id,
    name: session.user.name || name,
    email: '',
    role: session.user.role,
    permissions: session.permissions,
  });

  // Best-effort and unawaited: the till must not wait on it, and a hub that cannot be reached still
  // expires the row by TTL. The guard keeps a re-entrant call from revoking the session just minted.
  if (previous && previous !== session.token) void runtimeLogout(previous);

  // The pass to erplora.com goes with the person who leaves (hub#1538). A password login writes
  // `erplora.access`/`erplora.refresh` into this box; the hand-over does not sign anybody out, so
  // nothing used to take them out again — and the next cashier's whole shift then ran with the
  // previous person's plan, invoices and payment methods sitting in `localStorage` of a till she
  // does not own. Clearing the cloud plane is NOT signing out (ADR-0003: two planes, two
  // credentials): the runtime session just minted, the screen and the route are untouched, and the
  // day-to-day of the TPV never needed a JWT in the first place. Whoever wants erplora.com next
  // types their own password, which is the only correct answer to «whose account is this».
  //
  // The runtime's `handoff_identity_mismatch` (`crates/server/src/auth_api.rs`, hub#1400) stays as
  // it is: it guards the door, and the door is a different thing from not leaving keys behind.
  clearTokens();

  // And her conversation with the assistant goes with her too (hub#1544). Same separation, one
  // drawer along: the thread is session-scoped and lives only on the client (ADR-0149), so the box
  // it sits in IS the whole record — the Cloud keeps no copy to fall back on. Until this, the only
  // thing that emptied it was `logout()`, which is the gesture this module exists to avoid, so the
  // arriving cashier opened the ✨ drawer onto the previous person's morning — what she had taken,
  // what she still owed, what happened with an order — and could scroll all the way up it.
  //
  // Clearing it is NOT signing out, exactly like the credentials above: the runtime session just
  // minted, the screen and the route are untouched, and the new thread starts empty at her first
  // question. Both halves have to go — the in-memory `ref` the drawer is rendering right now, and
  // the `sessionStorage` key it re-hydrates from on the next reload — which is what
  // `clearAssistantHistory()` already does for `logout()`; this reuses it rather than inventing a
  // second way to forget.
  clearAssistantHistory();

  // Language, theme and avatar are per-user rows. Cleared first so nothing of the previous cashier
  // is left standing if `/api/profile` never answers, then re-read for the one who just arrived.
  resetUserProfile();
  resetUserThemePreferences();
  resetUserLocale();
  await getUserProfile().catch(() => null);
}

/**
 * The sentence for a refused hand-over, read off the stable `code` and nothing else.
 *
 * Matching on the message would be matching on prose that gets reworded and translated. The codes
 * are the runtime's contract (`crates/server/src/lib.rs`, `auth_pin`): a device that never did an
 * online login, a client that cannot name its device, and the brute-force guard (hub#329).
 *
 * **An unknown code — and no code at all — falls back to «incorrect PIN»**, which is also the
 * ordinary wrong-PIN case: the runtime sends that one bare. Merely unhelpful, where an instruction
 * invented for a code this build has never seen would be actively wrong.
 */
export function userSwitchRefusal(err: unknown): Refusal {
  const code = (err as { code?: unknown } | null)?.code;
  if (code === 'device_untrusted') return { key: 'userSwitch.deviceNotEnrolled' };
  if (code === 'device_unidentified') return { key: 'userSwitch.deviceUnidentified' };
  // hub#2285: the same lock as the login pinpad, so the same sentence — with the minutes.
  if (code === 'too_many_attempts') return lockRefusal(err);
  return { key: 'userSwitch.rejected' };
}
