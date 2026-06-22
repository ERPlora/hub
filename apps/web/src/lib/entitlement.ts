// Gate de entitlement del shell (ARQUITECTURA.md §2.10): decide qué módulos puede MONTAR el
// hub. En Tauri usa el comando `validate_entitlement` (token firmado cacheado + gracia
// offline); en web-pwa llama directo al endpoint del Cloud (online). Hasta resolver, es
// PERMISIVO (no rompe el dev/web mientras se resuelve el hub_id).
//
// Consumido por:
//  - lib/module-loader (filtra los módulos instalados a los entitled),
//  - App.vue (resuelve en boot/login y redirige a /activation si needs_activation),
//  - router (guard de /m/:moduleId y de /activation).
import { computed, ref } from 'vue';

import { cloudEntitlement, getAccessToken } from './cloud';
import { config } from './config';
import { invokeTauri } from './device';

export type EntitlementStatus = 'unknown' | 'unlocked' | 'needs_activation';

/** Resultado del comando Tauri `validate_entitlement` (serde tag="state", snake_case). */
interface GateOutcome {
  state: 'unlocked' | 'needs_activation' | 'hub_gone';
  modules?: Array<{ module_id: string; tier: string; version: string }>;
  deployment_mode?: string;
  offline?: boolean;
  reason?: string;
}

// `null` = aún sin resolver → permisivo. Un Set (aunque vacío) = resuelto → filtro estricto.
const _ids = ref<Set<string> | null>(null);
const _status = ref<EntitlementStatus>('unknown');
const _offline = ref<boolean>(false);
const _reason = ref<string>('');

export const entitlementStatus = computed<EntitlementStatus>(() => _status.value);
export const entitlementOffline = computed<boolean>(() => _offline.value);
export const entitlementReason = computed<string>(() => _reason.value);
export const needsActivation = computed<boolean>(() => _status.value === 'needs_activation');

/** ¿Puede montarse este módulo? Permisivo mientras no se haya resuelto el entitlement. */
export function isModuleEntitled(moduleId: string): boolean {
  if (_ids.value === null) return true;
  return _ids.value.has(moduleId);
}

/** Limpia el estado (al cerrar sesión). */
export function resetEntitlement(): void {
  _ids.value = null;
  _status.value = 'unknown';
  _offline.value = false;
  _reason.value = '';
}

/** Hook que dispara el shell cuando el Cloud reporta que el hub fue borrado/revocado (410
 *  `hub_not_found`). El shell lo cablea para olvidar la identidad local (`forget_hub`) + logout
 *  → /login; el siguiente login re-registra por `X-Device-Id` (§2.9b). */
let onHubGone: (() => void) | null = null;
export function setOnHubGone(fn: () => void): void {
  onHubGone = fn;
}

function applyOutcome(o: GateOutcome): void {
  if (o.state === 'unlocked') {
    _ids.value = new Set((o.modules ?? []).map((m) => m.module_id).filter(Boolean));
    _status.value = 'unlocked';
    _offline.value = Boolean(o.offline);
    _reason.value = '';
  } else {
    _ids.value = new Set(); // nada montable hasta activar
    _status.value = 'needs_activation';
    _offline.value = Boolean(o.offline);
    _reason.value = o.reason ?? '';
  }
}

/**
 * Resuelve el entitlement del hub activo. Idempotente: se puede llamar en boot y tras login.
 * - Tauri: `validate_entitlement` (offline-capable). Su `needs_activation` SÍ bloquea.
 * - Web: endpoint del Cloud. Si falla (p. ej. hub_id aún sin resolver), queda PERMISIVO — en
 *   web el shell es online y no tiene sentido bloquearlo por un fallo transitorio de red.
 */
export async function resolveEntitlement(): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    resetEntitlement();
    return;
  }

  // Camino Tauri (devuelve null si no estamos en Tauri).
  const outcome = await invokeTauri<GateOutcome>('validate_entitlement', {
    hubId: config.hubId,
    accessToken: token,
  }).catch(() => null);
  if (outcome) {
    if (outcome.state === 'hub_gone') {
      // El Cloud dice que el hub fue borrado/revocado (410 hub_not_found): olvidamos la identidad
      // local y salimos a /login. El siguiente login re-registra por X-Device-Id (§2.9b). NO
      // mostramos la pantalla de activación (no es un problema de licencia, el hub ya no existe).
      resetEntitlement();
      onHubGone?.();
      return;
    }
    applyOutcome(outcome);
    return;
  }

  // Camino web (online).
  try {
    const { modules } = await cloudEntitlement();
    _ids.value = new Set(modules.map((m) => m.moduleId).filter(Boolean));
    _status.value = 'unlocked';
    _offline.value = false;
    _reason.value = '';
  } catch {
    // Permisivo: no bloquear el shell web por un fallo transitorio (hub_id aún no listo, etc.).
    _ids.value = null;
    _status.value = 'unknown';
  }
}
