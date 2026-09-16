// The door from the till to MANAGEMENT — which is not a screen of this app (hub#364, PLAN step 8).
//
// Plans, invoices, the marketplace and the businesses themselves live in the SaaS. The Hub does not
// mirror them and does not write them: it LINKS, which is the whole decision of the issue ("enlaza
// al SaaS, no escribe") — less API surface, less auth to solve, same result.
//
// `view=advanced` is the Hub's half of the ONE switch of PLAN step 8. The SaaS half is the "Simple
// view" toggle of its topbar (saas#1159), which persists `Profile.view_mode = simple` and hands the
// session to the post-login router. Without a way back, that preference is a RATCHET: an account
// born in `simple` could never make the panel its landing again. The marker travels on a plain
// navigation because the Hub is another origin — it cannot POST to the SaaS with a CSRF token — and
// because the Hub deliberately holds no credential that could write there.
import { computed, type ComputedRef, ref } from 'vue';

import { config } from './config';
import { type DeviceContext, isTauri } from './device';
import { openExternal } from './open-external';
import { toastError } from './toast';
import { i18n } from '../i18n';
import { hasPermission, openedWithCloudLogin } from './session';
import { saasDoor } from './saas-door';

/**
 * The permission that opens this door: the one the core already owns (ADR-0248, hub#435).
 *
 * `hub.administer` is granted by `identity::session_permissions` to exactly the roles
 * `is_admin_role` accepts, so "the topbar offered it" and "an administrator asked for it" are the
 * same sentence. It is NOT re-invented here and no `module.json` can mint it (`permissions_for_role`
 * ignores the reserved `hub.` namespace).
 */
export const ADMINISTER_PERMISSION = 'hub.administer';

/**
 * Whether the copy of the app in the user's hands may be offered this door (hub#1897).
 *
 * The reasoning that kept it — managing your account is not a storefront, which is what every B2B
 * SaaS in both stores does — survives for the browser and for Windows. What derogates it on Play is
 * not an argument but a MEASUREMENT: the QA over the published v1.1.25 timed **three taps** from
 * the till to the SaaS's invoices screen, the first of them this button, and it lands ALREADY
 * SIGNED IN because the trip carries a one-time pass (pm#196). The panel is not a page that cannot
 * sell: it is the one next door to the page that does, with «Billing» in its own sidebar.
 *
 * **The cut is the DISTRIBUTION, not the operating system** — the same one `planUpgradeIsOfferable`
 * makes (hub#756), and for the same reason: the rule is set by whoever hands out the binary. A
 * sideloaded APK runs on the same Android and Google does not govern it; hiding an owner's own
 * account there would be taking something away under a rule that does not apply to them.
 *
 * With no signal it is OFFERED. A shell older than hub#757 does not send `distribution`, and a
 * browser never does: refusing by default would lock almost everybody out of their account to guard
 * against a risk that outside Play does not exist.
 */
export function managementIsOfferable(distribution: DeviceContext['distribution']): boolean {
  return distribution !== 'play';
}

/**
 * What the shell answered about this copy — `null` until it has answered at all.
 *
 * The distinction matters because the topbar is painted before the answer arrives. Defaulting to
 * "offered" would show the button on a Play install at every start and take it away a frame later:
 * the same defect, with a layout jump on top. A BROWSER, on the other hand, is known from the first
 * frame — no store hands out a Chrome tab — so there it opens with no wait.
 */
const shellDistribution = ref<DeviceContext['distribution'] | null>(null);

/**
 * Publish what the shell said about this copy (`GET device_context`), once, at boot.
 *
 * `null` puts it back to "not asked yet"; the app only ever calls this with the resolved answer.
 */
export function setManagementDistribution(distribution: DeviceContext['distribution'] | null): void {
  shellDistribution.value = distribution;
}

/** Whether this copy carries the door, with the pre-answer rule above applied. */
function offeredToThisCopy(): boolean {
  const answered = shellDistribution.value;
  if (answered === null) return !isTauri();
  return managementIsOfferable(answered);
}

