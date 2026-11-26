// The Hub's session doors, `/auth/pin`, `/auth/badge` and `/auth/logout`, and the sign-out that stays on the page.
import { forgetAssistant, useAssistant } from '@erplora/ui/components';
import { readCookie, readSpaConfig } from '@erplora/ui/sdk';
import { stopNoticeListening } from '@erplora/ui/shell';

/**
 * The network of the session doors: they open or close a session, which no operation does (Django's `login` and
 * `logout` need the request, as the callback's), so the SDK has no route to them. Same origin and the SDK's CSRF
 * header, as its own calls.
 */
// eslint-disable-next-line no-restricted-globals -- see above
export const sessionDoorFetch: typeof fetch = (...args) => fetch(...args);

/** The Hub's logout (`base/auth_views.py`): POST only, behind Django's CSRF check. */
export const LOGOUT_PATH = '/auth/logout';

/** How long the sign-out is waited for: past it, it failed and the person may try again. */
export const SIGN_OUT_WAIT_MS = 10_000;

/** How a sign-out ended: the session closed, the hub is gone (no session is left to close), or it did not happen. */
export type SessionEnd = 'closed' | 'gone' | 'failed';

/** When a person leaves the till (signing out, the idle lock, «Switch user»): whoever enters next finds the assistant
 *  closed and empty, as someone who just arrived. The device would otherwise keep the panel open for them. */
export function handOverAssistant(): void {
  forgetAssistant();
  useAssistant().setOpen(false);
}

/** What the hub does before its session ends: the assistant handed over and the installed app stops listening with
 *  the screen off (HUB_APP-F26), waited for. */
export async function beforeSignOut(): Promise<void> {
  handOverAssistant();
  await stopNoticeListening();
}

/**
 * Closes this hub's session without leaving the page: the logout answers with its redirect once it closed the
 * session, and the page does not follow it. The host's gate answers 410 for a hub that is gone; anything else, or no
 * answer, is a sign-out that did not happen.
 */
export async function endSession(doc: Document = document, fetcher: typeof fetch = sessionDoorFetch): Promise<SessionEnd> {
  try {
    const config = readSpaConfig(doc);
    const response = await fetcher(LOGOUT_PATH, {
      method: 'POST',
      credentials: 'same-origin',
      redirect: 'manual',
      headers: { [config.csrfHeader]: readCookie(doc.cookie, config.csrfCookieName) ?? '' },
      signal: AbortSignal.timeout(SIGN_OUT_WAIT_MS),
    });
    if (response.type === 'opaqueredirect') return 'closed';
    if (response.status === 410) return 'gone';
    console.error(`hub: the sign-out answered ${response.status}`);
  } catch (error) {
    console.error('hub: the sign-out did not answer', error);
  }
  return 'failed';
}
