// **Step-up approval, the part a person sees** (hub#363 — the last of ADR-0238 / ADR-0246 /
// ADR-0265).
//
// The runtime has been able to say «a manager could approve this» since hub#360, to verify the
// manager's PIN and mint a one-action approval since hub#361, and to write the receipt of every
// approval spent since hub#362. Until now nothing on the client ever asked: the whole chain existed
// with no door into it. This file is that door's state — one dialog at a time, and the sentence a
// refusal earns.
//
// What is deliberately NOT here: the endpoint, the header and the decision of when approval is
// needed. All three are the runtime's published contract and live once, in the transport
// (`@erplora/module-sdk`), so a screen cannot hold a second, drifting copy of them. What this file
// owns is only which words appear and when.
import { ref } from 'vue';
import type { ElevationApprover, ElevationAsk } from '@erplora/module-sdk';
import { lockRefusal, type Refusal } from './lock-refusal';

/**
 * The approval currently on screen, or `null` when there is none. `ElevationDialog` renders it and
 * answers with {@link resolveElevation}; nothing else writes it.
 */
export const pendingElevation = ref<ElevationAsk | null>(null);

/** Answers the promise {@link askForApproval} handed to the transport. */
let answer: ((token: string | null) => void) | null = null;

/**
 * The shell's {@link ElevationApprover}: wired into the transport once, in `runtime.ts`.
 *
 * **One dialog at a time.** A second ask while one is open is refused outright rather than queued
 * or stacked. A modal over a modal is how a manager approves the wrong action — they are shown one
 * sentence and a pinpad, and nothing on the screen says which of the two it belongs to. The refused
 * caller gets `null`, which the transport turns back into the plain refusal it already had, so the
 * cashier simply taps again once the first one is answered. Two people needing approval at the same
 * till in the same second is not a thing; approving the wrong void is.
 */
export const askForApproval: ElevationApprover = (ask: ElevationAsk) => {
  if (pendingElevation.value) return Promise.resolve(null);
  pendingElevation.value = ask;
  return new Promise<string | null>((resolve) => {
    answer = resolve;
  });
};

/**
 * Close the dialog with `token` (the manager approved) or `null` (nobody did). Idempotent, and a
 * no-op when nothing is open: the dialog can be dismissed by backdrop, by the button and by the
 * flow itself, and all three land here.
 */
export function resolveElevation(token: string | null): void {
  const resolve = answer;
  answer = null;
  pendingElevation.value = null;
  resolve?.(token);
}

/**
 * The sentence for a refusal of `POST /api/elevation/approve`.
 *
 * Read off the stable `code` and **nothing else**. Matching on the message would be matching on
 * prose that gets reworded and translated, and the day it is, the refusal silently starts landing
 * on the wrong sentence.
 *
 * ⚠️ There is exactly ONE key for a refused PIN, and that is not an omission. The runtime answers
 * `hub.elevation.rejected` identically to an unknown name, a wrong PIN and a deactivated user, so
 * that a dialog at the counter cannot be used to find out who works here. Splitting that code into
 * several sentences on this side would undo the decision from the outside.
 *
 * Anything unrecognised — a dropped connection, a command that vanished with an app, a code this
 * build has never seen — falls back to «it could not be done», never to «wrong PIN». The login
 * pinpad falls back the other way because there the only realistic cause IS the digits; here it is
 * not, and telling a manager their PIN is wrong when it is right is how a shop ends up sharing one
 * credential — the exact outcome this whole chain exists to avoid.
 */
export function elevationRefusal(err: unknown): Refusal {
  const code = (err as { code?: unknown } | null)?.code;
  switch (code) {
    case 'hub.elevation.rejected':
      return { key: 'elevation.rejected' };
    case 'hub.elevation.approver_cannot':
      return { key: 'elevation.approverCannot' };
    case 'hub.elevation.not_elevable':
      return { key: 'elevation.notElevable' };
    case 'hub.elevation.not_required':
      return { key: 'elevation.notRequired' };
    case 'too_many_attempts':
      // hub#2285: the login pinpad's lock, and its sentence, with the minutes the SDK's
      // `ErploraError` carries as `retryAfterSecs` (hub#2290).
      return lockRefusal(err);
    default:
      return { key: 'elevation.failed' };
  }
}
