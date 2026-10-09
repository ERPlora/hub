import { RuntimeError, runtimeCourierSession, setTokens } from './cloud';
import { getDeviceContext } from './device';
import { reportClientError } from './error-report';
import { refreshHubIdentity } from './runtime';
import { setHubSession, setUser } from './session';

const COURIER_KEY = 'courier';

/**
 * How long the auth gate is willing to wait for the exchange (hub#858).
 *
 * A gate with no deadline turns a hung runtime into a hung app: the router would never resolve and
 * the user would stare at an empty shell with no way to log in by hand. Ten seconds is far more
 * than the two same-origin round trips need, and expiring the wait only costs the auto-login —
 * the ordinary login page is exactly what a shell that could not redeem its courier should show.
 */
const COURIER_BOOT_WATCHDOG_MS = 10_000;

let bootGate: Promise<void> | null = null;
let releaseBootGate: (() => void) | null = null;
let bootWatchdog: ReturnType<typeof setTimeout> | null = null;

/**
 * Announce that a courier exchange is inbound, so the auth gate holds its decision (hub#858).
 *
 * This has to happen SYNCHRONOUSLY and early: `main.ts` installs the router at module evaluation
 * and Vue Router starts its initial navigation there and then, long before two network round trips
 * can finish. Before this gate existed the guard answered "no session → /login" and nothing ever
 * re-navigated, so the courier landed into a shell that was already showing a login form.
 */
export function armCourierBoot(watchdogMs: number = COURIER_BOOT_WATCHDOG_MS): void {
  if (bootGate) return;
  bootGate = new Promise<void>((resolve) => {
    releaseBootGate = resolve;
  });
  bootWatchdog = setTimeout(settleCourierBoot, watchdogMs);
}

/** Let navigation proceed: the exchange finished, failed, or ran out of patience. Idempotent. */
export function settleCourierBoot(): void {
  if (bootWatchdog !== null) {
    clearTimeout(bootWatchdog);
    bootWatchdog = null;
  }
  const release = releaseBootGate;
  bootGate = null;
  releaseBootGate = null;
  release?.();
}

/**
 * The in-flight courier exchange the auth gate must await, or `null` when there is none.
 *
 * `null` is the ordinary case (a plain browser boot, every navigation after the first): nothing
 * waits for anything, so this cannot slow the app down.
 */
export function courierBootPending(): Promise<void> | null {
  return bootGate;
}

let shellCodeTaken = false;
let shellCode: string | null = null;

/**
 * Take the shell's courier off the real URL, once per document, and remember it (hub#755).
 *
 * WHERE this runs matters more than what it returns, so it deserves its own entry point.
 * `history.replaceState` cleans the address bar but tells Vue Router nothing, and
 * `createWebHistory()` snapshots `window.location` — fragment included — the moment `router/index.ts`
 * is evaluated. `main.ts` imports that module, and ES imports run before the module body, so a
 * scrub written in `main.ts` was always too late: the router replayed its stale snapshot on the
 * initial navigation and wrote the credential straight back into the URL. That is why
 * `router/index.ts` calls this itself, before building its history.
 *
 * Being idempotent is what lets both callers ask without either needing to know who got there
 * first — and it keeps a second call from re-arming a boot gate that nobody will ever settle.
 */
export function takeShellCourierCode(): string | null {
  if (!shellCodeTaken) {
    shellCodeTaken = true;
    shellCode = takeCourierCode();
  }
  return shellCode;
}

/**
 * Take the opaque courier credential out of the URL fragment and scrub it synchronously.
 * Fragments are not sent to HTTP servers or in Referer headers; replacing history here also keeps
 * the one-time code out of screenshots, copy/paste and later browser history entries.
 *
 * Finding a code also ARMS the boot gate: this runs before the router is installed, which is the
 * only moment early enough to stop the auth gate from deciding without the session (hub#858).
 *
 * A hash without a `courier` key is left completely alone: the shell puts real state there
 * (`/settings#permissions`), and eating it would break every sub-tab deep link.
 */
