// Personal (core) — cliente REST del runtime del Hub: `/api/hub/users` + `/api/hub/roles`.
//
// El personal del Hub son sus USUARIOS reales (tabla `hub_user` del core): el owner/administrador
// que entra por Cloud, los admins, y el personal solo-local que entra con PIN. NO es el módulo
// `staff` — ese es un módulo de negocio (profesional reservable, comisiones, horarios) con su
// propia navegación, y en la mayoría de hubs ni está instalado; pedirle la lista era la causa del
// «No se pudo cargar el personal».
//
// Contrato (ver `crates/server/src/hub_users.rs`):
//   GET    /api/hub/users        → HubUser[]   (cualquier sesión de usuario)
//   POST   /api/hub/users        → HubUser     (sesión owner/admin)
//   PUT    /api/hub/users/{id}   → HubUser     (sesión owner/admin; parcial)
//   DELETE /api/hub/users/{id}   → HubUser     (sesión owner/admin; baja = desactivar)
//   GET    /api/hub/roles        → HubRole[]   (cualquier sesión de usuario)
//   PUT    /api/hub/roles/{key}  → HubRole[]   (sesión owner/admin; `{active}` — hub#352)
//
// Mismo transporte que el resto del shell (`runtime.ts`): mismo origen + `runtimeHeaders()`.

import { RUNTIME_URL, runtimeHeaders } from './runtime';

/** Un usuario del hub tal y como lo lista el runtime. */
export interface HubUser {
  id: string;
  name: string;
  /** Email del perfil; cadena vacía si aún no tiene. */
  email: string;
  role: string;
  /** Id en el Cloud si la identidad está vinculada al portal; `null` en el personal solo-local. */
  cloud_user_id: string | null;
  /** `false` = dado de baja. Sigue listado (histórico y auditoría apuntan a su id). */
  is_active: boolean;
  /** `true` si puede entrar con PIN local; el owner normalmente entra por Cloud. */
  has_pin: boolean;
  created_at: string;
}

/** De dónde sale un rol del catálogo (hub#352). */
export type HubRoleSource =
  /** Rol base del core (`admin`/`manager`/`employee`): siempre en el catálogo y siempre activo. */
  | { kind: 'core' }
  /** Declarado en el `roles[]` de un módulo instalado y activo. */
  | { kind: 'module'; module_id: string }
  /** Ya no lo declara nadie, pero algún usuario todavía lo lleva (módulo desinstalado). */
  | { kind: 'in_use' };

/** Un rol del hub: catálogo base del core ∪ roles que declaran los módulos activos ∪ roles en uso. */
export interface HubRole {
  name: string;
  /** Etiqueta legible en **inglés canónico** (ADR-0055); la traducción va por i18n. */
  label: string;
  /** Rol base del que cuelga. Un rol base cuelga de sí mismo; uno huérfano, de nada. */
  extends: string;
  source: HubRoleSource;
  /** ¿Está vivo en ESTE hub? Los base, siempre; los declarados, solo si el admin los activó. */
  active: boolean;
  /** Permisos efectivos que concede (unión de `role_permissions` de los módulos activos). */
  permissions: number;
  /** Usuarios activos con ese rol. */
  members: number;
}

/** Alta: `pin` vacío = sin PIN (entra por Cloud); `email` vacío = sin email. */
export interface NewHubUser {
  name: string;
  email: string;
  role: string;
  pin: string;
}

/** Edición parcial: solo viaja lo que se toca. `pin: ''` retira el PIN. */
export interface HubUserPatch {
  name?: string;
  email?: string;
  role?: string;
  is_active?: boolean;
  pin?: string;
}

interface Envelope<T> {
  ok?: boolean;
  data?: T;
  error?: { message?: string } | string;
}

/** Mensaje legible del envelope de error del runtime (`{ok:false,error:{message}}` o string). */
function errorMessage(body: unknown, fallback: string): string {
  const env = body as Envelope<unknown> | undefined;
  const error = env?.error;
  if (typeof error === 'string') return error;
  return error?.message ?? fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...runtimeHeaders() };
  if (init?.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${RUNTIME_URL}${path}`, { ...init, headers });
  const body = await res.json().catch(() => undefined);
  if (!res.ok) throw new Error(errorMessage(body, `${path} → ${res.status}`));
  const env = body as Envelope<T>;
  if (env?.ok === false) throw new Error(errorMessage(body, `${path} → error`));
  return (env?.data ?? (body as T)) as T;
}

/** Todos los usuarios del hub (activos e inactivos, con PIN y sin él). */
export async function listHubUsers(): Promise<HubUser[]> {
  const data = await request<HubUser[]>('/api/hub/users');
  return Array.isArray(data) ? data : [];
}

/** Roles del hub con sus permisos y sus miembros. */
export async function listHubRoles(): Promise<HubRole[]> {
  const data = await request<HubRole[]>('/api/hub/roles');
  return Array.isArray(data) ? data : [];
}

/** Alta de usuario. Requiere sesión owner/admin. */
export function createHubUser(input: NewHubUser): Promise<HubUser> {
  return request<HubUser>('/api/hub/users', { method: 'POST', body: JSON.stringify(input) });
}

/** Edición parcial. Requiere sesión owner/admin. */
export function updateHubUser(id: string, patch: HubUserPatch): Promise<HubUser> {
  return request<HubUser>(`/api/hub/users/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

/** Baja = **desactivar**, nunca borrar. Requiere sesión owner/admin. */
export function deactivateHubUser(id: string): Promise<HubUser> {
  return request<HubUser>(`/api/hub/users/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

/** Cómo entra un usuario al Hub. `none` = existe como persona, pero no puede iniciar sesión. */
export type HubAccess = 'pin' | 'cloud' | 'none';

/**
 * Vía de acceso de un usuario. El **PIN manda** cuando hay ambas: es la del día a día en el POS.
 * `none` no es un error — es el registro de alguien que trabaja en el negocio pero no usa el Hub
 * (p. ej. un profesional reservable en la agenda). Distinguirlo importa: decir «cuenta online» de
 * quien no tiene cuenta hace creer que puede entrar.
 */
export function accessOf(user: HubUser): HubAccess {
  if (user.has_pin) return 'pin';
  return user.cloud_user_id ? 'cloud' : 'none';
}

/** Roles que administran el hub (mismo conjunto que `is_admin_role` en el runtime). */
const ADMIN_ROLES = ['owner', 'admin'];

/** ¿Este usuario administra el hub y está activo? */
function isActiveAdmin(user: HubUser): boolean {
  return user.is_active && ADMIN_ROLES.includes(user.role.toLowerCase());
}

/**
 * ¿Se le puede ofrecer al admin la acción «dar de baja» sobre `targetId`? Espejo EN UI del guard
 * del servidor (`crates/server/src/hub_users.rs`): nadie se da de baja a sí mismo y el hub no se
 * queda sin ningún administrador activo. Es solo para mostrar/ocultar la acción — la autoridad
 * sigue siendo el runtime, que revalida y responde 400.
 */
export function canDeactivate(users: HubUser[], actorId: string, targetId: string): boolean {
  const target = users.find((u) => u.id === targetId);
  if (!target || !target.is_active) return false;
  if (target.id === actorId) return false;
  if (!isActiveAdmin(target)) return true;
  return users.some((u) => u.id !== targetId && isActiveAdmin(u));
}
