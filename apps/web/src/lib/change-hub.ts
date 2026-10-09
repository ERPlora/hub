// hub#447 — «switch business»: the user-driven exit from the ONE hub the installed app remembers.
//
// The mechanism predates the button: `/shell/?choose=1` lists the user's hubs and the `?shell=1`
// capture overwrites the previous one (ADR-0159, proven by `capturing_a_second_hub_replaces_the
// _first`). What never existed was a door from inside the hub — `forget_hub` was only ever fired
// by a Cloud 410, so an owner with two businesses and one tablet had no way across, and a till
// being reassigned to another venue could only be uninstalled (which on Android also destroys
// `device.id`, the stable anchor of ADR-0154's single-device session; `forget_hub` preserves it
// on purpose).
//
// Confirmation is part of the contract, not politeness: switching signs the person out of this
// business, so nothing happens until the user says so — and a backdrop tap is a "no".
//
// hub#2503: and it really signs out. `forget_hub` only drops the remembered address and navigates
// the whole window, so the session, the person's name and email and their erplora.com tokens used to
// stay in this origin's storage — the next person on the tablet could open the business again with
// a link and be inside. Everything is finished BEFORE the forget: the navigation cuts a revocation
// still in flight, and once the hub is forgotten this page may no longer stop the Android listening.
import { alertController } from '@ionic/vue';
import { invokeTauri, isTauri } from './device';
import { stopNoticeListening } from './notice-listening';
import { logoutBeforeLeaving } from './session';

/** How long the switch waits for the hub to revoke the session before leaving anyway. */
export const LEAVE_HUB_REVOKE_WAIT_MS = 5000;

/** The words the confirmation puts in front of the user — the CALLER owns i18n (ADR-0055). */
export interface ChangeHubLabels {
  header: string;
  message: string;
  cancel: string;
  confirm: string;
}

/**
 * Only inside the installed app: a browser holds no capture to forget — its way to another hub is
 * the address bar, and rendering the control there would offer a door into a wall.
 */
export function canChangeHub(): boolean {
  return isTauri();
}

/**
 * Asks, and only then switches. `choose: true` is load-bearing: plain `forget_hub` navigates to
 * `{saas}/shell/`, which auto-redirects a single-hub user straight back into the hub they were
 * trying to leave; `?choose=1` is the SaaS's own affordance for forcing the list.
 *
 * Resolves `true` when the switch was confirmed and requested — the shell then navigates the
 * whole window, so there is nothing further for the caller to do.
 */
export async function requestChangeHub(labels: ChangeHubLabels): Promise<boolean> {
  const alert = await alertController.create({
    header: labels.header,
    message: labels.message,
    buttons: [
      { text: labels.cancel, role: 'cancel' },
      // `destructive`: the session is closed. It is also the role the handler keys on, so a
      // backdrop dismissal (role `backdrop`) can never count as a yes.
      { text: labels.confirm, role: 'destructive' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  if (role !== 'destructive') return false;
  await signOutAndForgetHub(true);
  return true;
}

/**
 * Closes everything of the person on this device and only THEN forgets the hub — the one way out,
 * shared by «switch business» (`choose: true`) and the Cloud's 410 «hub not found» (`main.ts`).
 * The order is the contract: the listening stops while this page is still the linked business, the
 * session is revoked before the navigation can cut the request, and the forget comes last.
 */
export async function signOutAndForgetHub(choose: boolean): Promise<void> {
  await stopNoticeListening();
  await logoutBeforeLeaving(LEAVE_HUB_REVOKE_WAIT_MS);
  await invokeTauri('forget_hub', choose ? { choose: true } : undefined);
}