export function takeCourierCode(
  locationLike: Pick<Location, 'hash' | 'pathname' | 'search'> = window.location,
  replace: (url: string) => void = (url) => window.history.replaceState(null, '', url),
): string | null {
  if (!locationLike.hash.startsWith('#')) return null;
  const params = new URLSearchParams(locationLike.hash.slice(1));
  const code = params.get(COURIER_KEY)?.trim() ?? '';
  if (!code) return null;
  replace(`${locationLike.pathname}${locationLike.search}`);
  if (code.length > 128) return null;
  armCourierBoot();
  return code;
}

/** Complete shell auto-login before Vue/router mount.  Only the local opaque session and the same
 * Cloud tokens used by the ordinary login flow are persisted; no credential is logged.
 *
 * Always settles the boot gate, whatever happens: a rejected exchange must release navigation to
 * the login page instead of leaving the shell waiting forever. */
export async function bootCourier(code: string | null = takeShellCourierCode()): Promise<boolean> {
  if (!code) {
    settleCourierBoot();
    return false;
  }
  try {
    return await exchangeCourier(code);
  } finally {
    settleCourierBoot();
  }
}

async function exchangeCourier(code: string): Promise<boolean> {
  const device = await getDeviceContext();
  const result = await runtimeCourierSession(code, device?.id);
  setTokens(result.access, result.refresh);
  setHubSession(result.token, result.credential_kind);
  setUser({
    id: result.user.id,
    cloudUserId: result.cloud_user.id,
    name: result.cloud_user.name,
    email: result.cloud_user.email,
    role: result.user.role,
    permissions: result.permissions,
  });
  // hub#2510: a browser that came in through the panel was never trusted, so the boot read was not
  // told the faces. With the session it is, before the router mounts.
  await refreshHubIdentity();
  return true;
}

/** One-shot flag: a courier exchange failed during this boot (hub#2152). Read through
 *  `takeCourierFailure`, which resets it — see that export for why it exists. */
let courierFailed = false;

/**
 * Reduce a failed exchange to a stable identifier, never its prose and never the pass.
 *
 * ADR-0159: the runtime's free text is not trusted to be free of the one-time credential (it has
 * appeared inside error prose before, e.g. "pass … expired"), so only the machine-readable code or
 * error name ever leaves this module. `RuntimeError.code` is the contract most failures carry; a
 * `DOMException` `AbortError` (the runtime deadline, hub#2145) has no such code but its `name` is
 * just as stable. Some environments do not make `DOMException` an `instanceof Error`, so the name
 * is also read structurally as a fallback.
 */
function courierFailureReason(error: unknown): string {
  if (error instanceof RuntimeError && error.code) return error.code;
  if (error instanceof Error) return error.name;
  const name = (error as { name?: unknown } | null)?.name;
  return typeof name === 'string' && name ? name : 'unknown';
}

/**
 * Redeem the shell's one-time courier before the router mounts. This is `main.ts`'s single entry
 * point for it and it NEVER throws (hub#2152).
 *
 * Before this, `main.ts` called `bootCourier` behind an empty `catch`: a broken answer, a refusal,
 * or a hub that stopped responding all looked the same from there on — silence. Login has to stay
 * reachable no matter what the exchange does, so failure is reported through the ordinary
 * client-error channel with the runtime's CODE (never its message, never the pass — ADR-0159) and
 * left as a one-shot flag (`takeCourierFailure`) for the login screen to explain.
 */
export async function redeemShellCourier(code: string | null): Promise<boolean> {
  try {
    return await bootCourier(code);
  } catch (error) {
    courierFailed = true;
    reportClientError({
      message: `courier exchange failed: ${courierFailureReason(error)}`,
      component: 'courier',
    });
    return false;
  }
}

/**
 * One-shot read of the courier failure flag (hub#2152): the login screen reads it once when it is
 * created and resets it here, so coming back to the login later does not repeat the notice.
 */
export function takeCourierFailure(): boolean {
  const failed = courierFailed;
  courierFailed = false;
  return failed;
}
