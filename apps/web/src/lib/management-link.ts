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
import { computed, type ComputedRef } from 'vue';

import { config } from './config';
import { user } from './session';

/**
 * The permission that opens this door: the one the core already owns (ADR-0248, hub#435).
 *
 * `hub.administer` is granted by `identity::session_permissions` to exactly the roles
 * `is_admin_role` accepts, so "the topbar offered it" and "an administrator asked for it" are the
 * same sentence. It is NOT re-invented here and no `module.json` can mint it (`permissions_for_role`
 * ignores the reserved `hub.` namespace).
 */
export const ADMINISTER_PERMISSION = 'hub.administer';

/** The wildcard the shell hands an owner/admin session (mirror of `lib/runtime.ts`). */
const ALL_PERMISSIONS = '*';

/**
 * Whether THIS session may be offered the way out to management.
 *
 * A filter, not a wall (ADR-0248): there is no consequence a cashier has to be told about here —
 * managing the plan is simply not their task, and they may not even have an account at erplora.com.
 * The authority is the SaaS anyway (`IsHubAdmin` over `HubMember`); this only decides what to show.
 */
export const canOpenManagement: ComputedRef<boolean> = computed(() => {
  const granted = user.value?.permissions ?? [];
  return granted.includes(ADMINISTER_PERMISSION) || granted.includes(ALL_PERMISSIONS);
});

/**
 * The URL of the management panel for the hub this till belongs to.
 *
 * Built on demand: `config.hubId` is resolved from the runtime during boot
 * (`GET /api/hub/context`), so a value captured at module load would be the empty fallback.
 */
export function managementUrl(): string {
  return `${config.cloudApiUrl}/dashboard/?view=advanced&hub=${encodeURIComponent(config.hubId)}&utm_source=hub`;
}

/**
 * Walk out to management, in THIS tab.
 *
 * Not `openExternal` (which is `_blank`, and right for a checkout you come BACK from): this is a
 * switch between two halves of one product, and its return path is a feature of the destination —
 * the SaaS panel enters the hub again. A new tab would be a dead end on a till with no tab bar, and
 * inside the installed app it is worse than a dead end: there is no `shell`/`opener` plugin and the
 * webview spawns no window, so `window.open` would be a button that silently does nothing.
 * Navigating in place always leaves Back, on every surface.
 */
export function openManagement(): void {
  window.location.assign(managementUrl());
}