/**
 * Whether THIS session may be offered the way out to management.
 *
 * A filter, not a wall (ADR-0248): there is no consequence a cashier has to be told about here —
 * managing the plan is simply not their task, and they may not even have an account at erplora.com.
 * The authority is the SaaS anyway (`IsHubAdmin` over `HubMember`); this only decides what to show.
 *
 * La regla del comodín vive en un solo sitio (`hasPermission`, hub#506): antes estaba duplicada
 * aquí y en `app-update.ts`, y ninguna de las dos sabía de la otra.
 *
 * 🔒 **And a second half** (hub#1400): on top of the permission, the session has to have been
 * opened by typing an email and a password. `hub.administer` is a permission of the ROLE, and the
 * question here is about the METHOD — a PIN is a credential of the SHIFT, short and typed in front
 * of people, and ADR-0226 already says the local user's credential is never administrative. Turning
 * it into the key to the billing panel would hand the business's money to whoever opens the till.
 *
 * It is filtered here and not only in the runtime because an entry that is shown and then refused is
 * worse than one that was never shown: it promises something it does not deliver (hub#1400). The
 * authority is still the runtime, which revalidates it in `POST /api/auth/handoff`.
 *
 * 🏪 **And a third condition** (hub#1897): which copy of the app is asking. Permission and method are
 * about the PERSON, and the store's objection is not about the person — see
 * {@link managementIsOfferable}. It is folded in HERE, in the one predicate the chrome reads, so
 * that both places that render the door (the topbar button and the overflow menu) are covered by
 * writing the rule once.
 */
export const canOpenManagement: ComputedRef<boolean> = computed(
  () => hasPermission(ADMINISTER_PERMISSION) && openedWithCloudLogin.value && offeredToThisCopy(),
);

/**
 * The management panel **as a path of the SaaS**, marker and all.
 *
 * Separate from [`managementUrl`] because the one-time pass (pm#196) carries the destination as a
 * relative route: the runtime builds the address with ITS idea of where the SaaS is, and a page that
 * could choose the host would be choosing where the pass is spent.
 *
 * Built on demand: `config.hubId` is resolved from the runtime during boot
 * (`GET /api/hub/context`), so a value captured at module load would be the empty fallback.
 */
export function managementPath(): string {
  return `/dashboard/?view=advanced&hub=${encodeURIComponent(config.hubId)}&utm_source=hub`;
}

/**
 * The URL of the management panel for the hub this till belongs to.
 *
 * Built on demand: `config.hubId` is resolved from the runtime during boot
 * (`GET /api/hub/context`), so a value captured at module load would be the empty fallback.
 */
export function managementUrl(): string {
  return `${config.cloudApiUrl}${managementPath()}`;
}

/**
 * The address that actually gets opened: the one-time one when the runtime hands it over, the usual
 * one when it does not.
 *
 * The pass (pm#196) is what makes the browser land ALREADY SIGNED IN. Everything about minting it,
 * degrading when it cannot be minted, and saying so out loud lives in {@link saasDoor} — this is
 * one of its four callers, not the owner of the mechanism.
 */
async function managementDoor(): Promise<string> {
  return saasDoor(managementPath(), managementUrl(), 'management');
}

/**
 * Walk out to management — through the door OUT, never by navigating this window.
 *
 * **The Hub never takes its own window to the SaaS.** In a browser that is merely rude; inside the
 * installed app it is a trap: the webview has no chrome, no Back, no tabs, so the user lands on the
 * SaaS and is stuck there with no way home. Reported by Ioan on the desktop app (2026-08-09).
 *
 * This used to be `window.location.assign`, argued as "navigating in place always leaves Back, on
 * every surface". That is false on the one surface that matters most, and the other half of the
 * argument — that inside the app `window.open` opens NOTHING — stopped being true with hub#475,
 * which is precisely what it fixed: `openExternal` hands the address to the system browser through
 * the shell, and opens a tab in a browser. One door, both surfaces.
 *
 * When the trip cannot be made it is SAID, here rather than at the caller: a silent failure on a
 * topbar action is indistinguishable from a dead button — the exact defect hub#475 existed to end.
 * (The button carries a visible label since hub#1400; the reasoning holds either way, because what
 * a label cannot tell you is that the press went nowhere.)
 */
export async function openManagement(): Promise<void> {
  try {
    await openExternal(await managementDoor());
  } catch {
    await toastError(i18n.global.t('topbar.manageError'));
  }
}
