// The ONE door out of the till: the SaaS checkout, the plans page, the billing portal, the account
// page. Everything behind it is a round trip — the user leaves, does something in a browser and
// comes BACK to a till that never moved (five of the callers wire a recheck-on-focus that only
// works because this page stays alive).
//
// Leaving is not a detail of the UI, it is the design: the Hub does NOT sell (ADR-0114 §4). The
// module checkout was moved to the SaaS because Google Play does not allow paying for digital goods
// inside the app, and that is what lets the Android build ship at all.
//
// This file used to be one line — `window.open(url, '_blank', 'noopener')` — under a comment saying
// the Hub was "a pure PWA (no Tauri shell; the Bridge is a separate app)". That stopped being true
// with ADR-0196/0180: the same web app now also runs inside the webview of the installed app
// `com.erplora.app`, and there `window.open` opens NOTHING — the page is handed no `shell`/`opener`
// plugin and the webview spawns no window. So on the installed app every one of those buttons did
// nothing at all when pressed: no window, no error, no log (hub#475).
//
// Two paths, one contract — a browser the user comes back from:
//  - **Browser / PWA** → a new tab with `noopener`, exactly as before. The till stays behind.
//  - **Installed app** → the SYSTEM browser, asked for through the shell, which checks the address
//    first (`external_browser_url`, `apps/tauri/src-tauri/src/lib.rs`). Not a tab of ours: the
//    payment must happen outside the app, and a webview navigated onto a checkout is the very thing
//    ADR-0114 took out of it.
//
// There is deliberately NO third path. Navigating this window to the destination instead would be
// cheaper and is what ADR-0251 chose for the MANAGEMENT link — but that link is a switch between
// the two halves of one product, and these are checkouts. In here it would put the payment back
// inside the app, destroy the till the user is standing at, and kill the recheck-on-focus that
// reflects the purchase. When the trip cannot be made, this rejects and the caller SAYS so.
import { invokeTauri, isTauri } from './device';

/** The shell command that hands an address to the user's own browser (hub#475). */
export const OPEN_EXTERNAL_COMMAND = 'open_external_url';

/**
 * The trip out could not be made. Callers must turn this into something the user can read: a button
 * that does nothing when pressed is the defect this module exists to end.
 */
export class OpenExternalError extends Error {
  constructor(readonly url: string, options?: { cause?: unknown }) {
    super(`open_external_failed: ${url}`, options);
    this.name = 'OpenExternalError';
  }
}

/**
 * Opens `url` outside the till and resolves once it is on its way.
 *
 * Rejects with {@link OpenExternalError} when the installed app could not do it — the address is
 * not one the shell will open, the device has no browser, or the app is an older build with no
 * `open_external_url` command at all. That last one matters: a till that has not updated yet keeps
 * failing, but it now says so instead of ignoring the press.
 */
export async function openExternal(url: string): Promise<void> {
  if (isTauri()) {
    try {
      await invokeTauri(OPEN_EXTERNAL_COMMAND, { url });
    } catch (cause) {
      throw new OpenExternalError(url, { cause });
    }
    return;
  }
  // `noopener` on purpose: the opened page must not reach back into the till through
  // `window.opener`. It also means the return value is always `null` per spec, so a blocked popup
  // cannot be told apart from a successful one here — in the browser the user at least sees their
  // own blocker's notice.
  window.open(url, '_blank', 'noopener');
}
