// hub#1715 — the address the sidebar QR carries, in one place.
//
// A QR only earns its place if a DIFFERENT device can act on what it reads. That rules out every
// address that is only true on the machine that painted it, and it is why this is a function with
// tests rather than an expression inlined in the template: the failure mode is silent. A wrong
// address still renders a perfectly crisp, perfectly scannable code — the person only finds out
// once the phone is already in their hand.
//
// The destination goes through `hubUrl` (lib/deep-link), which is the CANONICAL boundary for hub
// destinations: the same one the SaaS applies to its links and the same one the installed app
// applies in `hub_url_for_host` (apps/tauri). Building the address here with our own rules would
// be a fourth guard that can disagree with the other three.

import { hubUrl } from './deep-link';

/**
 * The slice of `window.location` this needs. Passed in so the rule is testable without a DOM, and
 * typed to accept the real `Location` whole — including the parts it deliberately IGNORES, so a
 * test can hand it a browser sitting deep inside the app and watch them get dropped.
 */
export interface QrLocation {
  /** `hostname[:port]` — the port matters in development, where the hub is loopback http. */
  host: string;
  /** Scheme + host, exactly as the browser reports it. The fallback when `host` is not ours. */
  origin: string;
  /** Ignored. Present so `window.location` fits, and so the test can prove it is ignored. */
  href?: string;
}

/**
 * The URL to encode in the sidebar QR for the hub currently on screen.
 *
 * `host` and not `origin` on purpose: `hubUrl` NORMALISES (lowercase, trailing slash) and VALIDATES,
 * and it drops whatever path or query the shell happens to be sitting on. That last part is
 * load-bearing inside the installed app, which navigates its webview to `https://<host>/?shell=1`:
 * a QR built from the raw location would hand the phone a `shell=1` it has no business receiving.
 *
 * Never returns empty. When the host is not a hub of ours — a LAN address, a custom domain — the
 * origin is still the one honest answer: it is literally where this browser is. A blank QR would
 * be a code that hides itself, which is the one thing hub#1715 asked us not to build.
 */
export function installQrUrl(location: QrLocation): string {
  return hubUrl(location.host) ?? location.origin;
}
