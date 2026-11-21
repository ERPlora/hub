// «Change business», only inside the installed app (ERPlora/app HUB_APP-F04): the session of this hub closes first,
// then what the hub kept on the device is erased, and only then the app forgets the hub (`forget_hub`, a command any
// page may ask for), which takes the window to the list of businesses. A hub that answers, while open, that it is gone
// leaves the same way (HUB_APP-F05), without forcing the list.
import { readSpaConfig } from '@erplora/ui/sdk';
import { type NativeBridge, nativeBridge, PRIMER_ANSWERED_KEY } from '@erplora/ui/shell';
import { shallowRef } from 'vue';

import { beforeSignOut, endSession } from './sign-out';

/** The app's command that forgets the linked hub and opens the businesses (ERPlora/app `src-tauri/src/window.rs`). */
export const FORGET_HUB_COMMAND = 'forget_hub';

/** How «Change business» ended: the app left the hub, the sign-out failed (nothing forgotten), or the app refused. */
export type ChangeOutcome = 'left' | 'signOutFailed' | 'forgetRefused';

/** Whether «Change business?» (ChangeBusinessDialog, beside the pane) is open. */
export const changeBusinessOpen = shallowRef(false);

export function askChangeBusiness(): void {
  changeBusinessOpen.value = true;
}

/** Erases the hub's storage in this browser but the device's own: its id, the anchor of its one session, and its
 *  answer about the notices, which the app's permission already holds. */
function eraseWhatTheHubKept(win: Window): void {
  for (const name of ['localStorage', 'sessionStorage'] as const) {
    try {
      const keep = [readSpaConfig(win.document).deviceIdStorageKey, PRIMER_ANSWERED_KEY];
      const storage = win[name];
      const kept = keep.map((key) => [key, storage.getItem(key)] as const);
      storage.clear();
      for (const [key, value] of kept) if (value !== null) storage.setItem(key, value);
    } catch (error) {
      console.error(`hub: ${name} could not be erased`, error);
    }
  }
}

/** Once the session is closed: what the sign-out also does, the hub's storage erased, then the app forgets the hub. */
async function forgetTheHub(bridge: NativeBridge, choose: boolean, win: Window): Promise<boolean> {
  await beforeSignOut();
  eraseWhatTheHubKept(win);
  try {
    await bridge.invoke(FORGET_HUB_COMMAND, { choose });
    return true;
  } catch (error) {
    console.error('hub: forget_hub refused', error);
    return false;
  }
}

/** «Change business», confirmed: the list of businesses is forced, or a single one would open again at once. */
export async function changeBusiness(bridge: NativeBridge, win: Window = window): Promise<ChangeOutcome> {
  if ((await endSession(win.document)) === 'failed') return 'signOutFailed';
  return (await forgetTheHub(bridge, true, win)) ? 'left' : 'forgetRefused';
}

/**
 * The live client's reload, once the hub stopped serving the page. Inside the app, a hub that answers it is gone is
 * signed out of and forgotten; anything else reloads, as in a browser, and the hub's own page says what happened.
 */
export async function reloadOrForgetGone(win: Window = window): Promise<void> {
  const bridge = nativeBridge(win);
  if (bridge && (await endSession(win.document)) === 'gone' && (await forgetTheHub(bridge, false, win))) return;
  win.location.reload();
}
