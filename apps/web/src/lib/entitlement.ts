// Gate de entitlement del shell (ARQUITECTURA.md §2.10): decide qué módulos puede MONTAR el
// hub, llamando al endpoint del Cloud (online). Hasta resolver, es PERMISIVO (no rompe el
// dev/web mientras se resuelve el hub_id). ADR-0159: el camino Tauri (`validate_entitlement`,
// caché offline + gracia) se retiró con el producto local (ADR-0154) — dentro del shell fino el
// gate es EXACTAMENTE el mismo que en el navegador.
//
// Consumido por:
//  - lib/module-loader (filtra los módulos instalados a los entitled),
//  - App.vue (resuelve en boot/login y redirige a /activation si needs_activation),
//  - router (guard de /m/:moduleId y de /activation).
import { computed, ref } from 'vue';

import { cloudEntitlement, getAccessToken } from './cloud';

export type EntitlementStatus = 'unknown' | 'unlocked' | 'needs_activation';

// `null` = aún sin resolver → permisivo. Un Set (aunque vacío) = resuelto → filtro estricto.
const _ids = ref<Set<string> | null>(null);
const _status = ref<EntitlementStatus>('unknown');
const _offline = ref<boolean>(false);
const _reason = ref<string>('');
// Módulos de pago BLOQUEADOS por la revalidación híbrida (ADR-0114 §6): el dispatcher del
// runtime ya rechaza sus queries/commands con 402; aquí la UI los deshabilita con CTA
// "Gestionar suscripción". NUNCA se desinstalan ni se tocan datos locales.
const _blocked = ref<Set<string>>(new Set());

export const entitlementStatus = computed<EntitlementStatus>(() => _status.value);
export const entitlementOffline = computed<boolean>(() => _offline.value);
export const entitlementReason = computed<string>(() => _reason.value);
export const needsActivation = computed<boolean>(() => _status.value === 'needs_activation');

/** ¿Puede montarse este módulo? Permisivo mientras no se haya resuelto el entitlement. */
export function isModuleEntitled(moduleId: string): boolean {
  if (_ids.value === null) return true;
  return _ids.value.has(moduleId);
}

/** ¿Está el módulo de pago BLOQUEADO por la revalidación híbrida? (ADR-0114 §6).
 *  Estricto (default false): solo bloquea si el runtime lo afirma. */
export function isModuleBlocked(moduleId: string): boolean {
  return _blocked.value.has(moduleId);
}

/** Limpia el estado (al cerrar sesión). */
export function resetEntitlement(): void {
  _ids.value = null;
  _status.value = 'unknown';
  _offline.value = false;
  _reason.value = '';
  _blocked.value = new Set();
}

/**
 * Resuelve el entitlement del hub activo contra el endpoint del Cloud. Idempotente: se puede
 * llamar en boot y tras login. Si falla (p. ej. hub_id aún sin resolver), queda PERMISIVO — el
 * hub es online y no tiene sentido bloquearlo por un fallo transitorio de red. Un 410
 * `hub_not_found` lo maneja la capa de fetch del Cloud (`triggerHubGone`), no este gate.
 */
export async function resolveEntitlement(): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    resetEntitlement();
    return;
  }
  try {
    const { modules, blockedModules } = await cloudEntitlement();
    _ids.value = new Set(modules.map((m) => m.moduleId).filter(Boolean));
    _blocked.value = new Set(blockedModules);
    _status.value = 'unlocked';
    _offline.value = false;
    _reason.value = '';
  } catch {
    // Permisivo: no bloquear el shell web por un fallo transitorio (hub_id aún no listo, etc.).
    _ids.value = null;
    _status.value = 'unknown';
  }
}
