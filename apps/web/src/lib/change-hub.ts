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
// Confirmation is part of the contract, not politeness: forgetting the hub drops the local PWA
// session, so nothing happens until the user says so — and a backdrop tap is a "no".
import { alertController } from '@ionic/vue';
import { invokeTauri, isTauri } from './device';

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
      // `destructive`: the local session is lost. It is also the role the handler keys on, so a
      // backdrop dismissal (role `backdrop`) can never count as a yes.
      { text: labels.confirm, role: 'destructive' },
    ],
  });
  await alert.present();
  const { role } = await alert.onDidDismiss();
  if (role !== 'destructive') return false;
  await invokeTauri('forget_hub', { choose: true });
  return true;
}
