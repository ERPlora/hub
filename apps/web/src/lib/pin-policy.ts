// **"Ask for a PIN: always / per shift / never"** in the web (hub#359) — how often this business
// wants to be asked who is standing at the till.
//
// The second control over the same decision as hub#358's device mode, and the one the owner turns:
// the mode is of the DEVICE (the counter till vs the laptop in the back office), this dial is of
// the HUB — a statement about the business, for the case the mode cannot express, the one-person
// minimarket that does not want to type four digits to sell.
//
// **What each position does, in the client.** The dial decides whether the pinpad is OFFERED
// (`asksForPin`, read by `offersPinLogin` in `device-mode.ts` together with the mode and the
// device-trust). How long the session then lives is decided **server-side**, by the runtime, from
// both controls at once and always by the shorter of the two — a client cannot be trusted with
// that, and does not need to be.
//
// **Everything here fails towards the pinpad**, the same as the device mode:
//
//   - the value starts at `per_shift` — one of the two that keep asking — and only an explicit,
//     exactly-spelled answer from the hub moves it;
//   - anything else (a dead runtime, a 500, a spelling this build does not know) resolves to that
//     same strict value, and a previously granted `never` is **taken back** by the next unreadable
//     answer: the decision behind it lives in the hub, not in this tab;
//   - **it is never cached in `localStorage`.** A stored `never` would be a pinpad switch inside
//     devtools, editable by whoever is holding the tablet.
//
// **This module never writes.** The write door is `PUT /api/settings` behind an **admin session**
// (`hub-settings.ts`), which is the whole point: the login screen runs with no session, so it can
// only ever read where the dial points. A screen that could turn its own lock off is not a lock.
import { ref } from 'vue';

/** How often the hub asks who is at the till. The set is CLOSED (mirror of the runtime). */
export type PinPolicy = 'always' | 'per_shift' | 'never';

/**
 * The value assumed until the hub says otherwise: `per_shift`.
 *
 * Not "the strictest" — `always` is. It is the one that keeps every sale attributed to a person
 * (the property this feature protects) while changing nothing about how long anything lives, and it
 * mirrors the runtime's own default. What matters is the direction: this is never `never`.
 */
export const STRICT_PIN_POLICY: PinPolicy = 'per_shift';

/**
 * The dial as the hub last answered. Starts strict on purpose: the window between mounting the
 * login screen and the answer arriving is not a grey area, and one frame of a till with no pinpad
 * is a sale nobody's name is on.
 */
export const pinPolicy = ref<PinPolicy>(STRICT_PIN_POLICY);

/**
 * The three spellings the hub knows, and nothing near them — no trimming and no case folding, the
 * same closed set as `PinPolicy::parse` in the runtime. Two spellings on the wire would mean the
 * one that slips through is always the lax one, and the lax one here gives up the name on every
 * sale.
 */
export function parsePinPolicy(value: unknown): PinPolicy | null {
  return value === 'always' || value === 'per_shift' || value === 'never' ? value : null;
}

/**
 * Publish what the hub answered, falling back to {@link STRICT_PIN_POLICY} for anything
 * unreadable. Returns the value now in force.
 *
 * It **overwrites** on every call, including with the strict value: that is what takes a granted
 * `never` back when a later read fails. A publisher that only ever moved towards `never` would let
 * one lucky answer outlive the decision behind it.
 */
export function publishPinPolicy(value: unknown): PinPolicy {
  const next = parsePinPolicy(value) ?? STRICT_PIN_POLICY;
  pinPolicy.value = next;
  return next;
}

/**
 * Does this dial still ask who is at the till? Only `never` says no.
 *
 * `never` is the position of the one-person shop, and it is legitimate — with its consequence
 * stated in plain words where it is chosen: whoever opened the till in the morning is the name on
 * every sale until the session expires. It does **not** unlock anything: the session still dies
 * when the device says it does, so somebody with a real account still has to open the till.
 */
export function asksForPin(policy: PinPolicy): boolean {
  return policy !== 'never';
}
