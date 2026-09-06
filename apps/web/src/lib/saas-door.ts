// The way OUT of this app to erplora.com, for the pages the SaaS only shows to a signed-in person
// (pm#196, hub#1400).
//
// Inside the installed app the trip crosses a border that is invisible from here: the link opens in
// the SYSTEM browser, whose cookie jar is not the webview's. The owner had signed in minutes ago
// and still landed on a login form — password and second factor again, right before paying. So the
// address that gets opened is not the plain URL but a ONE-TIME one the runtime mints, which carries
// the session across.
//
// It lives apart from any one caller on purpose. The mechanism arrived wired to a single link
// ("manage your business") while the plan page and the fiscal representation grant — the two that
// the issue names as costing money — still crossed with nothing. One door, every caller.
import { runtimeBrowserHandoff } from './cloud';
import { reportClientError } from './error-report';
import { getHubSession } from './session';

/** The stable code for a pass dropped because the device changed hands (hub#1584). */
const SESSION_CHANGED = 'handoff_session_changed';

/**
 * The address to actually open for `path`: the one-time one when the runtime hands it over, the
 * plain `fallback` when it does not.
 *
 * **The runtime is asked with a PATH, never a full URL.** The address is assembled by the side that
 * knows where the SaaS is; a page that could choose the host would be choosing where the pass gets
 * spent — and the pass opens a session.
 *
 * **The pass belongs to the session that asked for it** (hub#1584). The runtime mints it from the
 * headers of whoever pressed the link, which is correct; what is not is spending it whenever it
 * comes back. On a shared till the hand-over is a PIN and a couple of seconds (`switchUser`), so it
 * fits inside the round trip — and then the browser opens on the previous person's erplora.com
 * account for somebody who typed no credential of her own. So the session is read again on arrival
 * and, if the till changed hands, the pass is dropped and the plain link opens: that one asks for
 * credentials, which is exactly what the person who just took over should meet. Reading it again
 * rather than trusting the mint is the point — the runtime cannot know about a swap that happened
 * after it answered.
 *
 * **Degrading is the contract, not a bug.** The runtime refuses a pass on purpose in three cases
 * (a shift PIN rather than a password, a role without `hub.administer`, a JWT naming somebody
 * else), and it can simply be unreachable. None of them may turn a button dead: the caller still
 * gets a working link — exactly the behaviour from before this issue — so trying is never worse
 * than not having tried.
 *
 * What it does **not** do is degrade in silence. `door` names the caller because four of them share
 * this code and "handoff failed" with no subject cannot be acted on: a failure nobody sees is a
 * failure nobody fixes.
 */
export async function saasDoor(path: string, fallback: string, door: string): Promise<string> {
  try {
    // Read BEFORE the round trip, so what is compared is who pressed the link — not who is at the
    // till by the time the answer lands. Inside the `try` because degrading is this door's whole
    // contract: nothing it does to decide may leave the caller holding a dead button.
    const opener = getHubSession();
    const url = await runtimeBrowserHandoff(path);
    if (getHubSession() !== opener) {
      reportClientError({
        message: `browser handoff dropped for ${door}: ${SESSION_CHANGED}`,
        component: 'saas-door',
      });
      return fallback;
    }
    return url || fallback;
  } catch (error) {
    reportClientError({
      message: `browser handoff failed for ${door}: ${error instanceof Error ? error.message : String(error)}`,
      component: 'saas-door',
    });
    return fallback;
  }
}
