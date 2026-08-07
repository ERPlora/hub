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

/**
 * Alta. Es **exhaustiva** (plan paso 2b): la casilla `local` elige cuál de las dos identidades se
 * crea, y las dos son la MISMA fila `hub_user`.
 *
 *  - `local: true` (hub#355) → esta persona existe solo en la BD de este hub: **nombre + PIN**, sin
 *    email y sin nada en el SaaS. Guardas: PIN obligatorio, ningún rol administrativo y un nombre
 *    que el hub no conozca ya.
 *  - `local` ausente/`false` (hub#356) → **usuario de cuenta**: el **email es obligatorio**, el
 *    SaaS le manda la invitación y la contraseña la pone él (el administrador no la conoce jamás).
 *    El `pin` sigue siendo opcional —lo necesita quien además atiende la barra— y, si se teclea,
 *    pasa por las mismas reglas que el del usuario local.
 */
export interface NewHubUser {
  name: string;
  email: string;
  role: string;
  pin: string;
  local?: boolean;
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
  error?: { message?: string; code?: string } | string;
}

/**
 * Rechazo del runtime con su **código estable** (`hub.users.pin_in_use`, …) cuando lo trae. El
 * mensaje del runtime está en inglés y es solo el respaldo: lo que se enseña se traduce por i18n
 * contra el código (ver [`hubUserErrorKey`]).
 */
export class HubUsersError extends Error {
  constructor(message: string, readonly code?: string) {
    super(message);
    this.name = 'HubUsersError';
  }
}

/** Mensaje legible del envelope de error del runtime (`{ok:false,error:{message}}` o string). */
function errorMessage(body: unknown, fallback: string): string {
  const env = body as Envelope<unknown> | undefined;
  const error = env?.error;
  if (typeof error === 'string') return error;
  return error?.message ?? fallback;
}

/** Código estable del envelope, si el error viene del namespace del core (`hub.users.*`). */
function errorCode(body: unknown): string | undefined {
  const error = (body as Envelope<unknown> | undefined)?.error;
  return typeof error === 'string' ? undefined : error?.code;
}

