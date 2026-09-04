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
import { openExternal } from './open-external';
import { toastError } from './toast';
import { i18n } from '../i18n';
import { hasPermission, openedWithCloudLogin } from './session';
import { runtimeManagementHandoff } from './cloud';
import { reportClientError } from './error-report';

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
 * Whether THIS session may be offered the way out to management.
 *
 * A filter, not a wall (ADR-0248): there is no consequence a cashier has to be told about here —
 * managing the plan is simply not their task, and they may not even have an account at erplora.com.
 * The authority is the SaaS anyway (`IsHubAdmin` over `HubMember`); this only decides what to show.
 *
 * La regla del comodín vive en un solo sitio (`hasPermission`, hub#506): antes estaba duplicada
 * aquí y en `app-update.ts`, y ninguna de las dos sabía de la otra.
 *
 * 🔒 **Y una segunda mitad** (hub#1400): además del permiso, la sesión tiene que haberse abierto
 * tecleando email y contraseña. `hub.administer` es un permiso del ROL y la pregunta aquí es sobre
 * el MÉTODO — un PIN es credencial de **turno**, corta y tecleada delante de gente, y ADR-0226 ya
 * dice que la credencial del usuario local no es nunca administrativa. Convertirla en la llave del
 * panel de facturación regalaría el billing del negocio a quien abre la caja.
 *
 * Se filtra aquí y no solo en el runtime porque una entrada que se enseña y luego se rechaza es
 * peor que no enseñarla: *«promete algo que no cumple»* (hub#1400). La autoridad sigue siendo el
 * runtime, que lo revalida en `POST /api/auth/handoff`.
 */
export const canOpenManagement: ComputedRef<boolean> = computed(
  () => hasPermission(ADMINISTER_PERMISSION) && openedWithCloudLogin.value,
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
 * La dirección que se abre de verdad: la de un solo uso si el runtime la da, la de siempre si no.
 *
 * El pase (pm#196) es lo que hace que el navegador aterrice **ya logueado**. Cuando no se puede
 * emitir —el SaaS no contesta, la sesión ya no vale— la puerta **no se queda muerta**: cae al enlace
 * de toda la vida, que es exactamente el comportamiento de antes de esta issue, así que degradar
 * nunca es peor que no haberlo intentado. Lo que no se hace es callarse: el motivo se reporta, o el
 * fallo se vuelve invisible y nadie lo arregla nunca.
 */
async function managementDoor(): Promise<string> {
  const fallback = managementUrl();
  try {
    const url = await runtimeManagementHandoff(managementPath());
    return url || fallback;
  } catch (error) {
    reportClientError({
      message: `management handoff failed: ${error instanceof Error ? error.message : String(error)}`,
      component: 'management-link',
    });
    return fallback;
  }
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
 * When the trip cannot be made it is SAID, here rather than at the caller: this door is opened from
 * an icon-only action in the topbar, and a silent failure there is indistinguishable from a dead
 * button — the exact defect hub#475 existed to end.
 */
export async function openManagement(): Promise<void> {
  try {
    await openExternal(await managementDoor());
  } catch {
    await toastError(i18n.global.t('topbar.manageError'));
  }
}