function failed(body: unknown, fallback: string): HubUsersError {
  return new HubUsersError(errorMessage(body, fallback), errorCode(body));
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...runtimeHeaders() };
  if (init?.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${RUNTIME_URL}${path}`, { ...init, headers });
  const body = await res.json().catch(() => undefined);
  if (!res.ok) throw failed(body, `${path} → ${res.status}`);
  const env = body as Envelope<T>;
  if (env?.ok === false) throw failed(body, `${path} → error`);
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

/**
 * Rechazo de la activación de un rol que CONSERVA el motivo del runtime (hub#352/hub#353).
 *
 * El runtime rechaza por dos razones distintas —«es un rol base, siempre está encendido» y «no lo
 * declara ningún módulo instalado»— y cada una pide algo distinto del administrador: la primera es
 * un límite del producto, la segunda se resuelve instalando el módulo que trae ese rol. Aplanarlas
 * a «no se pudo activar» convierte la guarda en un interruptor mudo. Mismo contrato que
 * `ModuleActionError` (hub#314): `code` presente = hay un motivo que enseñar; sin él es un fallo de
 * transporte y la UI se queda con su mensaje genérico.
 */
export class RoleActivationError extends Error {
  readonly code?: string;

  constructor(message: string, code?: string) {
    super(message);
    this.name = 'RoleActivationError';
    this.code = code;
  }
}

/**
 * Enciende o apaga un rol del catálogo **en este hub**. Requiere sesión owner/admin.
 *
 * Devuelve el catálogo YA actualizado (lo que responde el endpoint): la pantalla se queda con el
 * estado que afirma el servidor en vez de pintar un optimismo local que un rechazo dejaría mintiendo.
 */
export async function setRoleActivation(key: string, active: boolean): Promise<HubRole[]> {
  const res = await fetch(`${RUNTIME_URL}/api/hub/roles/${encodeURIComponent(key)}`, {
    method: 'PUT',
    headers: { ...runtimeHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ active }),
  });
  const env = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    data?: HubRole[];
    error?: { code?: string; message?: string };
  };
  if (!res.ok || env.ok === false) {
    throw new RoleActivationError(
      env.error?.message ?? `roles/${key} → ${res.status}`,
      env.error?.code,
    );
  }
  return Array.isArray(env.data) ? env.data : [];
}

/**
 * De un catálogo, los roles que se le pueden DAR hoy a una persona en este hub.
 *
 * Espejo EN UI de `roles::ensure_assignable` del runtime, que sigue siendo la autoridad y
 * revalida: un rol **declarado por un módulo** solo se asigna si el hub lo ha encendido. Los
 * demás no se estrechan — un rol **base** es el contrato congelado del core, y uno **huérfano**
 * (tecleado a mano antes de que hubiera catálogo, o el resto de un módulo desinstalado) hay que
 * poder seguir reasignándolo o se rompen hubs que funcionan.
 *
 * Sirve para no ofrecer en el alta lo que el servidor va a rechazar: un desplegable con roles
 * inasignables hace que apagar un rol parezca que no hace nada.
 */
export function assignableRoles(roles: HubRole[]): HubRole[] {
  return roles.filter((role) => role.source?.kind !== 'module' || role.active);
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

// ── Alta de usuario LOCAL (plan paso 2b, hub#355) ─────────────────────────────────────────────

/** Roles que administran el hub (mismo conjunto que `is_admin_role` en el runtime). */
const ADMIN_ROLES = ['owner', 'admin'];

/** Prefijo de los códigos de rechazo del core en `/api/hub/users` (namespace reservado, ADR-0192). */
const HUB_USERS_ERROR_PREFIX = 'hub.users.';

/**
 * Clave i18n del motivo de un rechazo del runtime (`hub.users.pin_in_use` → `pin_in_use`), o
 * `undefined` si el error no trae uno (fallo de red, 401 del gate, un error del navegador).
 *
 * Es lo que permite enseñar el motivo **traducido**: el runtime responde en inglés a propósito
 * (regla del código en inglés) y el Hub se ve en español.
 */
export function hubUserErrorKey(error: unknown): string | undefined {
  const code = error instanceof HubUsersError ? error.code : undefined;
  return code?.startsWith(HUB_USERS_ERROR_PREFIX)
    ? code.slice(HUB_USERS_ERROR_PREFIX.length)
    : undefined;
}

/**
 * ¿Es este uno de los PIN que se prueban primero? Todo el mismo dígito (`0000`) o una cuesta
 * seguida, arriba o abajo (`1234`, `4321`). **Espejo** de `is_guessable_pin` del runtime, que es
 * quien manda; aquí solo sirve para no hacer pulsar «Crear» para enterarse.
 */
function isGuessablePin(pin: string): boolean {
  const digits = [...pin].map(Number);
  if (digits.length < 2 || digits.some(Number.isNaN)) return true;
  const stepIs = (step: number) => digits.every((d, i) => i === 0 || d - digits[i - 1] === step);
  return stepIs(0) || stepIs(1) || stepIs(-1);
}

/**
 * Motivo por el que el runtime rechazaría este alta **local**, o `''` si es admisible. Espejo EN UI
 * de `ensure_local_identity` (`crates/runtime/src/hub_users.rs`), igual que [`canDeactivate`] lo es
 * del guard de la baja: la autoridad sigue siendo el runtime, que revalida y responde 409.
 *
 * `pin_in_use` **no** se puede adelantar desde aquí: los PIN se guardan hasheados (argon2id con sal
 * propia) y el shell no los ve nunca. Ese motivo llega del servidor, por [`hubUserErrorKey`].
 */
export function localUserIssue(
  input: { name: string; role: string; pin: string },
  users: HubUser[],
): string {
  const pin = input.pin.trim();
  if (!pin) return 'local_needs_pin';
  if (pin.length < 4 || pin.length > 8 || !/^\d+$/.test(pin)) return 'pin_length';
  if (isGuessablePin(pin)) return 'pin_too_simple';
  if (ADMIN_ROLES.includes(input.role.trim().toLowerCase())) return 'local_cannot_administer';
  // Activos e inactivos: una persona = una fila, y un homónimo al lado de quien fue dado de baja
  // le devuelve por la espalda un PIN que funciona (hub#348).
  const name = input.name.trim().toLowerCase();
  if (users.some((u) => u.name.trim().toLowerCase() === name)) return 'name_taken';
  return '';
}

// ── Alta de usuario de CUENTA (plan paso 2b, hub#356) ─────────────────────────────────────────

/**
 * Roles que el **SaaS** sabe poner en una membresía (su `HUB_ROLES`) y, por tanto, los únicos que
 * puede llevar un usuario de cuenta. Espejo de `is_grantable_account_role` en el runtime.
 *
 * `owner` **no** está: la propiedad del hub sale de `HUB_OWNER_EMAIL` (ADR-0157), no de una
 * invitación. Y un rol que declara un módulo (`kitchen`, `waiter`…) es de ESTE hub y de ninguno
 * más, así que es del personal local.
 */
const ACCOUNT_ROLES = ['admin', 'manager', 'employee'];

/** Forma mínima de un email (la misma que valida el runtime). */
function looksLikeEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/**
 * Motivo por el que el runtime rechazaría este alta **de cuenta**, o `''` si es admisible. Gemelo
 * de [`localUserIssue`] para la otra identidad del paso 2b: la autoridad sigue siendo el runtime,
 * que revalida y responde 409.
 *
 * Aquí sí se puede adelantar el email duplicado —el censo que pinta Personal ya trae el email de
 * cada fila, activos e inactivos—, y merece la pena: es el rechazo que significa «esta persona ya
 * existe, reincorpórala», no «vuelve a intentarlo».
 */
export function accountUserIssue(
  input: { email: string; role: string; pin: string },
  users: HubUser[],
): string {
  const email = input.email.trim().toLowerCase();
  if (!email) return 'account_needs_email';
  if (!looksLikeEmail(email)) return 'invalid_email';
  if (!ACCOUNT_ROLES.includes(input.role.trim().toLowerCase())) return 'account_role_not_grantable';
  // Activos e inactivos: una persona = una fila, y volver a invitar a quien fue dado de baja
  // resucitaría por la espalda una membresía que alguien revocó (hub#348).
  if (users.some((u) => u.email.trim().toLowerCase() === email)) return 'email_taken';
  // El PIN es OPCIONAL para un usuario de cuenta —entra con su cuenta— pero, si lo teclea, es la
  // misma credencial que la del usuario local y pasa por las mismas reglas.
  const pin = input.pin.trim();
  if (!pin) return '';
  if (pin.length < 4 || pin.length > 8 || !/^\d+$/.test(pin)) return 'pin_length';
  if (isGuessablePin(pin)) return 'pin_too_simple';
  return '';
}

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
